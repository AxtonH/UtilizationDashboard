"""Overtime statistics service for creative dashboard."""
from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from ..config import OdooSettings
from ..integrations.odoo_client import OdooClient


class OvertimeService:
    """Calculate overtime statistics from approval requests."""

    def __init__(self, client: OdooClient):
        self.client = client

    @classmethod
    def from_settings(cls, settings: OdooSettings) -> "OvertimeService":
        """Create an OvertimeService instance from Odoo settings."""
        return cls(OdooClient(settings))

    def calculate_overtime_statistics(
        self,
        month_start: date,
        month_end: date,
    ) -> Dict[str, Any]:
        """Calculate overtime statistics for a given month.
        
        Args:
            month_start: Start date of the month
            month_end: End date of the month
            
        Returns:
            Dictionary with total overtime hours and top projects
        """
        start_dt = datetime.combine(month_start, datetime.min.time())
        end_dt = datetime.combine(month_end + timedelta(days=1), datetime.min.time())
        
        domain = [
            ("date_start", ">=", start_dt.isoformat(sep=" ")),
            ("date_start", "<", end_dt.isoformat(sep=" ")),
            ("request_status", "=", "approved"),
        ]
        
        fields = ["id", "x_studio_hours", "x_studio_project", "date_start"]
        
        overtime_requests = []
        try:
            for batch in self.client.search_read_chunked(
                "approval.request",
                domain=domain,
                fields=fields,
                order="date_start asc, id asc",
            ):
                overtime_requests.extend(batch)
        except Exception as e:
            # Log error and return empty result
            print(f"Error fetching overtime requests: {e}")
            return {
                "total_hours": 0.0,
                "total_hours_display": "0h",
                "top_projects": [],
            }
        
        # Calculate total hours
        total_hours = 0.0
        project_hours: Dict[str, float] = {}
        
        for request in overtime_requests:
            hours = self._safe_float(request.get("x_studio_hours"))
            if hours <= 0:
                continue
            
            total_hours += hours
            
            # Group by project
            project_field = request.get("x_studio_project")
            if isinstance(project_field, (list, tuple)) and len(project_field) >= 2:
                project_id = project_field[0]
                project_name = str(project_field[1])
            else:
                project_name = "Unassigned Project"
            
            project_hours[project_name] = project_hours.get(project_name, 0.0) + hours
        
        # Get top 5 projects
        top_projects = sorted(
            [
                {"project_name": name, "hours": hours, "hours_display": self._format_hours(hours)}
                for name, hours in project_hours.items()
            ],
            key=lambda x: x["hours"],
            reverse=True,
        )[:5]
        
        return {
            "total_hours": total_hours,
            "total_hours_display": self._format_hours(total_hours),
            "top_projects": top_projects,
        }

    def _safe_float(self, value: Any) -> float:
        """Safely convert value to float."""
        if value is None:
            return 0.0
        try:
            return float(value)
        except (ValueError, TypeError):
            return 0.0

    def _format_hours(self, hours: float) -> str:
        """Format hours as a string."""
        if hours == 0:
            return "0h"
        if hours < 1:
            minutes = int(hours * 60)
            return f"{minutes}m"
        if hours == int(hours):
            return f"{int(hours)}h"
        return f"{hours:.1f}h"

