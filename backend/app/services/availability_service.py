"""Availability calculations for creatives based on shifts and time off."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Set, Tuple

from ..config import OdooSettings
from ..integrations.odoo_client import OdooClient


DAY_PATTERNS: Mapping[frozenset[str], Set[int]] = {
    frozenset({"sun-thu", "sunthu"}): {6, 0, 1, 2, 3},
    frozenset({"mon-fri", "monfri"}): {0, 1, 2, 3, 4},
    frozenset({"sat-wed", "satwed"}): {5, 6, 0, 1, 2},
    frozenset({"fri-tue", "fritue"}): {4, 5, 6, 0, 1},
}

DEFAULT_WORKWEEK = {0, 1, 2, 3, 4}
HOURS_PER_DAY = 8.0


@dataclass(frozen=True)
class AvailabilitySummary:
    base_hours: float
    time_off_hours: float
    public_holiday_hours: float
    public_holiday_details: List[Dict[str, Any]]  # List of holidays with their hours

    @property
    def available_hours(self) -> float:
        return max(self.base_hours - (self.time_off_hours + self.public_holiday_hours), 0.0)


class AvailabilityService:
    """Calculate monthly availability metrics for creatives."""

    def __init__(self, client: OdooClient):
        self.client = client

    @classmethod
    def from_settings(cls, settings: OdooSettings) -> "AvailabilityService":
        return cls(OdooClient(settings))

    def calculate_monthly_availability(
        self,
        employees: Sequence[Mapping[str, object]],
        month_start: date,
        month_end: date,
    ) -> Dict[int, AvailabilitySummary]:
        if not employees:
            return {}

        employee_meta: Dict[int, Dict[str, Any]] = {}
        for emp in employees:
            emp_id = emp.get("id")
            if not isinstance(emp_id, int):
                continue
            workdays = self._working_weekdays(emp.get("resource_calendar_name"))
            company_id = emp.get("company_id")
            employee_meta[emp_id] = {
                "record": emp,
                "workdays": workdays,
                "company_id": company_id if isinstance(company_id, int) else None,
            }

        if not employee_meta:
            return {}

        employee_ids = list(employee_meta.keys())

        base_hours = {
            emp_id: self._calculate_base_hours(
                meta["record"],
                month_start,
                month_end,
                workdays=meta["workdays"],
            )
            for emp_id, meta in employee_meta.items()
        }
        time_off_hours = self._fetch_time_off_hours(employee_ids, month_start, month_end)
        holiday_data = self._fetch_public_holiday_hours(employee_meta, month_start, month_end)

        return {
            emp_id: AvailabilitySummary(
                base_hours=base_hours.get(emp_id, 0.0),
                time_off_hours=time_off_hours.get(emp_id, 0.0),
                public_holiday_hours=holiday_data.get(emp_id, (0.0, []))[0],
                public_holiday_details=holiday_data.get(emp_id, (0.0, []))[1],
            )
            for emp_id in employee_ids
        }

    def _calculate_base_hours(
        self,
        employee: Mapping[str, object],
        month_start: date,
        month_end: date,
        *,
        workdays: Optional[Set[int]] = None,
    ) -> float:
        workday_set = workdays or self._working_weekdays(employee.get("resource_calendar_name"))
        total_days = self._count_workdays(month_start, month_end, workday_set)
        return float(total_days) * HOURS_PER_DAY

    def _working_weekdays(self, calendar_name: object) -> Set[int]:
        if not isinstance(calendar_name, str):
            return DEFAULT_WORKWEEK

        normalized = calendar_name.lower().replace(" ", "")
        for keys, weekdays in DAY_PATTERNS.items():
            if any(key in normalized for key in keys):
                return weekdays
        return DEFAULT_WORKWEEK

    def _count_workdays(self, start: date, end: date, workdays: Iterable[int]) -> int:
        workday_set = set(workdays)
        current = start
        count = 0
        while current <= end:
            if current.weekday() in workday_set:
                count += 1
            current += timedelta(days=1)
        return count

    def _fetch_time_off_hours(
        self,
        employee_ids: Sequence[int],
        month_start: date,
        month_end: date,
    ) -> Dict[int, float]:
        if not employee_ids:
            return {}

        start_str = month_start.isoformat()
        end_str = month_end.isoformat()

        domain = [
            ("employee_id", "in", list(employee_ids)),
            ("date", ">=", start_str),
            ("date", "<=", end_str),
            ("project_id.name", "=", "Internal"),
            ("task_id.name", "=", "Time Off"),
        ]
        fields = ["employee_id", "unit_amount"]

        totals: MutableMapping[int, float] = {}
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

                hours = float(record.get("unit_amount") or 0.0)
                totals[employee_id] = totals.get(employee_id, 0.0) + hours

        return dict(totals)

    def _fetch_public_holiday_hours(
        self,
        employee_meta: Mapping[int, Dict[str, Any]],
        month_start: date,
        month_end: date,
    ) -> Dict[int, Tuple[float, List[Dict[str, Any]]]]:
        """Return a dict mapping employee_id to (total_hours, holiday_details_list)."""
        if not employee_meta:
            return {}

        totals: Dict[int, Tuple[float, List[Dict[str, Any]]]] = {
            emp_id: (0.0, []) for emp_id in employee_meta
        }
        company_map: Dict[int, List[int]] = {}

        for emp_id, meta in employee_meta.items():
            company_id = meta.get("company_id")
            if isinstance(company_id, int):
                company_map.setdefault(company_id, []).append(emp_id)

        if not company_map:
            return totals

        start_dt = datetime.combine(month_start, datetime.min.time())
        end_dt = datetime.combine(month_end + timedelta(days=1), datetime.min.time())

        for company_id, emp_ids in company_map.items():
            holidays = self._get_company_holidays(company_id, start_dt, end_dt)
            if not holidays:
                continue

            pattern_cache: Dict[Tuple[int, ...], Tuple[float, List[Dict[str, Any]]]] = {}
            for emp_id in emp_ids:
                workdays = employee_meta[emp_id]["workdays"]
                pattern_key = tuple(sorted(workdays))
                if pattern_key not in pattern_cache:
                    pattern_cache[pattern_key] = self._calculate_holiday_hours_for_pattern(
                        holidays,
                        set(workdays),
                        month_start,
                        month_end,
                    )
                totals[emp_id] = pattern_cache[pattern_key]

        return totals

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
        fields = ["name", "date_from", "date_to"]

        holidays: List[Mapping[str, Any]] = []
        for batch in self.client.search_read_chunked(
            "resource.calendar.leaves",
            domain=domain,
            fields=fields,
            order="date_from asc",
        ):
            holidays.extend(batch)
        return holidays

    def _calculate_holiday_hours_for_pattern(
        self,
        holidays: Sequence[Mapping[str, Any]],
        workdays: Set[int],
        month_start: date,
        month_end: date,
    ) -> Tuple[float, List[Dict[str, Any]]]:
        """Return (total_hours, holiday_details_list) where each detail has name, date_from, date_to, hours."""
        if not holidays or not workdays:
            return (0.0, [])

        total_hours = 0.0
        holiday_details: List[Dict[str, Any]] = []
        
        for holiday in holidays:
            hours = self._holiday_hours_within_period(
                holiday,
                workdays,
                month_start,
                month_end,
            )
            if hours > 0:
                total_hours += hours
                # Extract dates for display - use the raw values from Odoo
                date_from_raw = holiday.get("date_from")
                date_to_raw = holiday.get("date_to")
                
                # Parse dates for display in breakdown
                display_from = self._format_holiday_date_for_display(date_from_raw)
                display_to = self._format_holiday_date_for_display(date_to_raw)
                
                # Debug: Log formatted dates
                import logging
                logger = logging.getLogger(__name__)
                logger.debug(f"Holiday '{holiday.get('name')}': raw_from={date_from_raw!r}, formatted_from={display_from!r}, raw_to={date_to_raw!r}, formatted_to={display_to!r}, hours={hours}")
                
                holiday_details.append({
                    "name": holiday.get("name", "Unknown Holiday"),
                    "date_from": display_from,
                    "date_to": display_to,
                    "hours": hours,
                })
        
        return (total_hours, holiday_details)
    
    def _format_holiday_date_for_display(self, date_value: Any) -> str:
        """Format a holiday date for display in the breakdown.
        
        Converts UTC datetime to local time (GMT+3) before extracting the date.
        """
        if not date_value:
            return "Unknown"
        
        try:
            # Parse as UTC and convert to local time (GMT+3)
            dt_utc = self._parse_datetime_as_utc(date_value)
            if dt_utc:
                # Convert UTC to GMT+3
                gmt3_offset = timedelta(hours=3)
                dt_local = dt_utc + gmt3_offset
                return dt_local.date().isoformat()
            return "Unknown"
        except (ValueError, TypeError):
            return str(date_value)

    def _holiday_hours_within_period(
        self,
        holiday: Mapping[str, Any],
        workdays: Set[int],
        month_start: date,
        month_end: date,
    ) -> float:
        """Calculate holiday hours within a period.
        
        Odoo stores datetimes in UTC. We need to parse them as UTC and convert to local time
        (GMT+3) to get the correct date. For example:
        - "2025-09-03 21:00:00" UTC = "2025-09-04 00:00:00" GMT+3 (Sep 4)
        - "2025-09-04 20:59:59" UTC = "2025-09-04 23:59:59" GMT+3 (Sep 4)
        """
        date_from_str = holiday.get("date_from")
        date_to_str = holiday.get("date_to")
        
        if not date_from_str or not date_to_str:
            return 0.0
        
        # Parse datetimes as UTC (Odoo stores in UTC)
        start_dt_utc = self._parse_datetime_as_utc(date_from_str)
        end_dt_utc = self._parse_datetime_as_utc(date_to_str)
        
        if not start_dt_utc or not end_dt_utc:
            return 0.0

        # Convert UTC to GMT+3 (local timezone)
        # GMT+3 is UTC+3
        gmt3_offset = timedelta(hours=3)
        start_dt_local = start_dt_utc + gmt3_offset
        end_dt_local = end_dt_utc + gmt3_offset
        
        # Extract dates from local time
        holiday_start_date = start_dt_local.date()
        
        # Check if end_dt is at midnight (00:00:00) - if so, it's exclusive
        if end_dt_local.hour == 0 and end_dt_local.minute == 0 and end_dt_local.second == 0:
            # Exclusive: holiday ends at the start of this day, so it was active until the end of the previous day
            holiday_end_date = (end_dt_local - timedelta(days=1)).date()
        else:
            # Inclusive: holiday is active on this day
            holiday_end_date = end_dt_local.date()
        
        # Ensure the holiday overlaps with the month
        if holiday_end_date < month_start or holiday_start_date > month_end:
            return 0.0

        # Calculate the overlap range
        start_date = max(holiday_start_date, month_start)
        end_date = min(holiday_end_date, month_end)
        
        if end_date < start_date:
            return 0.0

        # Count workdays within the overlap range
        total_days = 0
        current_date = start_date
        while current_date <= end_date:
            if current_date.weekday() in workdays:
                total_days += 1
            current_date += timedelta(days=1)

        return float(total_days * HOURS_PER_DAY)

    def _parse_datetime_as_utc(self, value: Any) -> Optional[datetime]:
        """Parse an Odoo datetime string as UTC.
        
        Odoo stores datetimes in UTC. This function parses the string and returns
        a naive datetime representing UTC time.
        """
        if isinstance(value, datetime):
            # If already a datetime, use as-is (assume it's UTC)
            return datetime(value.year, value.month, value.day, value.hour, value.minute, value.second, value.microsecond)
        if isinstance(value, str):
            candidate = value.replace("T", " ")
            try:
                # Parse the datetime string
                parsed = datetime.fromisoformat(candidate)
                # If timezone-aware, convert to UTC naive datetime
                if parsed.tzinfo is not None:
                    # Convert to UTC and remove timezone info
                    utc_dt = parsed.astimezone(timezone.utc)
                    return datetime(utc_dt.year, utc_dt.month, utc_dt.day, utc_dt.hour, utc_dt.minute, utc_dt.second, utc_dt.microsecond)
                # If naive, assume it's UTC
                return parsed
            except ValueError:
                return None
        return None

    def _parse_datetime(self, value: Any) -> Optional[datetime]:
        """Parse an Odoo datetime string into a datetime object.
        
        This is a legacy method kept for backward compatibility.
        For holiday calculations, use _parse_datetime_as_utc instead.
        """
        if isinstance(value, datetime):
            return datetime(value.year, value.month, value.day, value.hour, value.minute, value.second, value.microsecond)
        if isinstance(value, str):
            candidate = value.replace("T", " ")
            try:
                parsed = datetime.fromisoformat(candidate)
                if parsed.tzinfo is not None:
                    return datetime(parsed.year, parsed.month, parsed.day, parsed.hour, parsed.minute, parsed.second, parsed.microsecond)
                return parsed
            except ValueError:
                return None
        return None
