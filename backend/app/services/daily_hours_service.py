"""Per-day hours breakdown for a single creative (card calendar view)."""
from __future__ import annotations

import threading
from collections import defaultdict
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Set

from ..config import OdooSettings
from ..integrations.odoo_client import OdooClient
from .availability_service import HOURS_PER_DAY
from .overtime_service import _CreativeMatcher, _extract_owner_id, _extract_owner_name
from .planning_service import PlanningService

# Absence data (time off / public holidays) is fetched over the viewed period
# plus this pad so it can load in parallel with the planning slots while still
# covering slots that start/end outside the period. Slots exceeding the pad
# trigger a (rare) sequential top-up fetch.
ABSENCE_PAD_DAYS = 45

# Long-lived worker pool with one Odoo client per thread. Keeping the clients
# (and their HTTPS connections) alive across requests removes the TLS
# handshake that otherwise dominates this endpoint's latency; xmlrpc's
# transport retries once when a kept-alive connection has gone cold.
_WORKER_POOL = ThreadPoolExecutor(max_workers=6, thread_name_prefix="dailyhours")
_THREAD_STATE = threading.local()


def _pooled_client(settings: OdooSettings) -> OdooClient:
    client: Optional[OdooClient] = getattr(_THREAD_STATE, "client", None)
    if (
        client is None
        or client.settings.url != settings.url
        or client.settings.db != settings.db
    ):
        client = OdooClient(settings)
        _THREAD_STATE.client = client
    return client


def run_pooled(settings: OdooSettings, fn: Callable[[OdooClient], Any]) -> Future:
    """Run fn(client) on the shared worker pool with a persistent client."""
    return _WORKER_POOL.submit(lambda: fn(_pooled_client(settings)))


