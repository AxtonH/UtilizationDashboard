"""Planning-related helpers for computing per-creative planned hours."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, DefaultDict, Dict, List, Mapping, MutableMapping, Optional, Sequence, Set

from ..config import OdooSettings
from ..integrations.odoo_client import OdooClient
from .availability_service import DAY_PATTERNS, DEFAULT_WORKWEEK, HOURS_PER_DAY


class PlanningService:
    """Fetch and aggregate planned hours for creatives within a month."""

    def __init__(self, client: OdooClient):
        self.client = client

    @classmethod
    def from_settings(cls, settings: OdooSettings) -> "PlanningService":
        return cls(OdooClient(settings))

    def planned_hours_for_month(
        self,
        employees: Sequence[Mapping[str, Any]],
        month_start: date,
        month_end: date,
    ) -> Dict[int, float]:
        if not employees:
            return {}

        employee_map = self._build_employee_lookup(employees)
        if not employee_map:
            return {}

        employee_meta = self._build_employee_metadata(employees)
        if not employee_meta:
            return {}

        start_dt = datetime.combine(month_start, datetime.min.time())
        end_dt = datetime.combine(month_end + timedelta(days=1), datetime.min.time())

        domain = [
            ("start_datetime", "<=", end_dt.isoformat(sep=" ")),
            ("end_datetime", ">=", start_dt.isoformat(sep=" ")),
        ]
        fields = ["resource_id", "allocated_hours", "start_datetime", "end_datetime"]

        totals: MutableMapping[int, float] = {emp_id: 0.0 for emp_id in employee_map.values()}
        slots: List[Dict[str, Any]] = []
        earliest_start: Optional[datetime] = None
        latest_end: Optional[datetime] = None

        # Collect all relevant slots first so we can build absence data over their span.
        for batch in self.client.search_read_chunked(
            "planning.slot",
            domain=domain,
            fields=fields,
            order="start_datetime asc",
        ):
            for record in batch:
                employee_id = self._match_employee(record.get("resource_id"), employee_map)
                if employee_id is None:
                    continue

                allocated_hours = float(record.get("allocated_hours") or 0.0)
                if allocated_hours <= 0:
                    continue

                slot_start = self._parse_datetime(record.get("start_datetime"))
                slot_end = self._parse_datetime(record.get("end_datetime"))
                if not slot_start or not slot_end or slot_end <= slot_start:
                    continue

                slots.append(
                    {
                        "employee_id": employee_id,
                        "allocated": allocated_hours,
                        "start": slot_start,
                        "end": slot_end,
                    }
                )

                if earliest_start is None or slot_start < earliest_start:
                    earliest_start = slot_start
                if latest_end is None or slot_end > latest_end:
                    latest_end = slot_end

        if not slots:
            return dict(totals)

        absence_lookup = self._build_absence_lookup(employee_meta, earliest_start, latest_end)

        for slot in slots:
            employee_id = slot["employee_id"]
            meta = employee_meta.get(employee_id)
            if not meta:
                continue

            workdays: Set[int] = meta["workdays"]
            absences = absence_lookup.get(employee_id)
            slot_start: datetime = slot["start"]
            slot_end: datetime = slot["end"]

            denominator = self._working_hours_between(slot_start, slot_end, workdays, absences)

            overlap_start = max(slot_start, start_dt)
            overlap_end = min(slot_end, end_dt)
            if overlap_end <= overlap_start:
                continue

            if denominator > 0:
                overlap_hours = self._working_hours_between(overlap_start, overlap_end, workdays, absences)
                ratio = overlap_hours / denominator if denominator else 0.0
            else:
                # Fallback to raw time-based ratio if we cannot infer a working-hour denominator.
                overlap_hours = self._overlap_hours(slot_start, slot_end, start_dt, end_dt)
                if overlap_hours <= 0:
                    continue
                slot_duration_hours = (slot_end - slot_start).total_seconds() / 3600.0
                if slot_duration_hours <= 0:
                    continue
                ratio = overlap_hours / slot_duration_hours

            ratio = min(max(ratio, 0.0), 1.0)
            if ratio == 0.0:
                continue

            totals[employee_id] = totals.get(employee_id, 0.0) + (slot["allocated"] * ratio)

        return dict(totals)

    def _build_employee_lookup(self, employees: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
        lookup: Dict[str, int] = {}
        for employee in employees:
            emp_id = employee.get("id")
            name = employee.get("name")
            if not isinstance(emp_id, int) or not isinstance(name, str):
                continue
            normalized = self._normalize_name(name)
            if normalized:
                lookup[normalized] = emp_id
        return lookup

    def _build_employee_metadata(self, employees: Sequence[Mapping[str, Any]]) -> Dict[int, Dict[str, Any]]:
        metadata: Dict[int, Dict[str, Any]] = {}
        for employee in employees:
            emp_id = employee.get("id")
            if not isinstance(emp_id, int):
                continue

            workdays = self._working_weekdays(employee.get("resource_calendar_name"))
            company_id = employee.get("company_id")
            metadata[emp_id] = {
                "workdays": workdays,
                "company_id": company_id if isinstance(company_id, int) else None,
            }
        return metadata

    def _match_employee(self, resource_field: Any, lookup: Dict[str, int]) -> Optional[int]:
        if isinstance(resource_field, (list, tuple)) and len(resource_field) >= 2:
            label = str(resource_field[1])
        elif isinstance(resource_field, str):
            label = resource_field
        else:
            return None

        candidate = self._normalize_name(label.split("(")[0])
        if candidate and candidate in lookup:
            return lookup[candidate]

        # Fallback to substring matching if direct normalization fails.
        normalized_label = self._normalize_name(label)
        for key, emp_id in lookup.items():
            if key in normalized_label:
                return emp_id

        return None

    def _normalize_name(self, value: str | None) -> str:
        if not value:
            return ""
        return " ".join(value.lower().split())

    def _working_weekdays(self, calendar_name: Any) -> Set[int]:
        if not isinstance(calendar_name, str):
            return set(DEFAULT_WORKWEEK)

        normalized = calendar_name.lower().replace(" ", "")
        for keys, weekdays in DAY_PATTERNS.items():
            if any(key in normalized for key in keys):
                return set(weekdays)
        return set(DEFAULT_WORKWEEK)

    def _build_absence_lookup(
        self,
        employee_meta: Mapping[int, Mapping[str, Any]],
        range_start: Optional[datetime],
        range_end: Optional[datetime],
    ) -> Dict[int, Dict[date, float]]:
        if not employee_meta or range_start is None or range_end is None:
            return {}

        # Make the date bounds inclusive on both ends.
        start_date = range_start.date()
        end_date = (range_end - timedelta(microseconds=1)).date()

        employee_ids = list(employee_meta.keys())
        time_off = self._fetch_time_off_by_date(employee_ids, start_date, end_date)
        holidays = self._fetch_public_holiday_hours_by_date(employee_meta, range_start, range_end)

        combined: Dict[int, Dict[date, float]] = {}
        for emp_id in employee_ids:
            entries: Dict[date, float] = {}
            for source in (time_off.get(emp_id), holidays.get(emp_id)):
                if not source:
                    continue
                for day, hours in source.items():
                    current = entries.get(day, 0.0)
                    # Cap at a full working day to avoid negative allocations.
                    entries[day] = min(current + max(hours, 0.0), HOURS_PER_DAY)
            if entries:
                combined[emp_id] = entries
        return combined

    def _fetch_time_off_by_date(
        self,
        employee_ids: Sequence[int],
        start_date: date,
        end_date: date,
    ) -> Dict[int, Dict[date, float]]:
        if not employee_ids or start_date > end_date:
            return {}

        domain = [
            ("employee_id", "in", list(employee_ids)),
            ("date", ">=", start_date.isoformat()),
            ("date", "<=", end_date.isoformat()),
            ("project_id.name", "=", "Internal"),
            ("task_id.name", "=", "Time Off"),
        ]
        fields = ["employee_id", "unit_amount", "date"]

        totals: DefaultDict[int, DefaultDict[date, float]] = defaultdict(lambda: defaultdict(float))
        for batch in self.client.search_read_chunked(
            "account.analytic.line",
            domain=domain,
            fields=fields,
            order="date asc",
        ):
            for record in batch:
                employee_field = record.get("employee_id")
                if isinstance(employee_field, (list, tuple)) and employee_field:
                    employee_id = employee_field[0]
                elif isinstance(employee_field, int):
                    employee_id = employee_field
                else:
                    continue

                if employee_id not in employee_ids:
                    continue

                date_value = record.get("date")
                try:
                    entry_date = date.fromisoformat(str(date_value))
                except (TypeError, ValueError):
                    continue

                hours = float(record.get("unit_amount") or 0.0)
                if hours <= 0:
                    continue

                totals[employee_id][entry_date] += hours

        return {emp_id: dict(day_map) for emp_id, day_map in totals.items()}

    def _fetch_public_holiday_hours_by_date(
        self,
        employee_meta: Mapping[int, Mapping[str, Any]],
        range_start: datetime,
        range_end: datetime,
    ) -> Dict[int, Dict[date, float]]:
        if not employee_meta:
            return {}

        start_dt = range_start
        end_dt = range_end

        company_map: Dict[int, List[int]] = {}
        for emp_id, meta in employee_meta.items():
            company_id = meta.get("company_id")
            if isinstance(company_id, int):
                company_map.setdefault(company_id, []).append(emp_id)

        if not company_map:
            return {}

        totals: DefaultDict[int, DefaultDict[date, float]] = defaultdict(lambda: defaultdict(float))

        for company_id, emp_ids in company_map.items():
            holidays = self._get_company_holidays(company_id, start_dt, end_dt)
            if not holidays:
                continue

            for holiday in holidays:
                holiday_start = self._parse_datetime(holiday.get("date_from"))
                holiday_end = self._parse_datetime(holiday.get("date_to"))
                if not holiday_start or not holiday_end:
                    continue

                effective_start = max(holiday_start, start_dt)
                effective_end = min(holiday_end, end_dt)
                if effective_end <= effective_start:
                    continue

                current = effective_start
                while current < effective_end:
                    day = current.date()
                    day_start = datetime.combine(day, datetime.min.time())
                    next_day = day_start + timedelta(days=1)
                    segment_start = max(current, day_start)
                    segment_end = min(effective_end, next_day)
                    if segment_end <= segment_start:
                        current = next_day
                        continue

                    segment_hours = (segment_end - segment_start).total_seconds() / 3600.0
                    segment_hours = min(segment_hours, HOURS_PER_DAY)
                    if segment_hours <= 0:
                        current = next_day
                        continue

                    for emp_id in emp_ids:
                        workdays: Set[int] = employee_meta[emp_id]["workdays"]
                        if day.weekday() not in workdays:
                            continue
                        current_total = totals[emp_id][day]
                        totals[emp_id][day] = min(current_total + segment_hours, HOURS_PER_DAY)

                    current = next_day

        return {emp_id: dict(day_map) for emp_id, day_map in totals.items()}

    def _get_company_holidays(
        self,
        company_id: int,
        start_dt: datetime,
        end_dt: datetime,
    ) -> List[Mapping[str, Any]]:
        start_str = start_dt.isoformat(sep=" ")
        end_str = end_dt.isoformat(sep=" ")
        domain = [
            ("company_id", "=", company_id),
            ("resource_id", "=", False),
            ("date_from", "<=", end_str),
            ("date_to", ">=", start_str),
        ]
        fields = ["date_from", "date_to"]

        holidays: List[Mapping[str, Any]] = []
        for batch in self.client.search_read_chunked(
            "resource.calendar.leaves",
            domain=domain,
            fields=fields,
            order="date_from asc",
        ):
            holidays.extend(batch)
        return holidays

    def _overlap_hours(
        self,
        slot_start: datetime,
        slot_end: datetime,
        range_start: datetime,
        range_end: datetime,
    ) -> float:
        start = max(slot_start, range_start)
        end = min(slot_end, range_end)
        if end <= start:
            return 0.0
        return (end - start).total_seconds() / 3600.0

    def _working_hours_between(
        self,
        start_dt: datetime,
        end_dt: datetime,
        workdays: Set[int],
        absences: Optional[Mapping[date, float]] = None,
    ) -> float:
        if end_dt <= start_dt:
            return 0.0

        absence_map = absences or {}
        total_hours = 0.0

        current = start_dt
        while current < end_dt:
            day = current.date()
            day_start = datetime.combine(day, datetime.min.time())
            next_day = day_start + timedelta(days=1)
            segment_start = max(current, day_start)
            segment_end = min(end_dt, next_day)
            if segment_end <= segment_start:
                current = next_day
                continue

            if segment_start.weekday() not in workdays:
                current = next_day
                continue

            segment_hours = (segment_end - segment_start).total_seconds() / 3600.0
            if segment_hours >= 24:
                segment_hours = HOURS_PER_DAY
            else:
                segment_hours = min(segment_hours, HOURS_PER_DAY)

            if segment_hours <= 0:
                current = next_day
                continue

            absence_hours = min(absence_map.get(day, 0.0), HOURS_PER_DAY)
            effective_hours = max(segment_hours - min(absence_hours, segment_hours), 0.0)
            if effective_hours > 0:
                total_hours += effective_hours

            current = next_day

        return total_hours

    def _parse_datetime(self, value: Any) -> Optional[datetime]:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            candidate = value.replace("T", " ")
            try:
                return datetime.fromisoformat(candidate)
            except ValueError:
                return None
        return None
