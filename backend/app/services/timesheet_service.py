"""Timesheet aggregation utilities for creatives."""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, Iterable, Mapping, MutableMapping, Optional, Sequence

from ..config import OdooSettings
from ..integrations.odoo_client import OdooClient


class TimesheetService:
    """Fetch logged timesheet hours for creatives within a month."""

    def __init__(self, client: OdooClient):
        self.client = client

    @classmethod
    def from_settings(cls, settings: OdooSettings) -> "TimesheetService":
        return cls(OdooClient(settings))

    def logged_hours_for_month(
        self,
        employees: Sequence[Mapping[str, Any]],
        month_start: date,
        month_end: date,
    ) -> Dict[int, float]:
        employee_ids = self._extract_employee_ids(employees)
        if not employee_ids:
            return {}

        domain = [
            ("employee_id", "in", list(employee_ids)),
            ("date", ">=", month_start.isoformat()),
            ("date", "<=", month_end.isoformat()),
        ]
        fields = ["employee_id", "task_id", "unit_amount"]

        totals: MutableMapping[int, float] = {emp_id: 0.0 for emp_id in employee_ids}
        for batch in self.client.search_read_chunked(
            "account.analytic.line",
            domain=domain,
            fields=fields,
            order="date asc, id asc",
        ):
            for record in batch:
                employee_id = self._parse_employee_id(record.get("employee_id"))
                if employee_id is None or employee_id not in employee_ids:
                    continue

                task_name = self._parse_task_name(record.get("task_id"))
                if task_name and task_name.strip().lower() == "time off":
                    continue

                hours = self._parse_hours(record.get("unit_amount"))
                if hours <= 0:
                    continue

                totals[employee_id] = totals.get(employee_id, 0.0) + hours

        return {emp_id: totals.get(emp_id, 0.0) for emp_id in employee_ids if totals.get(emp_id, 0.0) > 0}

    def _extract_employee_ids(self, employees: Iterable[Mapping[str, Any]]) -> set[int]:
        ids: set[int] = set()
        for employee in employees:
            emp_id = employee.get("id")
            if isinstance(emp_id, int):
                ids.add(emp_id)
        return ids

    def _parse_employee_id(self, value: Any) -> Optional[int]:
        if isinstance(value, int):
            return value
        if isinstance(value, (list, tuple)) and value:
            try:
                return int(value[0])
            except (TypeError, ValueError):
                return None
        return None

    def _parse_task_name(self, value: Any) -> Optional[str]:
        if isinstance(value, str):
            return value
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            return str(value[1])
        return None

    def _parse_hours(self, value: Any) -> float:
        try:
            return float(value or 0.0)
        except (TypeError, ValueError):
            return 0.0
