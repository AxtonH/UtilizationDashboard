"""Service for calculating month-over-month comparisons for dashboard metrics."""
from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from ..integrations.odoo_client import OdooClient
from .availability_service import AvailabilityService
from .employee_service import EmployeeService
from .planning_service import PlanningService
from .timesheet_service import TimesheetService


class ComparisonService:
    """Calculate month-over-month comparisons for utilization metrics."""

    def __init__(
        self,
        employee_service: EmployeeService,
        availability_service: AvailabilityService,
        planning_service: PlanningService,
        timesheet_service: TimesheetService,
    ):
        self.employee_service = employee_service
        self.availability_service = availability_service
        self.planning_service = planning_service
        self.timesheet_service = timesheet_service

    def calculate_previous_month_aggregates(
        self, current_month: date, creatives: Optional[List[Dict[str, object]]] = None
    ) -> Optional[Dict[str, Any]]:
        """Calculate aggregates for the previous month.
        
        Args:
            current_month: The current month being viewed
            creatives: Optional pre-fetched list of creatives. If None, will fetch from Odoo.
            
        Returns:
            Dictionary with aggregates for previous month, or None if current_month is January 2025
        """
        # Don't compare if we're viewing January 2025 (the start month)
        if current_month.year == 2025 and current_month.month == 1:
            return None
        
        # Calculate previous month
        if current_month.month == 1:
            previous_month = date(current_month.year - 1, 12, 1)
        else:
            previous_month = date(current_month.year, current_month.month - 1, 1)
        
        # Calculate month bounds using calendar module
        _, last_day = monthrange(previous_month.year, previous_month.month)
        previous_month_end = previous_month.replace(day=last_day)
        
        # Use provided creatives or fetch from Odoo
        if creatives is None:
            creatives = self.employee_service.get_creatives()
        
        # Calculate aggregates for previous month
        summaries = self.availability_service.calculate_monthly_availability(
            creatives, previous_month, previous_month_end
        )
        planned_hours = self.planning_service.planned_hours_for_month(
            creatives, previous_month, previous_month_end
        )
        logged_hours = self.timesheet_service.logged_hours_for_month(
            creatives, previous_month, previous_month_end
        )
        
        # Use the first day of the previous month for market filtering (same as dashboard)
        target_month = previous_month.replace(day=1)
        
        # Import the market filtering function here to avoid circular import issues
        try:
            from ..routes.creatives import _get_creative_market_for_month
        except ImportError:
            # If import fails, fall back to basic date checking
            _get_creative_market_for_month = None
        
        # Aggregate totals - only include creatives with valid market dates for previous month
        totals = {"planned": 0.0, "logged": 0.0, "available": 0.0}
        for creative in creatives:
            creative_id = creative.get("id")
            if not isinstance(creative_id, int):
                continue
            
            # Filter out creatives without valid market dates for the previous month
            # This excludes creative directors and others without start/end dates
            # (same filtering logic as the dashboard)
            if _get_creative_market_for_month is not None:
                market_result = _get_creative_market_for_month(creative, target_month)
                if market_result is None:
                    # Creative doesn't have valid market dates for the previous month, skip
                    continue
                market_slug, _ = market_result
                if not market_slug:
                    # Creative has no valid market slug, skip
                    continue
            else:
                # Fallback: check if creative has at least one valid start date
                # If all start dates are None, exclude the creative
                current_start = creative.get("current_market_start")
                previous_start_1 = creative.get("previous_market_1_start")
                previous_start_2 = creative.get("previous_market_2_start")
                previous_start_3 = creative.get("previous_market_3_start")
                
                if not any([current_start, previous_start_1, previous_start_2, previous_start_3]):
                    # Creative has no valid market start dates, skip (e.g., creative directors)
                    continue
            
            summary = summaries.get(creative_id)
            if summary:
                totals["available"] += float(summary.available_hours)
            totals["planned"] += float(planned_hours.get(creative_id, 0.0))
            totals["logged"] += float(logged_hours.get(creative_id, 0.0))
        
        return totals

    def calculate_comparison(
        self, current: Dict[str, float], previous: Optional[Dict[str, float]]
    ) -> Dict[str, Any]:
        """Calculate percentage change between current and previous values.
        
        Args:
            current: Dictionary with current month values (planned, logged, available)
            previous: Dictionary with previous month values, or None
            
        Returns:
            Dictionary with comparison data including percentage changes
        """
        if previous is None:
            return {
                "available": {"value": current.get("available", 0.0), "change": None},
                "planned": {"value": current.get("planned", 0.0), "change": None},
                "logged": {"value": current.get("logged", 0.0), "change": None},
                "utilization": {"value": None, "change": None},
                "booking_capacity": {"value": None, "change": None},
            }
        
        def _calculate_percentage_change(current_val: float, previous_val: float) -> Optional[float]:
            """Calculate percentage change."""
            if previous_val == 0:
                return None if current_val == 0 else 100.0
            return ((current_val - previous_val) / previous_val) * 100.0
        
        # Calculate utilization percentages
        current_available = current.get("available", 0.0)
        current_logged = current.get("logged", 0.0)
        current_planned = current.get("planned", 0.0)
        
        previous_available = previous.get("available", 0.0)
        previous_logged = previous.get("logged", 0.0)
        previous_planned = previous.get("planned", 0.0)
        
        # Current utilization (logged / available)
        current_utilization = (
            (current_logged / current_available * 100.0) if current_available > 0 else 0.0
        )
        previous_utilization = (
            (previous_logged / previous_available * 100.0) if previous_available > 0 else 0.0
        )
        
        # Current booking capacity (planned / available)
        current_booking = (
            (current_planned / current_available * 100.0) if current_available > 0 else 0.0
        )
        previous_booking = (
            (previous_planned / previous_available * 100.0) if previous_available > 0 else 0.0
        )
        
        return {
            "available": {
                "value": current_available,
                "change": _calculate_percentage_change(current_available, previous_available),
            },
            "planned": {
                "value": current_planned,
                "change": _calculate_percentage_change(current_planned, previous_planned),
            },
            "logged": {
                "value": current_logged,
                "change": _calculate_percentage_change(current_logged, previous_logged),
            },
            "utilization": {
                "value": current_utilization,
                "change": _calculate_percentage_change(current_utilization, previous_utilization),
            },
            "booking_capacity": {
                "value": current_booking,
                "change": _calculate_percentage_change(current_booking, previous_booking),
            },
        }