class DailyHoursService:
    """Compute logged / booked / overtime hours per day for one creative.

    Reuses PlanningService's calendar helpers (workday patterns, per-day
    time-off and public-holiday fetchers, slot proration) so day-level math
    stays consistent with the monthly aggregates shown on the dashboard.
    """

    def __init__(self, client: OdooClient):
        self.client = client
        self._planning = PlanningService(client)

    @classmethod
    def from_settings(cls, settings: OdooSettings) -> "DailyHoursService":
        return cls(OdooClient(settings))

    def daily_breakdown(
        self,
        creative: Mapping[str, Any],
        period_start: date,
        period_end: date,
    ) -> Dict[str, Any]:
        employee_id = creative.get("id")
        if not isinstance(employee_id, int) or period_end < period_start:
            return {"creative_id": None, "days": []}

        meta = self._planning._build_employee_metadata([creative]).get(employee_id) or {
            "workdays": set(),
            "company_id": None,
        }
        workdays: Set[int] = meta["workdays"]

        start_dt = datetime.combine(period_start, datetime.min.time())
        end_dt = datetime.combine(period_end + timedelta(days=1), datetime.min.time())
        pad = timedelta(days=ABSENCE_PAD_DAYS)

        # The five Odoo queries are independent, so run them concurrently on
        # the shared worker pool (persistent per-thread clients, no handshake).
        settings = self.client.settings
        resource_id = creative.get("resource_id")
        resource_id = resource_id if isinstance(resource_id, int) else None

        def own(fn):
            return lambda client: fn(DailyHoursService(client))

        f_slots = run_pooled(
            settings,
            own(lambda svc: svc._fetch_slots(employee_id, creative, start_dt, end_dt, resource_id)),
        )
        # Logged hours and time off both live in account.analytic.line: one
        # query over the padded range serves both maps.
        f_analytic = run_pooled(
            settings,
            own(lambda svc: svc._analytic_lines_by_day(
                employee_id,
                period_start,
                period_end,
                (start_dt - pad).date(),
                (end_dt + pad).date(),
            )),
        )
        f_overtime = run_pooled(
            settings, own(lambda svc: svc._overtime_by_day(creative, start_dt, end_dt))
        )
        f_holidays = run_pooled(
            settings,
            own(lambda svc: svc._planning._fetch_public_holiday_hours_by_date(
                {employee_id: meta}, start_dt - pad, end_dt + pad
            )),
        )
        slots = f_slots.result()
        logged, time_off, logged_by_project = f_analytic.result()
        overtime, overtime_by_project = f_overtime.result()
        holidays = f_holidays.result().get(employee_id, {})

        # Absences must cover the full span of any slot so proration
        # denominators match planned_hours_for_month. The padded fetch above
        # almost always covers this; top up sequentially when a slot exceeds it.
        slot_min = min((s["start"] for s in slots), default=start_dt)
        slot_max = max((s["end"] for s in slots), default=end_dt)
        if slot_min < start_dt - pad or slot_max > end_dt + pad:
            absence_start = min(slot_min, start_dt)
            absence_end = max(slot_max, end_dt)
            time_off = self._planning._fetch_time_off_by_date(
                [employee_id], absence_start.date(), (absence_end - timedelta(microseconds=1)).date()
            ).get(employee_id, {})
            holidays = self._planning._fetch_public_holiday_hours_by_date(
                {employee_id: meta}, absence_start, absence_end
            ).get(employee_id, {})

        absences = self._merge_absences(time_off, holidays)
        booked, booked_by_project = self._prorate_slots_by_day(
            slots, start_dt, end_dt, workdays, absences
        )

        days = self._build_days_list(
            period_start, period_end, workdays, logged, booked, overtime, time_off, holidays
        )
        projects = self._combine_project_hours(logged_by_project, booked_by_project)
        overtime_projects = self._combine_overtime_projects(
            overtime_by_project, logged_by_project, booked_by_project
        )

        return {
            "creative_id": employee_id,
            "days": days,
            "projects": projects,
            "overtime_projects": overtime_projects,
        }

    def daily_breakdown_bulk(
        self,
        creatives: Sequence[Mapping[str, Any]],
        period_start: date,
        period_end: date,
    ) -> Dict[int, Dict[str, Any]]:
        """Days + projects for MANY creatives in five batched Odoo queries.

        Same math as daily_breakdown, but fetched month-wide once (analytic
        lines, all planning slots, approvals, holidays, resource links)
        instead of per employee — this is what makes background warming of
        every card affordable (~5 queries instead of ~5 per creative).
        """
        employees = [c for c in creatives if isinstance(c.get("id"), int)]
        if not employees or period_end < period_start:
            return {}

        employee_ids = [c["id"] for c in employees]
        meta_map = self._planning._build_employee_metadata(employees)

        start_dt = datetime.combine(period_start, datetime.min.time())
        end_dt = datetime.combine(period_end + timedelta(days=1), datetime.min.time())
        pad = timedelta(days=ABSENCE_PAD_DAYS)
        settings = self.client.settings

        def own(fn):
            return lambda client: fn(DailyHoursService(client))

        f_resources = run_pooled(
            settings, own(lambda svc: svc._fetch_resource_map(employee_ids))
        )
        f_analytic = run_pooled(
            settings,
            own(lambda svc: svc._analytic_lines_bulk(
                employee_ids, period_start, period_end,
                (start_dt - pad).date(), (end_dt + pad).date(),
            )),
        )
        f_slots = run_pooled(settings, own(lambda svc: svc._fetch_all_slots(start_dt, end_dt)))
        f_overtime = run_pooled(
            settings, own(lambda svc: svc._overtime_bulk(employees, start_dt, end_dt))
        )
        f_holidays = run_pooled(
            settings,
            own(lambda svc: svc._planning._fetch_public_holiday_hours_by_date(
                meta_map, start_dt - pad, end_dt + pad
            )),
        )

        resource_map = f_resources.result()
        analytic = f_analytic.result()
        raw_slots = f_slots.result()
        overtime_by_day_map, overtime_by_project_map = f_overtime.result()
        holidays_map = f_holidays.result()

        slots_by_employee: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
        for slot in raw_slots:
            emp_id = resource_map.get(slot.get("resource_id"))
            if emp_id is not None:
                slots_by_employee[emp_id].append(slot)

        # Top up absence data when any slot extends beyond the padded window
        # (rare) so proration denominators stay exact, mirroring the single path.
        slot_min = min((s["start"] for s in raw_slots), default=start_dt)
        slot_max = max((s["end"] for s in raw_slots), default=end_dt)
        extended_time_off: Optional[Dict[int, Dict[date, float]]] = None
        if slot_min < start_dt - pad or slot_max > end_dt + pad:
            absence_start = min(slot_min, start_dt)
            absence_end = max(slot_max, end_dt)
            extended_time_off = self._planning._fetch_time_off_by_date(
                employee_ids, absence_start.date(), (absence_end - timedelta(microseconds=1)).date()
            )
            holidays_map = self._planning._fetch_public_holiday_hours_by_date(
                meta_map, absence_start, absence_end
            )

        out: Dict[int, Dict[str, Any]] = {}
        for creative in employees:
            emp_id = creative["id"]
            meta = meta_map.get(emp_id) or {"workdays": set(), "company_id": None}
            workdays: Set[int] = meta["workdays"]
            entry = analytic.get(emp_id) or {"logged": {}, "time_off": {}, "projects": {}}
            logged = entry["logged"]
            time_off = (
                extended_time_off.get(emp_id, {}) if extended_time_off is not None else entry["time_off"]
            )
            holidays = holidays_map.get(emp_id, {})
            overtime = overtime_by_day_map.get(emp_id, {})

            absences = self._merge_absences(time_off, holidays)
            booked, booked_by_project = self._prorate_slots_by_day(
                slots_by_employee.get(emp_id, []), start_dt, end_dt, workdays, absences
            )
            out[emp_id] = {
                "days": self._build_days_list(
                    period_start, period_end, workdays, logged, booked, overtime, time_off, holidays
                ),
                "projects": self._combine_project_hours(entry["projects"], booked_by_project),
                "overtime_projects": self._combine_overtime_projects(
                    overtime_by_project_map.get(emp_id, {}), entry["projects"], booked_by_project
                ),
            }
        return out

    def _fetch_resource_map(self, employee_ids: Sequence[int]) -> Dict[int, int]:
        """resource.resource id -> employee id, one batched hr.employee read."""
        wanted = [eid for eid in employee_ids if isinstance(eid, int)]
        if not wanted:
            return {}
        rows = self.client.execute_kw(
            "hr.employee",
            "search_read",
            [[("id", "in", wanted)]],
            {"fields": ["resource_id"], "context": {"active_test": False}},
        )
        mapping: Dict[int, int] = {}
        for row in rows or []:
            emp_id = row.get("id")
            value = row.get("resource_id")
            resource_id = (
                value[0]
                if isinstance(value, (list, tuple)) and value and isinstance(value[0], int)
                else value if isinstance(value, int) else None
            )
            if isinstance(emp_id, int) and resource_id is not None:
                mapping[resource_id] = emp_id
        return mapping

    def _fetch_all_slots(self, start_dt: datetime, end_dt: datetime) -> List[Dict[str, Any]]:
        """All planning slots overlapping the period, with their resource id."""
        domain = [
            ("start_datetime", "<=", end_dt.isoformat(sep=" ")),
            ("end_datetime", ">=", start_dt.isoformat(sep=" ")),
        ]
        fields = ["resource_id", "allocated_hours", "start_datetime", "end_datetime", "project_id"]

        slots: List[Dict[str, Any]] = []
        for batch in self.client.search_read_chunked(
            "planning.slot",
            domain=domain,
            fields=fields,
            order="start_datetime asc",
            chunk_size=2000,
        ):
            for record in batch:
                allocated = float(record.get("allocated_hours") or 0.0)
                slot_start = self._planning._parse_datetime(record.get("start_datetime"))
                slot_end = self._planning._parse_datetime(record.get("end_datetime"))
                if allocated <= 0 or not slot_start or not slot_end or slot_end <= slot_start:
                    continue

                resource_field = record.get("resource_id")
                resource_id = (
                    resource_field[0]
                    if isinstance(resource_field, (list, tuple))
                    and resource_field
                    and isinstance(resource_field[0], int)
                    else resource_field if isinstance(resource_field, int) else None
                )
                project_field = record.get("project_id")
                project_name = (
                    str(project_field[1])
                    if isinstance(project_field, (list, tuple)) and len(project_field) >= 2
                    else "Unassigned Project"
                )
                slots.append(
                    {
                        "allocated": allocated,
                        "start": slot_start,
                        "end": slot_end,
                        "project_name": project_name,
                        "resource_id": resource_id,
                    }
                )
        return slots

    def _overtime_bulk(
        self,
        creatives: Sequence[Mapping[str, Any]],
        start_dt: datetime,
        end_dt: datetime,
    ) -> tuple[Dict[int, Dict[date, float]], Dict[int, Dict[str, float]]]:
        """Approved overtime per employee, one query for everyone:
        (hours by day per employee, hours by project per employee).

        Attribution reuses _CreativeMatcher: exact res.users id join first,
        name fallback only for creatives without a linked user.
        """
        matcher = _CreativeMatcher([dict(c) for c in creatives])

        domain = [
            ("date_start", ">=", start_dt.isoformat(sep=" ")),
            ("date_start", "<", end_dt.isoformat(sep=" ")),
            ("request_status", "=", "approved"),
        ]
        fields = ["date_start", "x_studio_hours", "request_owner_id", "x_studio_project"]

        totals: Dict[int, Dict[date, float]] = defaultdict(lambda: defaultdict(float))
        by_project: Dict[int, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for batch in self.client.search_read_chunked(
            "approval.request",
            domain=domain,
            fields=fields,
            order="date_start asc, id asc",
        ):
            for record in batch:
                owner_field = record.get("request_owner_id")
                emp_id = matcher.resolve(
                    _extract_owner_id(owner_field), _extract_owner_name(owner_field)
                )
                if emp_id is None:
                    continue

                parsed = self._planning._parse_datetime(record.get("date_start"))
                if not parsed:
                    continue

                hours = float(record.get("x_studio_hours") or 0.0)
                if hours > 0:
                    totals[emp_id][parsed.date()] += hours
                    by_project[emp_id][self._ot_project_name(record)] += hours
        return (
            {emp_id: dict(day_map) for emp_id, day_map in totals.items()},
            {emp_id: dict(proj_map) for emp_id, proj_map in by_project.items()},
        )

    @staticmethod
    def _combine_overtime_projects(
        overtime_by_project: Mapping[str, float],
        logged_by_project: Mapping[str, float],
        booked_by_project: Mapping[str, float],
    ) -> List[Dict[str, Any]]:
        """Rows for the card's Overtime section, most overtime first.

        overtime: approved OT hours taken on the project.
        logged_overtime: hours logged above booking (max(logged - booked, 0)),
        i.e. how much extra time the project actually needed. Projects appear
        when either signal is positive so unrequested over-work still shows.
        """
        names = set(overtime_by_project)
        for name in set(logged_by_project) | set(booked_by_project):
            if logged_by_project.get(name, 0.0) - booked_by_project.get(name, 0.0) > 0:
                names.add(name)

        rows: List[Dict[str, Any]] = []
        for name in names:
            taken = round(overtime_by_project.get(name, 0.0), 2)
            over_logged = round(
                max(logged_by_project.get(name, 0.0) - booked_by_project.get(name, 0.0), 0.0), 2
            )
            if taken <= 0 and over_logged <= 0:
                continue
            rows.append({"project_name": name, "overtime": taken, "logged_overtime": over_logged})
        rows.sort(key=lambda r: (r["overtime"], r["logged_overtime"]), reverse=True)
        return rows

    @staticmethod
    def _merge_absences(
        time_off: Mapping[date, float], holidays: Mapping[date, float]
    ) -> Dict[date, float]:
        """Combine per-day time off + holidays, capped at a full working day."""
        absences: Dict[date, float] = {}
        for source in (time_off, holidays):
            for day, hours in source.items():
                absences[day] = min(absences.get(day, 0.0) + max(hours, 0.0), HOURS_PER_DAY)
        return absences

    @staticmethod
    def _build_days_list(
        period_start: date,
        period_end: date,
        workdays: Set[int],
        logged: Mapping[date, float],
        booked: Mapping[date, float],
        overtime: Mapping[date, float],
        time_off: Mapping[date, float],
        holidays: Mapping[date, float],
    ) -> List[Dict[str, Any]]:
        days: List[Dict[str, Any]] = []
        current = period_start
        while current <= period_end:
            is_workday = current.weekday() in workdays
            days.append(
                {
                    "date": current.isoformat(),
                    "weekday": current.weekday(),
                    "expected": HOURS_PER_DAY if is_workday else 0.0,
                    "logged": round(logged.get(current, 0.0), 2),
                    "booked": round(booked.get(current, 0.0), 2),
                    "overtime": round(overtime.get(current, 0.0), 2),
                    "time_off": round(min(time_off.get(current, 0.0), HOURS_PER_DAY), 2),
                    "holiday": round(min(holidays.get(current, 0.0), HOURS_PER_DAY), 2),
                }
            )
            current += timedelta(days=1)
        return days

    @staticmethod
    def _combine_project_hours(
        logged_by_project: Mapping[str, float],
        booked_by_project: Mapping[str, float],
    ) -> List[Dict[str, Any]]:
        """Merge per-project logged and booked hours, busiest projects first."""
        names = set(logged_by_project) | set(booked_by_project)
        projects = [
            {
                "project_name": name,
                "logged": round(logged_by_project.get(name, 0.0), 2),
                "booked": round(booked_by_project.get(name, 0.0), 2),
            }
            for name in names
        ]
        projects.sort(key=lambda p: (p["logged"] + p["booked"], p["logged"]), reverse=True)
        return projects

    def _analytic_lines_by_day(
        self,
        employee_id: int,
        period_start: date,
        period_end: date,
        absence_start: date,
        absence_end: date,
    ) -> tuple[Dict[date, float], Dict[date, float], Dict[str, float]]:
        """Single-employee wrapper over the bulk analytic-line pass."""
        entry = self._analytic_lines_bulk(
            [employee_id], period_start, period_end, absence_start, absence_end
        ).get(employee_id)
        if not entry:
            return {}, {}, {}
        return entry["logged"], entry["time_off"], entry["projects"]

    def _analytic_lines_bulk(
        self,
        employee_ids: Sequence[int],
        period_start: date,
        period_end: date,
        absence_start: date,
        absence_end: date,
    ) -> Dict[int, Dict[str, Dict]]:
        """One analytic-line query serving three maps per employee:
        logged by day, time_off by day, logged by project.

        Logged: non-Time-Off hours per day within the viewed period (same
        exclusion as TimesheetService). Time off: Internal-project "Time Off"
        task hours per day over the wider absence range (same filter as
        PlanningService._fetch_time_off_by_date, applied client-side). The
        per-project map reuses the same rows, so the Worked Projects section
        costs no extra Odoo round trip.
        """
        wanted = {eid for eid in employee_ids if isinstance(eid, int)}
        if not wanted:
            return {}
        fetch_start = min(period_start, absence_start)
        fetch_end = max(period_end, absence_end)
        domain = [
            ("employee_id", "in", list(wanted)),
            ("date", ">=", fetch_start.isoformat()),
            ("date", "<=", fetch_end.isoformat()),
        ]
        fields = ["employee_id", "date", "unit_amount", "task_id", "project_id"]

        out: Dict[int, Dict[str, Dict]] = {
            eid: {
                "logged": defaultdict(float),
                "time_off": defaultdict(float),
                "projects": defaultdict(float),
            }
            for eid in wanted
        }
        for batch in self.client.search_read_chunked(
            "account.analytic.line",
            domain=domain,
            fields=fields,
            order="date asc, id asc",
            chunk_size=2000,
        ):
            for record in batch:
                emp_field = record.get("employee_id")
                emp_id = (
                    emp_field[0]
                    if isinstance(emp_field, (list, tuple)) and emp_field
                    else emp_field if isinstance(emp_field, int) else None
                )
                entry = out.get(emp_id)
                if entry is None:
                    continue

                try:
                    entry_date = date.fromisoformat(str(record.get("date")))
                except (TypeError, ValueError):
                    continue

                hours = float(record.get("unit_amount") or 0.0)
                if hours <= 0:
                    continue

                task_field = record.get("task_id")
                task_name = (
                    str(task_field[1])
                    if isinstance(task_field, (list, tuple)) and len(task_field) >= 2
                    else task_field if isinstance(task_field, str) else None
                )
                project_field = record.get("project_id")
                project_name = (
                    str(project_field[1])
                    if isinstance(project_field, (list, tuple)) and len(project_field) >= 2
                    else project_field if isinstance(project_field, str) else None
                )

                is_time_off_task = bool(task_name) and task_name.strip().lower() == "time off"
                if is_time_off_task:
                    if project_name == "Internal" and task_name == "Time Off":
                        entry["time_off"][entry_date] += hours
                    continue

                if period_start <= entry_date <= period_end:
                    entry["logged"][entry_date] += hours
                    entry["projects"][project_name or "Unassigned Project"] += hours

        return {
            eid: {
                "logged": dict(entry["logged"]),
                "time_off": dict(entry["time_off"]),
                "projects": dict(entry["projects"]),
            }
            for eid, entry in out.items()
        }

    def _fetch_slots(
        self,
        employee_id: int,
        creative: Mapping[str, Any],
        start_dt: datetime,
        end_dt: datetime,
        resource_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Planning slots overlapping the period, filtered to this employee.

        Primary filter is the employee's resource id (exact, server-side),
        passed in by the caller when already known. Falls back to the name
        matching used by planned_hours_for_month when unavailable.
        """
        if resource_id is None:
            resource_id = self._get_resource_id(employee_id)

        domain: List[Any] = [
            ("start_datetime", "<=", end_dt.isoformat(sep=" ")),
            ("end_datetime", ">=", start_dt.isoformat(sep=" ")),
        ]
        if resource_id is not None:
            domain.append(("resource_id", "=", resource_id))
        fields = ["resource_id", "allocated_hours", "start_datetime", "end_datetime", "project_id"]

        employee_lookup = (
            None if resource_id is not None else self._planning._build_employee_lookup([creative])
        )

        slots: List[Dict[str, Any]] = []
        for batch in self.client.search_read_chunked(
            "planning.slot",
            domain=domain,
            fields=fields,
            order="start_datetime asc",
            chunk_size=2000,
        ):
            for record in batch:
                if employee_lookup is not None:
                    matched = self._planning._match_employee(record.get("resource_id"), employee_lookup)
                    if matched != employee_id:
                        continue

                allocated = float(record.get("allocated_hours") or 0.0)
                slot_start = self._planning._parse_datetime(record.get("start_datetime"))
                slot_end = self._planning._parse_datetime(record.get("end_datetime"))
                if allocated <= 0 or not slot_start or not slot_end or slot_end <= slot_start:
                    continue

                project_field = record.get("project_id")
                project_name = (
                    str(project_field[1])
                    if isinstance(project_field, (list, tuple)) and len(project_field) >= 2
                    else "Unassigned Project"
                )
                slots.append(
                    {
                        "allocated": allocated,
                        "start": slot_start,
                        "end": slot_end,
                        "project_name": project_name,
                    }
                )
        return slots

    def _get_resource_id(self, employee_id: int) -> Optional[int]:
        try:
            rows = self.client.execute_kw(
                "hr.employee", "read", [[employee_id]], {"fields": ["resource_id"]}
            )
        except Exception:
            return None
        for row in rows or []:
            value = row.get("resource_id")
            if isinstance(value, (list, tuple)) and value and isinstance(value[0], int):
                return value[0]
            if isinstance(value, int):
                return value
        return None

    def _prorate_slots_by_day(
        self,
        slots: List[Dict[str, Any]],
        start_dt: datetime,
        end_dt: datetime,
        workdays: Set[int],
        absences: Mapping[date, float],
    ) -> tuple[Dict[date, float], Dict[str, float]]:
        """Distribute each slot's allocated hours across the days it spans.

        Same denominator logic as planned_hours_for_month: working hours over
        the whole slot, with a raw-duration fallback when that is zero.
        Returns (hours by day, hours by project) from the same pass.
        """
        totals: Dict[date, float] = defaultdict(float)
        by_project: Dict[str, float] = defaultdict(float)

        for slot in slots:
            slot_start: datetime = slot["start"]
            slot_end: datetime = slot["end"]
            allocated: float = slot["allocated"]

            denominator = self._planning._working_hours_between(
                slot_start, slot_end, workdays, absences
            )
            use_raw = denominator <= 0
            if use_raw:
                denominator = (slot_end - slot_start).total_seconds() / 3600.0
                if denominator <= 0:
                    continue

            overlap_start = max(slot_start, start_dt)
            overlap_end = min(slot_end, end_dt)

            current = overlap_start
            while current < overlap_end:
                day = current.date()
                day_start = datetime.combine(day, datetime.min.time())
                next_day = day_start + timedelta(days=1)
                segment_start = max(current, day_start)
                segment_end = min(overlap_end, next_day)
                if segment_end <= segment_start:
                    current = next_day
                    continue

                if use_raw:
                    day_hours = (segment_end - segment_start).total_seconds() / 3600.0
                else:
                    day_hours = self._planning._working_hours_between(
                        segment_start, segment_end, workdays, absences
                    )

                if day_hours > 0:
                    share = allocated * min(day_hours / denominator, 1.0)
                    totals[day] += share
                    by_project[slot.get("project_name") or "Unassigned Project"] += share
                current = next_day

        return dict(totals), dict(by_project)

    def _overtime_by_day(
        self,
        creative: Mapping[str, Any],
        start_dt: datetime,
        end_dt: datetime,
    ) -> tuple[Dict[date, float], Dict[str, float]]:
        """Approved overtime for this creative: (hours by day, hours by project).

        Filters server-side on the linked res.users id when available;
        otherwise falls back to the same name matching OvertimeService uses.
        """
        user_id = creative.get("user_id")

        domain: List[Any] = [
            ("date_start", ">=", start_dt.isoformat(sep=" ")),
            ("date_start", "<", end_dt.isoformat(sep=" ")),
            ("request_status", "=", "approved"),
        ]
        if isinstance(user_id, int):
            domain.append(("request_owner_id", "=", user_id))
        fields = ["date_start", "x_studio_hours", "request_owner_id", "x_studio_project"]

        matcher = None if isinstance(user_id, int) else _CreativeMatcher([dict(creative)])
        employee_id = creative.get("id")

        totals: Dict[date, float] = defaultdict(float)
        by_project: Dict[str, float] = defaultdict(float)
        for batch in self.client.search_read_chunked(
            "approval.request",
            domain=domain,
            fields=fields,
            order="date_start asc, id asc",
        ):
            for record in batch:
                if matcher is not None:
                    owner_field = record.get("request_owner_id")
                    matched = matcher.resolve(
                        _extract_owner_id(owner_field), _extract_owner_name(owner_field)
                    )
                    if matched != employee_id:
                        continue

                parsed = self._planning._parse_datetime(record.get("date_start"))
                if not parsed:
                    continue

                hours = float(record.get("x_studio_hours") or 0.0)
                if hours > 0:
                    totals[parsed.date()] += hours
                    by_project[self._ot_project_name(record)] += hours
        return dict(totals), dict(by_project)

    @staticmethod
    def _ot_project_name(record: Mapping[str, Any]) -> str:
        project_field = record.get("x_studio_project")
        if isinstance(project_field, (list, tuple)) and len(project_field) >= 2:
            return str(project_field[1])
        return "Unassigned Project"
