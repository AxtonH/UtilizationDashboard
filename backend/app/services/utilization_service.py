"""Utilization dashboard service for company-wide metrics."""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, List

from .availability_service import AvailabilityService
from .employee_service import EmployeeService
from .external_hours_service import ExternalHoursService
from .planning_service import PlanningService
from .timesheet_service import TimesheetService


POOL_DEFINITIONS = [
    {"slug": "ksa", "label": "KSA", "tag": "ksa"},
    {"slug": "nightshift", "label": "Nightshift", "tag": "nightshift"},
    {"slug": "uae", "label": "UAE", "tag": "uae"},
]


class UtilizationService:
    """Aggregate company-wide utilization metrics."""

    def __init__(
        self,
        employee_service: EmployeeService,
        availability_service: AvailabilityService,
        planning_service: PlanningService,
        timesheet_service: TimesheetService,
        external_hours_service: ExternalHoursService,
    ):
        self.employee_service = employee_service
        self.availability_service = availability_service
        self.planning_service = planning_service
        self.timesheet_service = timesheet_service
        self.external_hours_service = external_hours_service

    def get_utilization_summary(self, month_start: date, month_end: date) -> Dict[str, Any]:
        """Get company-wide utilization summary for the specified month."""
        creatives = self.employee_service.get_creatives()

        # Get availability data
        summaries = self.availability_service.calculate_monthly_availability(
            creatives, month_start, month_end
        )

        # Get planned and logged hours
        planned_hours = self.planning_service.planned_hours_for_month(
            creatives, month_start, month_end
        )
        logged_hours = self.timesheet_service.logged_hours_for_month(
            creatives, month_start, month_end
        )

        # Get external hours
        external_data = self.external_hours_service.external_hours_for_month(
            month_start, month_end
        )
        subscription_data = self.external_hours_service.subscription_hours_for_month(
            month_start, month_end
        )

        # Calculate totals
        total_available_hours = sum(
            summary.available_hours for summary in summaries.values()
        )
        total_planned_hours = sum(planned_hours.values())
        total_logged_hours = sum(logged_hours.values())

        # External hours breakdown
        total_external_hours = external_data.get("summary", {}).get("total_external_hours", 0.0)
        total_subscription_used_hours = subscription_data.get("summary", {}).get(
            "total_subscription_used_hours", 0.0
        )
        total_external_used_hours = total_external_hours + total_subscription_used_hours

        # Available creatives count
        available_creatives_count = sum(
            1 for summary in summaries.values() if summary.available_hours > 0
        )

        # Calculate pool statistics
        pool_stats = self._calculate_pool_stats(
            creatives, summaries, planned_hours, logged_hours
        )

        return {
            "available_creatives": available_creatives_count,
            "total_available_hours": round(total_available_hours, 2),
            "total_planned_hours": round(total_planned_hours, 2),
            "total_logged_hours": round(total_logged_hours, 2),
            "total_external_used_hours": round(total_external_used_hours, 2),
            "available_hours_display": self._format_hours(total_available_hours),
            "planned_hours_display": self._format_hours(total_planned_hours),
            "logged_hours_display": self._format_hours(total_logged_hours),
            "external_used_hours_display": self._format_hours(total_external_used_hours),
            "pool_stats": pool_stats,
        }

    def _calculate_pool_stats(
        self,
        creatives: List[Dict[str, Any]],
        summaries: Dict[int, Any],
        planned_hours: Dict[int, float],
        logged_hours: Dict[int, float],
    ) -> List[Dict[str, Any]]:
        """Calculate utilization statistics for each pool."""
        pool_stats = []

        for pool in POOL_DEFINITIONS:
            pool_tag = pool["tag"]

            # Filter creatives by pool tag
            pool_creatives = [
                creative for creative in creatives
                if self._match_pool(creative.get("tags"), pool_tag)
            ]

            # Calculate pool totals
            total_creatives = len(pool_creatives)
            total_available_hours = 0.0
            total_planned_hours = 0.0
            total_logged_hours = 0.0

            for creative in pool_creatives:
                creative_id = creative.get("id")
                if isinstance(creative_id, int):
                    summary = summaries.get(creative_id)
                    if summary:
                        total_available_hours += summary.available_hours
                    total_planned_hours += planned_hours.get(creative_id, 0.0)
                    total_logged_hours += logged_hours.get(creative_id, 0.0)

            # Calculate utilization percentage
            utilization_percent = 0.0
            if total_available_hours > 0:
                utilization_percent = round((total_logged_hours / total_available_hours) * 100, 1)

            pool_stats.append({
                "slug": pool["slug"],
                "label": pool["label"],
                "total_creatives": total_creatives,
                "available_hours": round(total_available_hours, 2),
                "available_hours_display": self._format_hours(total_available_hours),
                "planned_hours": round(total_planned_hours, 2),
                "planned_hours_display": self._format_hours(total_planned_hours),
                "logged_hours": round(total_logged_hours, 2),
                "logged_hours_display": self._format_hours(total_logged_hours),
                "utilization_percent": utilization_percent,
            })

        return pool_stats

    def _match_pool(self, tags: List[str] | None, target: str) -> bool:
        """Check if creative tags match the target pool tag."""
        if not tags:
            return False
        normalized = [str(tag).lower() for tag in tags if isinstance(tag, str)]
        return any(target in tag for tag in normalized)

    def _format_hours(self, value: float) -> str:
        """Format hours as 'XXXh' or 'XXXh YYm'."""
        total_minutes = int(round(value * 60))
        hours, minutes = divmod(total_minutes, 60)
        if minutes == 0:
            return f"{hours}h"
        return f"{hours}h {minutes:02d}m"
