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
        self._agreement_cache: Dict[int, str] = {}

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

    def tasks_for_month(
        self,
        employees: Sequence[Mapping[str, Any]],
        month_start: date,
        month_end: date,
    ) -> List[Dict[str, Any]]:
        """Return distinct projects creatives are planned on within a month."""
        if not employees:
            return []

        employee_map = self._build_employee_lookup(employees)
        if not employee_map:
            return []

        start_dt = datetime.combine(month_start, datetime.min.time())
        end_dt = datetime.combine(month_end + timedelta(days=1), datetime.min.time())

        domain = [
            ("start_datetime", "<=", end_dt.isoformat(sep=" ")),
            ("end_datetime", ">=", start_dt.isoformat(sep=" ")),
        ]
        fields = ["resource_id", "project_id", "start_datetime", "end_datetime", "x_studio_parent_task"]

        project_ids: Set[int] = set()
        project_names: Dict[int, str] = {}
        project_creatives: Dict[int, Set[int]] = {}
        # Store parent tasks per project to attach them later, or just store them in a list if we return a flat list of tasks (which we do, but currently it seems we group by project? No, we return a list of project-like dicts? Let's check the return type).
        # The current implementation returns a list of dicts, where each dict represents a *project* with aggregated info.
        # Wait, `tasks_for_month` returns `List[Dict[str, Any]]`.
        # Looking at the code:
        # for project_id in project_ids: ... tasks.append({...})
        # It seems it returns one entry per PROJECT.
        # But the user wants "Total Tasks" which implies counting tasks across projects or within projects.
        # If I aggregate by project, I lose the individual task granularity unless I aggregate tasks within the project entry.
        # The user says: "count the number of unique Parent tasks for the creatives we are filtering for".
        # So I should probably collect all unique parent tasks associated with the project (and the creatives).
        
        # Let's see how `tasks_for_month` works currently.
        # It iterates over slots, collects `project_id`.
        # Then it fetches project metadata.
        # Then it constructs the list of projects.
        
        # I need to change this to also collect parent task info.
        # Since `tasks_for_month` seems to return "projects" (based on `project_ids`), I might need to augment what it returns.
        # Or, I can change it to return "slots" or "tasks" but that might break existing consumers.
        # Let's look at `TasksService.calculate_tasks_statistics`.
        # It calls `self._tasks_for_month`.
        # Then `_summarize_tasks` iterates over these "tasks" (which are actually projects).
        # `total = len(tasks)` -> This confirms "Total Projects" is just the length of this list.
        
        # If I want "Total Tasks", I should probably attach the set of parent tasks to each project entry.
        # Then in `TasksService`, I can union all these sets to get the total unique tasks.
        
        project_parent_tasks: Dict[int, Set[str]] = {} # Map project_id -> set of parent task identifiers

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

                project_field = record.get("project_id")
                project_id: Optional[int] = None
                project_label: Optional[str] = None
                if isinstance(project_field, (list, tuple)) and len(project_field) >= 2:
                    raw_id = project_field[0]
                    project_id = raw_id if isinstance(raw_id, int) and raw_id > 0 else None
                    project_label = self._safe_str(project_field[1])
                elif isinstance(project_field, int):
                    project_id = project_field if project_field > 0 else None

                if project_id is None:
                    continue

                slot_start = self._parse_datetime(record.get("start_datetime"))
                slot_end = self._parse_datetime(record.get("end_datetime"))
                if not slot_start or not slot_end or slot_end <= slot_start:
                    continue

                overlap_start = max(slot_start, start_dt)
                overlap_end = min(slot_end, end_dt)
                if overlap_end <= overlap_start:
                    continue

                project_ids.add(project_id)
                if project_label and project_id not in project_names:
                    project_names[project_id] = project_label
                project_creatives.setdefault(project_id, set()).add(employee_id)
                
                # Capture parent task
                parent_task_field = record.get("x_studio_parent_task")
                if parent_task_field:
                    # Assuming Many2one: [id, "Name"]
                    if isinstance(parent_task_field, (list, tuple)) and len(parent_task_field) >= 2:
                        # Use ID as unique identifier, but maybe keep name for display if needed?
                        # For counting unique tasks, ID is best.
                        # Let's store a tuple or a composite string "id::name" to be safe and useful.
                        pt_id = parent_task_field[0]
                        pt_name = parent_task_field[1]
                        project_parent_tasks.setdefault(project_id, set()).add(f"{pt_id}::{pt_name}")
                    elif isinstance(parent_task_field, str):
                        # If it's a char field
                        project_parent_tasks.setdefault(project_id, set()).add(parent_task_field)
                    elif isinstance(parent_task_field, int):
                         project_parent_tasks.setdefault(project_id, set()).add(str(parent_task_field))


        if not project_ids:
            return []

        project_meta = self._fetch_project_metadata(project_ids)

        tasks: List[Dict[str, Any]] = []
        for project_id in project_ids:
            meta = project_meta.get(project_id, {})
            # Convert set of parent tasks to sorted list for JSON serialization
            parent_tasks_list = sorted(list(project_parent_tasks.get(project_id, set())))
            
            tasks.append(
                {
                    "project_id": project_id,
                    "project_name": self._safe_str(
                        meta.get("name"),
                        default=project_names.get(project_id, "Unassigned Project"),
                    ),
                    "agreement_type": self._format_agreement_label(
                        meta.get("x_studio_agreement_type_1"),
                        meta.get("agreement_type_names")
                    ),
                    "market": self._format_project_market(meta.get("x_studio_market_2")),
                    "tags": meta.get("tag_names") if isinstance(meta.get("tag_names"), list) else [],
                    "creator_ids": sorted(project_creatives.get(project_id, set())),
                    "parent_tasks": parent_tasks_list,
                }
            )

        return tasks

    def _fetch_project_metadata(self, project_ids: Set[int]) -> Dict[int, Mapping[str, Any]]:
        if not project_ids:
            return {}

        projects: Dict[int, Mapping[str, Any]] = {}
        for batch in self.client.search_read_chunked(
            "project.project",
            domain=[("id", "in", list(project_ids))],
            fields=["id", "name", "x_studio_agreement_type_1", "x_studio_market_2", "tag_ids"],
        ):
            for record in batch:
                project_id = record.get("id")
                if isinstance(project_id, int):
                    projects[project_id] = record

        if not projects:
            return {}

        # Resolve agreement type IDs to names (similar to external_hours_service)
        agreement_ids: Set[int] = set()
        for record in projects.values():
            raw_agreements = record.get("x_studio_agreement_type_1") or []
            for agreement_id in raw_agreements:
                if isinstance(agreement_id, int):
                    agreement_ids.add(agreement_id)
                elif isinstance(agreement_id, (list, tuple)) and len(agreement_id) >= 1:
                    raw_id = agreement_id[0]
                    if isinstance(raw_id, int):
                        agreement_ids.add(raw_id)

        agreement_map = self._fetch_agreement_types(agreement_ids) if agreement_ids else {}
        for record in projects.values():
            raw_agreements = record.get("x_studio_agreement_type_1") or []
            agreement_names = []
            for agreement_id in raw_agreements:
                if isinstance(agreement_id, int):
                    name = agreement_map.get(agreement_id)
                    if name:
                        agreement_names.append(name)
                elif isinstance(agreement_id, (list, tuple)) and len(agreement_id) >= 1:
                    raw_id = agreement_id[0]
                    if isinstance(raw_id, int):
                        name = agreement_map.get(raw_id)
                        if name:
                            agreement_names.append(name)
            record["agreement_type_names"] = agreement_names

        # Resolve tag IDs to names to mimic client dashboard behavior.
        tag_ids: Set[int] = set()
        for record in projects.values():
            for tag_id in record.get("tag_ids") or []:
                if isinstance(tag_id, int):
                    tag_ids.add(tag_id)

        tag_names = self._fetch_project_tags(tag_ids) if tag_ids else {}
        for record in projects.values():
            ids = record.get("tag_ids") or []
            record["tag_names"] = [tag_names.get(tag_id, f"Tag {tag_id}") for tag_id in ids if isinstance(tag_id, int)]
        return projects

    def _fetch_agreement_types(self, type_ids: Set[int]) -> Dict[int, str]:
        """Fetch agreement type names from Odoo, using cache to avoid duplicate requests."""
        ids = [type_id for type_id in type_ids if isinstance(type_id, int)]
        if not ids:
            return {}
        missing = [type_id for type_id in ids if type_id not in self._agreement_cache]
        if missing:
            records = self.client.read("x_agreement_type", missing, ["display_name", "x_name"])
            for record in records:
                type_id = record.get("id")
                if not isinstance(type_id, int):
                    continue
                name = record.get("display_name") or record.get("x_name")
                self._agreement_cache[type_id] = self._safe_str(name, default=f"Agreement {type_id}")
        mapping: Dict[int, str] = {}
        for type_id in ids:
            if type_id in self._agreement_cache:
                mapping[type_id] = self._agreement_cache[type_id]
        return mapping

    def _fetch_project_tags(self, tag_ids: Set[int]) -> Dict[int, str]:
        ids = [tag_id for tag_id in tag_ids if isinstance(tag_id, int)]
        if not ids:
            return {}
        tags = self.client.read("project.tags", ids, ["name"])
        mapping: Dict[int, str] = {}
        for tag in tags:
            tag_id = tag.get("id")
            if isinstance(tag_id, int):
                mapping[tag_id] = self._safe_str(tag.get("name"), default=f"Tag {tag_id}")
        return mapping

    def _format_project_market(self, raw_market: Any) -> str:
        if isinstance(raw_market, (list, tuple)) and len(raw_market) >= 2:
            return self._safe_str(raw_market[1], default="Unassigned Market")
        return self._safe_str(raw_market, default="Unassigned Market")

    def _format_agreement_label(self, raw_agreement: Any, agreement_type_names: Any = None) -> str:
        """Format agreement type label, preferring resolved names over raw data."""
        # First try to use the resolved agreement type names (like external_hours_service)
        if agreement_type_names is not None:
            if isinstance(agreement_type_names, list):
                cleaned = [self._safe_str(name).strip() for name in agreement_type_names if isinstance(name, str)]
                cleaned = [name for name in cleaned if name]
                if cleaned:
                    return ", ".join(cleaned)
        
        # Fallback to parsing raw agreement data
        if isinstance(raw_agreement, (list, tuple)):
            labels: List[str] = []
            for item in raw_agreement:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    label = self._safe_str(item[1])
                else:
                    label = self._safe_str(item)
                if label and label not in {"0", "[]"}:
                    labels.append(label)
            if labels:
                return ", ".join(labels)

        if isinstance(raw_agreement, (str, int)):
            value = self._safe_str(raw_agreement)
            if value and value not in {"0", "[]"}:
                return value

        return ""

    def _safe_str(self, value: Any, *, default: str = "") -> str:
        if value is None:
            return default
        try:
            return str(value).strip() or default
        except Exception:
            return default

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
