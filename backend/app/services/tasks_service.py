"""Tasks statistics service for creative dashboard."""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, Optional

from .comparison_service import ComparisonService


class TasksService:
    """Calculate task statistics from sales orders and subscriptions."""

    def __init__(self, comparison_service: ComparisonService):
        self.comparison_service = comparison_service

    @classmethod
    def from_comparison_service(cls, comparison_service: ComparisonService) -> "TasksService":
        """Create a TasksService instance from a ComparisonService."""
        return cls(comparison_service)

    def _categorize_agreement_type(self, agreement_type: str) -> str:
        """Categorize agreement type into ad-hoc, framework, or retainer.
        
        Args:
            agreement_type: The agreement type string
            
        Returns:
            One of: 'ad-hoc', 'framework', 'retainer', or 'other'
        """
        if not agreement_type:
            return "other"
        
        agreement_lower = agreement_type.lower()
        
        # Check for retainer (subscriptions are retainers)
        if "retainer" in agreement_lower or "subscription" in agreement_lower:
            return "retainer"
        
        # Check for framework
        if "framework" in agreement_lower:
            return "framework"
        
        # Check for ad-hoc
        if "ad-hoc" in agreement_lower or "adhoc" in agreement_lower or "ad hoc" in agreement_lower:
            return "ad-hoc"
        
        # Default to other if not matched
        return "other"

    def calculate_tasks_statistics(
        self,
        client_sales_summary: Dict[str, Any],
        client_subscription_summary: Dict[str, Any],
        client_external_hours: list[Dict[str, Any]],
        client_subscription_hours: list[Dict[str, Any]],
        selected_month: date,
        available_creatives: int,
        external_hours_service: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Calculate task statistics including totals, categories, comparison, and average.
        
        Args:
            client_sales_summary: Summary from external hours (contains total_invoices)
            client_subscription_summary: Summary from subscriptions (contains total_parent_tasks)
            client_external_hours: List of markets with projects and sales orders
            client_subscription_hours: List of markets with subscriptions
            selected_month: The month being viewed
            available_creatives: Number of available creatives
            
        Returns:
            Dictionary with task statistics
        """
        # Get total tasks
        total_invoices = client_sales_summary.get("total_invoices", 0) or 0
        total_parent_tasks = client_subscription_summary.get("total_parent_tasks", 0) or 0
        total_tasks = total_invoices + total_parent_tasks
        
        # Categorize tasks
        adhoc_count = 0
        framework_count = 0
        retainer_count = 0
        
        # Count from sales orders (external hours)
        for market in client_external_hours or []:
            for project in market.get("projects", []):
                agreement_type = project.get("agreement_type", "")
                category = self._categorize_agreement_type(agreement_type)
                # Each sales order counts as a task
                order_count = len(project.get("sales_orders", []))
                if category == "ad-hoc":
                    adhoc_count += order_count
                elif category == "framework":
                    framework_count += order_count
                elif category == "retainer":
                    retainer_count += order_count
        
        # Count from subscriptions (parent tasks are retainers)
        retainer_count += total_parent_tasks
        
        # Calculate average tasks per creator
        avg_tasks_per_creator = (
            round(total_tasks / available_creatives, 2) if available_creatives > 0 else 0.0
        )
        
        result = {
            "total": total_tasks,
            "adhoc": adhoc_count,
            "framework": framework_count,
            "retainer": retainer_count,
            "average_per_creator": avg_tasks_per_creator,
        }
        
        # Add comparison with previous month
        if external_hours_service:
            try:
                previous_month = self._get_previous_month(selected_month)
                if previous_month:
                    previous_stats = self.calculate_previous_month_tasks(
                        previous_month,
                        external_hours_service,
                    )
                    if previous_stats:
                        comparison = self._calculate_comparison(total_tasks, previous_stats.get("total", 0))
                        result["comparison"] = comparison
                        result["previous_total"] = previous_stats.get("total", 0)
            except Exception:
                pass
        
        return result

    def _get_previous_month(self, current_month: date) -> Optional[date]:
        """Get the previous month date."""
        if current_month.month == 1:
            return date(current_month.year - 1, 12, 1)
        return date(current_month.year, current_month.month - 1, 1)

    def calculate_previous_month_tasks(
        self,
        previous_month: date,
        external_hours_service: Any,
    ) -> Optional[Dict[str, Any]]:
        """Calculate tasks for previous month.
        
        Args:
            previous_month: The previous month date
            external_hours_service: ExternalHoursService instance to fetch data
            
        Returns:
            Dictionary with previous month task statistics or None if unavailable
        """
        try:
            from calendar import monthrange
            from datetime import datetime, timedelta
            
            prev_month_start = date(previous_month.year, previous_month.month, 1)
            _, last_day = monthrange(prev_month_start.year, prev_month_start.month)
            prev_month_end = date(prev_month_start.year, prev_month_start.month, last_day)
            
            # Fetch previous month data
            prev_external_data = external_hours_service.external_hours_for_month(prev_month_start, prev_month_end)
            prev_subscription_data = external_hours_service.subscription_hours_for_month(prev_month_start, prev_month_end)
            
            prev_total_invoices = prev_external_data.get("summary", {}).get("total_invoices", 0) or 0
            prev_total_parent_tasks = prev_subscription_data.get("summary", {}).get("total_parent_tasks", 0) or 0
            prev_total_tasks = prev_total_invoices + prev_total_parent_tasks
            
            return {"total": prev_total_tasks}
        except Exception:
            return None

    def _calculate_comparison(self, current: int, previous: int) -> Optional[Dict[str, Any]]:
        """Calculate comparison between current and previous month.
        
        Args:
            current: Current month value
            previous: Previous month value
            
        Returns:
            Dictionary with change_percentage and trend, or None if comparison not available
        """
        if previous == 0:
            if current > 0:
                return {"change_percentage": 100.0, "trend": "up"}
            return None
        
        change = ((current - previous) / previous) * 100
        trend = "up" if change >= 0 else "down"
        
        return {
            "change_percentage": abs(change),
            "trend": trend,
        }

