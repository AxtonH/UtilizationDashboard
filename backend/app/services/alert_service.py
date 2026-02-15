"""Alert service for detecting dashboard metric imbalances."""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from .sales_service import SalesService
from .comparison_service import ComparisonService


class AlertService:
    """Service for detecting and reporting dashboard alerts."""

    def __init__(
        self,
        sales_service: SalesService,
        employee_service: Optional[Any] = None,
        availability_service: Optional[Any] = None,
        planning_service: Optional[Any] = None,
        timesheet_service: Optional[Any] = None,
        comparison_service: Optional[ComparisonService] = None,
    ):
        """Initialize the alert service.
        
        Args:
            sales_service: SalesService instance for fetching sales order data
            employee_service: EmployeeService instance for fetching creatives (optional)
            availability_service: AvailabilityService instance for calculating availability (optional)
            planning_service: PlanningService instance for calculating planned hours (optional)
            timesheet_service: TimesheetService instance for calculating logged hours (optional)
            comparison_service: ComparisonService instance for calculating trends (optional)
        """
        self.sales_service = sales_service
        self.employee_service = employee_service
        self.availability_service = availability_service
        self.planning_service = planning_service
        self.timesheet_service = timesheet_service
        self.comparison_service = comparison_service

    def detect_internal_external_imbalance(
        self,
        month_start: date,
        month_end: date,
    ) -> Dict[str, Any]:
        """Detect projects with internal hours greater than external hours.
        
        Groups sales orders by project and checks if internal hours > external hours.
        
        Args:
            month_start: First day of the month
            month_end: Last day of the month
            
        Returns:
            Dictionary with:
            - count: Number of imbalanced projects
            - projects: List of project details with imbalance information
        """
        # Get sales orders for the month
        sales_orders = self.sales_service._get_sales_order_details(month_start, month_end)
        
        if not sales_orders:
            return {
                "count": 0,
                "projects": [],
            }
        
        # Group orders by project and aggregate hours
        project_hours: Dict[str, Dict[str, Any]] = {}
        
        for order in sales_orders:
            project_name = order.get("project_name", "Unassigned Project")
            
            # Skip unassigned projects
            if project_name == "Unassigned Project":
                continue
            
            internal_hours = order.get("internal_hours", 0.0)
            external_hours = order.get("external_hours", 0.0)
            
            # Convert to float if needed
            try:
                internal_hours = float(internal_hours or 0.0)
                external_hours = float(external_hours or 0.0)
            except (ValueError, TypeError):
                internal_hours = 0.0
                external_hours = 0.0
            
            # Initialize project entry if not exists
            if project_name not in project_hours:
                project_hours[project_name] = {
                    "project_name": project_name,
                    "market": order.get("market", "Unassigned Market"),
                    "agreement_type": order.get("agreement_type", "Unknown"),
                    "internal_hours": 0.0,
                    "external_hours": 0.0,
                    "imbalance_degree": 0.0,
                }
            
            # Aggregate hours
            project_hours[project_name]["internal_hours"] += internal_hours
            project_hours[project_name]["external_hours"] += external_hours
        
        # Calculate imbalance degree and filter projects where internal > external
        imbalanced_projects = []
        for project_name, project_data in project_hours.items():
            internal = project_data["internal_hours"]
            external = project_data["external_hours"]
            imbalance_degree = internal - external
            
            # Only include projects where internal hours > external hours
            if internal > external:
                project_data["imbalance_degree"] = imbalance_degree
                imbalanced_projects.append(project_data)
        
        # Sort by imbalance degree (descending)
        imbalanced_projects.sort(key=lambda x: x["imbalance_degree"], reverse=True)
        
        return {
            "count": len(imbalanced_projects),
            "projects": imbalanced_projects,
        }

    def detect_overbooking(
        self,
        month_start: date,
        month_end: date,
    ) -> Dict[str, Any]:
        """Detect creatives with planned utilization above 110%.
        
        Args:
            month_start: First day of the month
            month_end: Last day of the month
            
        Returns:
            Dictionary with:
            - count: Number of overbooked creatives
            - creatives: List of creative details with overbooking information
        """
        if not all([self.employee_service, self.availability_service, self.planning_service]):
            return {
                "count": 0,
                "creatives": [],
            }
        
        # Get all creatives
        creatives = self.employee_service.get_creatives()
        
        if not creatives:
            return {
                "count": 0,
                "creatives": [],
            }
        
        # Get availability summaries
        summaries = self.availability_service.calculate_monthly_availability(
            creatives, month_start, month_end
        )
        
        # Get planned hours
        planned_hours = self.planning_service.planned_hours_for_month(
            creatives, month_start, month_end
        )
        
        # Calculate utilization and find overbooked creatives
        overbooked_creatives = []
        
        # Use the first day of the month for market filtering (same as dashboard)
        target_month = month_start.replace(day=1)
        
        # Import the market filtering function here to avoid circular import issues
        try:
            from ..routes.creatives import _get_creative_market_for_month
        except ImportError:
            # If import fails, fall back to basic date checking
            _get_creative_market_for_month = None
        
        for creative in creatives:
            creative_id = creative.get("id")
            if not isinstance(creative_id, int):
                continue
            
            # Filter out creatives without valid market dates for this month
            # This excludes creative directors and others without start/end dates
            # (same filtering logic as the dashboard)
            if _get_creative_market_for_month is not None:
                market_result = _get_creative_market_for_month(creative, target_month)
                if market_result is None:
                    # Creative doesn't have valid market dates for this month, skip
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
            
            # Get availability summary
            summary = summaries.get(creative_id)
            if not summary:
                continue
            
            available_hours = summary.available_hours
            planned = planned_hours.get(creative_id, 0.0)
            
            # Calculate planned utilization
            if available_hours > 0:
                planned_utilization = (planned / available_hours) * 100.0
            else:
                # If no available hours, skip (can't calculate utilization)
                continue
            
            # Check if overbooked (planned utilization > 110%)
            if planned_utilization > 110.0:
                overbooked_creatives.append({
                    "creative_name": creative.get("name", "Unknown"),
                    "planned_hours": round(planned, 2),
                    "available_hours": round(available_hours, 2),
                    "planned_utilization": round(planned_utilization, 1),
                    "overbooking_degree": round(planned_utilization - 100.0, 1),  # How much over 100%
                })
        
        # Sort by planned utilization (descending)
        overbooked_creatives.sort(key=lambda x: x["planned_utilization"], reverse=True)
        
        return {
            "count": len(overbooked_creatives),
            "creatives": overbooked_creatives,
        }

    def detect_underbooking(
        self,
        month_start: date,
        month_end: date,
    ) -> Dict[str, Any]:
        """Detect creatives with planned utilization below 70%.
        
        Args:
            month_start: First day of the month
            month_end: Last day of the month
            
        Returns:
            Dictionary with:
            - count: Number of underbooked creatives
            - creatives: List of creative details with underbooking information
        """
        if not all([self.employee_service, self.availability_service, self.planning_service]):
            return {
                "count": 0,
                "creatives": [],
            }
        
        # Get all creatives
        creatives = self.employee_service.get_creatives()
        
        if not creatives:
            return {
                "count": 0,
                "creatives": [],
            }
        
        # Get availability summaries
        summaries = self.availability_service.calculate_monthly_availability(
            creatives, month_start, month_end
        )
        
        # Get planned hours
        planned_hours = self.planning_service.planned_hours_for_month(
            creatives, month_start, month_end
        )
        
        # Calculate utilization and find underbooked creatives
        underbooked_creatives = []
        
        # Use the first day of the month for market filtering (same as dashboard)
        target_month = month_start.replace(day=1)
        
        # Import the market filtering function here to avoid circular import issues
        try:
            from ..routes.creatives import _get_creative_market_for_month
        except ImportError:
            # If import fails, fall back to basic date checking
            _get_creative_market_for_month = None
        
        for creative in creatives:
            creative_id = creative.get("id")
            if not isinstance(creative_id, int):
                continue
            
            # Filter out creatives without valid market dates for this month
            # This excludes creative directors and others without start/end dates
            # (same filtering logic as the dashboard)
            if _get_creative_market_for_month is not None:
                market_result = _get_creative_market_for_month(creative, target_month)
                if market_result is None:
                    # Creative doesn't have valid market dates for this month, skip
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
            
            # Get availability summary
            summary = summaries.get(creative_id)
            if not summary:
                continue
            
            available_hours = summary.available_hours
            planned = planned_hours.get(creative_id, 0.0)
            
            # Calculate planned utilization
            if available_hours > 0:
                planned_utilization = (planned / available_hours) * 100.0
            else:
                # If no available hours, skip (can't calculate utilization)
                continue
            
            # Check if underbooked (planned utilization < 70%)
            if planned_utilization < 70.0:
                underbooked_creatives.append({
                    "creative_name": creative.get("name", "Unknown"),
                    "planned_hours": round(planned, 2),
                    "available_hours": round(available_hours, 2),
                    "planned_utilization": round(planned_utilization, 1),
                    "underbooking_degree": round(70.0 - planned_utilization, 1),  # How much below 70%
                })
        
        # Sort by planned utilization (ascending - lowest first)
        underbooked_creatives.sort(key=lambda x: x["planned_utilization"])
        
        return {
            "count": len(underbooked_creatives),
            "creatives": underbooked_creatives,
        }

    def detect_declining_utilization_trend(
        self,
        month_start: date,
        month_end: date,
    ) -> Optional[Dict[str, Any]]:
        """Detect if utilization is declining compared to previous month.
        
        Args:
            month_start: First day of the month
            month_end: Last day of the month
            
        Returns:
            Dictionary with declining utilization trend data, or None if not declining
        """
        if not all([self.employee_service, self.availability_service, self.planning_service, self.timesheet_service, self.comparison_service]):
            return None
        
        # Get all creatives
        creatives = self.employee_service.get_creatives()
        
        if not creatives:
            return None
        
        # Calculate current month aggregates
        current_summaries = self.availability_service.calculate_monthly_availability(
            creatives, month_start, month_end
        )
        current_planned_hours = self.planning_service.planned_hours_for_month(
            creatives, month_start, month_end
        )
        current_logged_hours = self.timesheet_service.logged_hours_for_month(
            creatives, month_start, month_end
        )
        
        # Use the first day of the month for market filtering (same as dashboard)
        target_month = month_start.replace(day=1)
        
        # Import the market filtering function here to avoid circular import issues
        try:
            from ..routes.creatives import _get_creative_market_for_month
        except ImportError:
            # If import fails, fall back to basic date checking
            _get_creative_market_for_month = None
        
        # Aggregate current month totals - only include creatives with valid market dates
        current_totals = {"planned": 0.0, "logged": 0.0, "available": 0.0}
        for creative in creatives:
            creative_id = creative.get("id")
            if not isinstance(creative_id, int):
                continue
            
            # Filter out creatives without valid market dates for this month
            # This excludes creative directors and others without start/end dates
            # (same filtering logic as the dashboard)
            if _get_creative_market_for_month is not None:
                market_result = _get_creative_market_for_month(creative, target_month)
                if market_result is None:
                    # Creative doesn't have valid market dates for this month, skip
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
            
            summary = current_summaries.get(creative_id)
            if summary:
                current_totals["available"] += float(summary.available_hours)
            current_totals["planned"] += float(current_planned_hours.get(creative_id, 0.0))
            current_totals["logged"] += float(current_logged_hours.get(creative_id, 0.0))
        
        # Calculate previous month aggregates
        previous_aggregates = self.comparison_service.calculate_previous_month_aggregates(
            month_start, creatives
        )
        
        if previous_aggregates is None:
            # No previous month data available
            return None
        
        # Calculate comparison
        comparison = self.comparison_service.calculate_comparison(current_totals, previous_aggregates)
        
        # Check utilization change
        utilization_change = comparison.get("utilization", {}).get("change")
        current_utilization = comparison.get("utilization", {}).get("value")
        
        if utilization_change is None or current_utilization is None:
            return None
        
        # If utilization is declining (negative change), return alert data
        if utilization_change < 0:
            return {
                "current_utilization": round(current_utilization, 1),
                "decline_percentage": round(abs(utilization_change), 1),
            }
        
        return None

    def detect_subscription_hours_alert(
        self,
        month_start: date,
        month_end: date,
    ) -> Dict[str, Any]:
        """Detect subscriptions where external hours used > external hours sold.
        
        Args:
            month_start: First day of the month
            month_end: Last day of the month
            
        Returns:
            Dictionary with:
            - count: Number of subscriptions with overused hours
            - subscriptions: List of subscription details with overuse information
        """
        if not self.sales_service:
            return {
                "count": 0,
                "subscriptions": [],
            }
        
        # Get subscriptions for the month
        subscriptions = self.sales_service.get_subscriptions_for_month(month_start, month_end)
        
        if not subscriptions:
            return {
                "count": 0,
                "subscriptions": [],
            }
        
        # Find subscriptions where external_hours_used > external_sold_hours
        overused_subscriptions = []
        
        for subscription in subscriptions:
            external_sold = subscription.get("external_sold_hours", 0.0)
            external_used = subscription.get("external_hours_used", 0.0)
            
            # Convert to float if needed
            try:
                external_sold = float(external_sold or 0.0)
                external_used = float(external_used or 0.0)
            except (ValueError, TypeError):
                external_sold = 0.0
                external_used = 0.0
            
            # Check if used > sold
            if external_used > external_sold:
                overuse_amount = external_used - external_sold
                overuse_percentage = ((external_used - external_sold) / external_sold * 100.0) if external_sold > 0 else 0.0
                
                overused_subscriptions.append({
                    "customer_name": subscription.get("customer_name", "Unknown"),
                    "order_name": subscription.get("order_name", "Unknown"),
                    "project_name": subscription.get("project_name", "Unknown"),
                    "market": subscription.get("market", "Unknown"),
                    "agreement_type": subscription.get("agreement_type", "Unknown"),
                    "external_sold_hours": round(external_sold, 2),
                    "external_hours_used": round(external_used, 2),
                    "overuse_amount": round(overuse_amount, 2),
                    "overuse_percentage": round(overuse_percentage, 1),
                })
        
        # Sort by overuse amount (descending - highest overuse first)
        overused_subscriptions.sort(key=lambda x: x["overuse_amount"], reverse=True)
        
        return {
            "count": len(overused_subscriptions),
            "subscriptions": overused_subscriptions,
        }
