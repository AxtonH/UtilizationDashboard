"""External / Strategy& hours totals and breakdowns."""
from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple
import re
from ...integrations.odoo_client import OdooClient


class ExternalHoursMixin:
    """External / Strategy& hours totals and breakdowns."""

    def _is_strategy_and(self, project_name: Optional[str], tags: Optional[List[str]]) -> bool:
        """Check if a project belongs to Strategy& (to exclude from external hours calculations).
        
        Args:
            project_name: Name of the project
            tags: List of tags associated with the project
            
        Returns:
            True if the project belongs to Strategy&, False otherwise
        """
        if project_name:
            project_name_lower = str(project_name).lower()
            if "strategy&" in project_name_lower:
                return True
        
        if tags:
            for tag in tags:
                if isinstance(tag, str):
                    tag_lower = tag.lower()
                    if "strategy&" in tag_lower:
                        return True
        
        return False

    def get_external_hours_totals(
        self,
        month_start: date,
        month_end: date,
        subscriptions: Optional[List[Dict[str, Any]]] = None,
        sales_orders: Optional[List[Dict[str, Any]]] = None,
        *,
        previous_period: Optional[Tuple[date, date]] = None,
        previous_subscriptions: Optional[List[Dict[str, Any]]] = None,
        previous_sales_orders: Optional[List[Dict[str, Any]]] = None,
        manual_strategy_sold: float = 0.0,
        manual_strategy_used: float = 0.0,
        previous_manual_strategy_sold: float = 0.0,
        previous_manual_strategy_used: float = 0.0,
    ) -> Dict[str, Any]:
        """Calculate total external hours sold and used for the selected period.
        
        External Hours Sold = subscription ext. sold + sales-order hours + manual Strategy& (Supabase)
        External Hours Used = subscription ext. used + sales-order hours + manual Strategy& (Supabase)
        
        Odoo Strategy& projects remain excluded from subscription/order sums; use Settings → Strategy& hours.
        
        Args:
            month_start: First day of the month
            month_end: Last day of the month
            
        Returns:
            Dictionary with:
            - external_hours_sold: Total external hours sold
            - external_hours_used: Total external hours used
            - strategy_and_external_hours_sold: Manual Strategy& sold included in the total
            - strategy_and_external_hours_used: Manual Strategy& used included in the total
            - comparison_sold: Month-over-month comparison for sold hours
            - comparison_used: Month-over-month comparison for used hours
        """
        # Get subscriptions and sales orders for current month (reuse if provided)
        if subscriptions is None:
            subscriptions = self.get_subscriptions_for_month(month_start, month_end)
        if sales_orders is None:
            sales_orders = self._get_sales_order_details_for_external_hours(month_start, month_end)
        
        # Calculate totals from subscriptions
        subscription_sold_total = 0.0
        subscription_used_total = 0.0
        
        for subscription in subscriptions:
            # Skip Strategy& projects
            project_name = subscription.get("project_name")
            tags = subscription.get("tags", [])
            if self._is_strategy_and(project_name, tags):
                continue
            
            # Sum external_sold_hours (x_studio_external_billable_hours_monthly)
            external_sold = subscription.get("external_sold_hours", 0.0)
            if external_sold:
                try:
                    subscription_sold_total += float(external_sold)
                except (ValueError, TypeError):
                    pass
            
            # Sum external_hours_used
            external_used = subscription.get("external_hours_used", 0.0)
            if external_used:
                try:
                    subscription_used_total += float(external_used)
                except (ValueError, TypeError):
                    pass
        
        # Calculate totals from sales orders
        sales_order_total = 0.0
        
        for order in sales_orders:
            # Skip Strategy& projects
            project_name = order.get("project_name")
            tags = order.get("tags", [])
            if self._is_strategy_and(project_name, tags):
                continue
            
            external_hours = order.get("external_hours", 0.0)
            if external_hours:
                try:
                    sales_order_total += float(external_hours)
                except (ValueError, TypeError):
                    pass
        
        ms_sold = float(manual_strategy_sold) if manual_strategy_sold else 0.0
        ms_used = float(manual_strategy_used) if manual_strategy_used else 0.0

        # Calculate combined totals (Odoo sums exclude Strategy&; manual rows add it back)
        total_sold = subscription_sold_total + sales_order_total + ms_sold
        total_used = subscription_used_total + sales_order_total + ms_used
        
        # Previous period for comparison (defaults to previous calendar month)
        if previous_period:
            prev_start, prev_end = previous_period
        else:
            previous_bounds = self._previous_month_bounds(month_start)
            if previous_bounds:
                prev_start, prev_end = previous_bounds
            else:
                prev_start = prev_end = None
        comparison_sold = None
        comparison_used = None
        
        if prev_start and prev_end:
            # Reuse prefetched previous-period data when the caller provides it
            # (the /api/sales route fetches both concurrently at request start).
            prev_subscriptions = (
                previous_subscriptions
                if previous_subscriptions is not None
                else self.get_subscriptions_for_month(prev_start, prev_end)
            )
            prev_sales_orders = (
                previous_sales_orders
                if previous_sales_orders is not None
                else self._get_sales_order_details_for_external_hours(prev_start, prev_end)
            )
            
            # Calculate previous month totals
            prev_subscription_sold = 0.0
            prev_subscription_used = 0.0
            
            for subscription in prev_subscriptions:
                # Skip Strategy& projects
                project_name = subscription.get("project_name")
                tags = subscription.get("tags", [])
                if self._is_strategy_and(project_name, tags):
                    continue
                
                external_sold = subscription.get("external_sold_hours", 0.0)
                if external_sold:
                    try:
                        prev_subscription_sold += float(external_sold)
                    except (ValueError, TypeError):
                        pass
                
                external_used = subscription.get("external_hours_used", 0.0)
                if external_used:
                    try:
                        prev_subscription_used += float(external_used)
                    except (ValueError, TypeError):
                        pass
            
            prev_sales_order_total = 0.0
            for order in prev_sales_orders:
                # Skip Strategy& projects
                project_name = order.get("project_name")
                tags = order.get("tags", [])
                if self._is_strategy_and(project_name, tags):
                    continue
                
                external_hours = order.get("external_hours", 0.0)
                if external_hours:
                    try:
                        prev_sales_order_total += float(external_hours)
                    except (ValueError, TypeError):
                        pass
            
            pms_sold = float(previous_manual_strategy_sold) if previous_manual_strategy_sold else 0.0
            pms_used = float(previous_manual_strategy_used) if previous_manual_strategy_used else 0.0
            prev_total_sold = prev_subscription_sold + prev_sales_order_total + pms_sold
            prev_total_used = prev_subscription_used + prev_sales_order_total + pms_used
            
            # Calculate comparisons
            comparison_sold = self._calculate_comparison(total_sold, prev_total_sold)
            comparison_used = self._calculate_comparison(total_used, prev_total_used)
        
        return {
            "external_hours_sold": total_sold,
            "external_hours_used": total_used,
            "strategy_and_external_hours_sold": ms_sold,
            "strategy_and_external_hours_used": ms_used,
            "comparison_sold": comparison_sold,
            "comparison_used": comparison_used,
        }

    def get_external_hours_by_agreement_type(
        self,
        month_start: date,
        month_end: date,
        subscriptions: Optional[List[Dict[str, Any]]] = None,
        sales_orders: Optional[List[Dict[str, Any]]] = None,
        *,
        manual_strategy_sold: float = 0.0,
        manual_strategy_used: float = 0.0,
    ) -> Dict[str, Dict[str, float]]:
        """Calculate external hours sold and used grouped by agreement type.
        
        Manual Strategy& totals (Supabase) appear under the ``Strategy&`` key in sold/used.
        
        Args:
            month_start: First day of the month
            month_end: Last day of the month
            
        Returns:
            Dictionary with structure:
            {
                "sold": {
                    "Retainer": float,
                    "Framework": float,
                    "Ad Hoc": float,
                    "Unknown": float,
                    "Strategy&": float,
                },
                "used": {
                    "Retainer": float,
                    "Framework": float,
                    "Ad Hoc": float,
                    "Unknown": float,
                    "Strategy&": float,
                }
            }
        """
        # Get subscriptions and sales orders for current month (reuse if provided)
        if subscriptions is None:
            subscriptions = self.get_subscriptions_for_month(month_start, month_end)
        if sales_orders is None:
            sales_orders = self._get_sales_order_details_for_external_hours(month_start, month_end)
        
        # Initialize totals by agreement type
        sold_totals = {
            "Retainer": 0.0,
            "Framework": 0.0,
            "Ad Hoc": 0.0,
            "Unknown": 0.0,
            "Strategy&": 0.0,
        }
        used_totals = {
            "Retainer": 0.0,
            "Framework": 0.0,
            "Ad Hoc": 0.0,
            "Unknown": 0.0,
            "Strategy&": 0.0,
        }
        
        # Process subscriptions
        for subscription in subscriptions:
            # Skip Strategy& projects
            project_name = subscription.get("project_name")
            tags = subscription.get("tags", [])
            if self._is_strategy_and(project_name, tags):
                continue
            
            agreement_type = subscription.get("agreement_type", "Unknown")
            category = self._categorize_agreement_type(agreement_type, tags)
            
            # Add external sold hours
            external_sold = subscription.get("external_sold_hours", 0.0)
            if external_sold:
                try:
                    sold_totals[category] += float(external_sold)
                except (ValueError, TypeError):
                    pass
            
            # Add external hours used
            external_used = subscription.get("external_hours_used", 0.0)
            if external_used:
                try:
                    used_totals[category] += float(external_used)
                except (ValueError, TypeError):
                    pass
        
        # Process sales orders
        for order in sales_orders:
            # Skip Strategy& projects
            project_name = order.get("project_name")
            tags = order.get("tags", [])
            if self._is_strategy_and(project_name, tags):
                continue
            
            agreement_type = order.get("agreement_type", "Unknown")
            category = self._categorize_agreement_type(agreement_type, tags)
            
            # Add external hours (same value for both sold and used for sales orders)
            external_hours = order.get("external_hours", 0.0)
            if external_hours:
                try:
                    hours_value = float(external_hours)
                    sold_totals[category] += hours_value
                    used_totals[category] += hours_value
                except (ValueError, TypeError):
                    pass
        
        ms_sold = float(manual_strategy_sold) if manual_strategy_sold else 0.0
        ms_used = float(manual_strategy_used) if manual_strategy_used else 0.0
        sold_totals["Strategy&"] += ms_sold
        used_totals["Strategy&"] += ms_used
        
        return {
            "sold": sold_totals,
            "used": used_totals,
        }

    def _calculate_external_hours_used(
        self,
        project_ids: Iterable[int],
        month_start: date,
        month_end: date,
        include_breakdown: bool = False,
    ) -> Dict[int, Any]:
        """Calculate external hours used for projects based on parent task Request Receipt Date & Time.
        
        For each project:
        1. Get all tasks under that project (including request receipt datetime)
        2. Get all subtasks for each task
        3. For subtasks where sale_line_id is False and the parent task's
           x_studio_request_receipt_date_time is within the month, sum x_studio_external_hours_2
        
        Args:
            project_ids: List of project IDs
            month_start: First day of the month
            month_end: Last day of the month
            
        Returns:
            Dict mapping project_id to total external hours used, or if include_breakdown is True:
            {
                "totals": {project_id: hours, ...},
                "breakdowns": {project_id: [{title, hours, hours_display, created_on, created_on_display}, ...], ...}
            }
        """
        ids = [pid for pid in project_ids if isinstance(pid, int)]
        if not ids:
            return {}
        
        # Get all tasks for these projects
        domain = [
            ("project_id", "in", ids),
        ]
        fields = ["id", "project_id", "child_ids", "x_studio_request_receipt_date_time"]
        
        try:
            # Large chunk: thousands of parent tasks; round-trips are
            # latency-bound (~0.2s each), so 200/page cost ~5s per call here.
            tasks = self.odoo_client.search_read_all(
                model="project.task",
                domain=domain,
                fields=fields,
                chunk_size=2000,
            )
        except Exception as e:
            print(f"Error fetching tasks for external hours calculation: {e}")
            return {}
        
        if not tasks:
            return {}
        
        # Collect all subtask IDs and parent request datetimes
        subtask_ids = []
        task_project_map = {}  # Map task_id to project_id
        task_request_datetime_map = {}  # Map task_id to request receipt datetime
        
        for task in tasks:
            task_id = task.get("id")
            if not isinstance(task_id, int):
                continue
                
            project_field = task.get("project_id")
            if isinstance(project_field, (list, tuple)) and len(project_field) >= 1:
                project_id = project_field[0]
                if isinstance(project_id, int):
                    task_project_map[task_id] = project_id

            # Store Request Receipt Date & Time for month filtering
            request_receipt = self._parse_odoo_datetime(task.get("x_studio_request_receipt_date_time"))
            if request_receipt:
                task_request_datetime_map[task_id] = request_receipt
            
            child_ids = task.get("child_ids") or []
            for child_id in child_ids:
                if isinstance(child_id, int):
                    subtask_ids.append(child_id)
        
        if not subtask_ids:
            return {}
        
        # Fetch subtasks with external hours
        try:
            subtask_fields = ["id", "x_studio_external_hours_2", "parent_id", "sale_line_id"]
            if include_breakdown:
                subtask_fields.extend(["name", "create_date"])
            subtasks = self.odoo_client.read(
                "project.task",
                subtask_ids,
                subtask_fields
            )
        except Exception as e:
            print(f"Error fetching subtasks for external hours calculation: {e}")
            return {}
        
        # Calculate totals per project
        project_totals: Dict[int, float] = {}
        project_breakdowns: Dict[int, List[Dict[str, Any]]] = {} if include_breakdown else {}
        
        for subtask in subtasks:
            # Get project_id from parent task
            parent_field = subtask.get("parent_id")
            if not isinstance(parent_field, (list, tuple)) or len(parent_field) < 1:
                continue
            
            parent_id = parent_field[0]
            if not isinstance(parent_id, int):
                continue
            
            project_id = task_project_map.get(parent_id)
            if not project_id:
                continue
            
            # Only include subtasks where sale_line_id is False (empty/null)
            sale_line_id = subtask.get("sale_line_id")
            if sale_line_id:  # If sale_line_id has a value, skip this subtask
                continue

            # Check if parent task's Request Receipt Date & Time is within the month
            parent_request_dt = task_request_datetime_map.get(parent_id)
            if not parent_request_dt:
                continue

            start_dt = datetime.combine(month_start, datetime.min.time())
            # include end date inclusive by moving to next day exclusive
            end_dt = datetime.combine(month_end + timedelta(days=1), datetime.min.time())

            if parent_request_dt < start_dt or parent_request_dt >= end_dt:
                continue
            
            # Add external hours
            external_hours = subtask.get("x_studio_external_hours_2")
            if external_hours:
                try:
                    hours_value = float(external_hours)
                    if hours_value > 0:
                        if project_id not in project_totals:
                            project_totals[project_id] = 0.0
                        project_totals[project_id] += hours_value

                        if include_breakdown:
                            subtask_id = subtask.get("id")
                            name_raw = subtask.get("name")
                            subtask_title = self._safe_str(name_raw, default=f"Subtask {subtask_id}" if subtask_id else "Subtask")
                            created_dt = self._parse_odoo_datetime(subtask.get("create_date"))
                            created_display = created_dt.strftime("%d %b %Y %H:%M") if isinstance(created_dt, datetime) else None
                            created_iso = created_dt.isoformat() if isinstance(created_dt, datetime) else None

                            project_breakdowns.setdefault(project_id, []).append(
                                {
                                    "title": subtask_title,
                                    "hours": hours_value,
                                    "hours_display": self._format_hours_minutes(hours_value),
                                    "created_on": created_iso,
                                    "created_on_display": created_display,
                                }
                            )
                except (ValueError, TypeError):
                    pass
        
        if include_breakdown:
            return {
                "totals": project_totals,
                "breakdowns": project_breakdowns,
            }
        return project_totals
