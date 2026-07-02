"""Subscription listing and statistics."""
from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple
import re
from ...integrations.odoo_client import OdooClient


class SubscriptionsMixin:
    """Subscription listing and statistics."""

    def get_subscriptions_for_month(
        self,
        month_start: date,
        month_end: date,
    ) -> List[Dict[str, Any]]:
        """Get active subscriptions for the selected month.
        
        A subscription is considered active if:
        - first_contract_date <= month_end
        - end_date >= month_start (or end_date is False/null for ongoing subscriptions)
        
        Args:
            month_start: First day of the month
            month_end: Last day of the month
            
        Returns:
            List of subscription dictionaries with:
            - customer_name: Customer name from partner_id
            - market: Market from project.project (x_studio_market_2)
            - external_sold_hours: x_studio_external_billable_hours_monthly
            - monthly_recurring_payment: recurring_monthly
            - order_id: Sale order ID
            - order_name: Sale order name/reference
            - project_id: Project ID
            - project_name: Project name
            - first_contract_date: First contract date
            - end_date: End date (or None if ongoing)
        """
        # Build domain filter for subscriptions
        # Subscriptions exist if: first_contract_date <= month_end AND (end_date >= month_start OR end_date is False/null)
        # and only if the order is confirmed (state = sale).
        domain = [
            "&", "&",
            ("state", "=", "sale"),
            ("first_contract_date", "<=", month_end.isoformat()),
            "|",
            ("end_date", "=", False),
            ("end_date", ">=", month_start.isoformat()),
        ]
        
        # Fetch subscription orders
        fields = [
            "id",
            "name",
            "partner_id",
            "project_id",
            "x_studio_external_billable_hours_monthly",
            "recurring_monthly",
            "first_contract_date",
            "start_date",
            "end_date",
        ]
        
        orders = self.odoo_client.search_read_all(
            model="sale.order",
            domain=domain,
            fields=fields,
        )
        
        if not orders:
            return []
        
        # Collect partner IDs and project IDs
        partner_ids = set()
        project_ids = set()
        for order in orders:
            partner_field = order.get("partner_id")
            if isinstance(partner_field, (list, tuple)) and len(partner_field) >= 1:
                partner_ids.add(partner_field[0])
            
            project_field = order.get("project_id")
            if isinstance(project_field, (list, tuple)) and len(project_field) >= 1:
                project_ids.add(project_field[0])
        
        # Fetch partner details
        partners = {}
        if partner_ids:
            partner_records = self.odoo_client.read(
                "res.partner",
                list(partner_ids),
                ["name"]
            )
            partners = {p["id"]: p.get("name", "Unknown Customer") for p in partner_records}
        
        # Fetch project details (for market)
        projects = self._fetch_projects(project_ids)
        
        # Calculate external hours used for each project
        external_hours_result = self._calculate_external_hours_used(
            project_ids,
            month_start,
            month_end,
            include_breakdown=True,
        )
        external_hours_used_map = (
            external_hours_result.get("totals", {})
            if isinstance(external_hours_result, dict)
            else external_hours_result
        )
        external_hours_breakdowns = (
            external_hours_result.get("breakdowns", {})
            if isinstance(external_hours_result, dict)
            else {}
        )
        
        # Build subscription list
        subscriptions = []
        for order in orders:
            order_id = order.get("id")
            order_name = order.get("name", "")
            
            # Get customer
            partner_field = order.get("partner_id")
            customer_name = "Unknown Customer"
            if isinstance(partner_field, (list, tuple)) and len(partner_field) >= 1:
                customer_name = partners.get(partner_field[0], "Unknown Customer")
            
            # Get market and agreement type from project
            project_field = order.get("project_id")
            market = "Unassigned Market"
            project_id = None
            project_name = "Unassigned Project"
            agreement_type = "Unknown"
            tags = []
            
            if isinstance(project_field, (list, tuple)) and len(project_field) >= 1:
                project_id = project_field[0]
                project = projects.get(project_id)
                if project:
                    market = self._market_label(project)
                    project_name = project.get("name", "Unassigned Project")
                    agreement_type = self._format_agreement_type(project)
                    tags = self._project_tags(project)
            
            # Get external sold hours
            external_hours = order.get("x_studio_external_billable_hours_monthly")
            external_sold_hours = 0.0
            if external_hours:
                try:
                    external_sold_hours = float(external_hours)
                except (ValueError, TypeError):
                    pass
            
            # Get monthly recurring payment
            recurring = order.get("recurring_monthly")
            monthly_recurring_payment = 0.0
            if recurring:
                try:
                    monthly_recurring_payment = float(recurring)
                except (ValueError, TypeError):
                    pass
            
            # Parse dates
            first_contract_date = self._parse_odoo_date(order.get("first_contract_date"))
            start_date_val = self._parse_odoo_date(order.get("start_date")) or first_contract_date
            end_date = self._parse_odoo_date(order.get("end_date"))
            is_churned = bool(end_date and end_date <= month_end)
            is_new_in_month = bool(start_date_val and month_start <= start_date_val <= month_end)
            
            # Get external hours used for this project
            external_hours_used = 0.0
            external_hours_breakdown: List[Dict[str, Any]] = []
            if project_id:
                external_hours_used = external_hours_used_map.get(project_id, 0.0)
                breakdown_entries = external_hours_breakdowns.get(project_id, [])
                if isinstance(breakdown_entries, list):
                    external_hours_breakdown = breakdown_entries
            
            subscriptions.append({
                "order_id": order_id,
                "order_name": order_name,
                "customer_name": customer_name,
                "market": market,
                "project_id": project_id,
                "project_name": project_name,
                "agreement_type": agreement_type,
                "tags": tags,
                "external_sold_hours": external_sold_hours,
                "external_sold_hours_display": f"{external_sold_hours:.1f}h" if external_sold_hours > 0 else "0h",
                "external_hours_used": external_hours_used,
                "external_hours_used_display": self._format_hours_minutes(external_hours_used),
                "external_hours_breakdown": external_hours_breakdown,
                "monthly_recurring_payment": monthly_recurring_payment,
                "monthly_recurring_payment_display": f"AED {monthly_recurring_payment:,.2f}" if monthly_recurring_payment > 0 else "AED 0.00",
                "first_contract_date": first_contract_date.isoformat() if first_contract_date else None,
                "start_date": start_date_val.isoformat() if start_date_val else None,
                "end_date": end_date.isoformat() if end_date else None,
                "is_ongoing": end_date is None,
                "is_churned": is_churned,
                "is_new_in_month": is_new_in_month,
            })
        
        # Sort by customer name, then by order name
        subscriptions.sort(key=lambda x: (x["customer_name"].lower(), x["order_name"]))
        
        return subscriptions

    def get_subscription_statistics(
        self,
        month_start: date,
        month_end: date,
        subscriptions: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Calculate subscription statistics for the selected month.
        
        Args:
            month_start: First day of the month
            month_end: Last day of the month
            
        Returns:
            Dictionary with:
            - active_count: Number of subscriptions that are not churned (based on end_date)
            - churned_count: Number of subscriptions where end_date is within the month or has passed
            - new_renew_count: Number of subscriptions where start_date is in the month
            - mrr: Total monthly recurring revenue (sum of recurring_monthly for active subscriptions only)
        """
        def _default_subscription_stats() -> Dict[str, Any]:
            return {
                "active_count": 0,
                "churned_count": 0,
                "new_renew_count": 0,
                "mrr": 0.0,
                "mrr_display": "AED 0.00",
                "active_order_names": [],
                "total_subscriptions": 0,
                "subscription_comparison": None,
            }

        def _compute_subscription_stats(start: date, end: date, prefetch: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
            if prefetch is None:
                domain = [
                    "&", "&",
                    ("state", "=", "sale"),
                    ("first_contract_date", "<=", end.isoformat()),
                    "|",
                    ("end_date", "=", False),
                    ("end_date", ">=", start.isoformat()),
                ]
                fields = [
                    "id",
                    "name",
                    "start_date",
                    "end_date",
                    "recurring_monthly",
                ]

                try:
                    orders = self.odoo_client.search_read_all(
                        model="sale.order",
                        domain=domain,
                        fields=fields,
                    )
                except Exception as e:
                    print(f"Error fetching subscription statistics: {e}")
                    return _default_subscription_stats()
            else:
                orders = prefetch

            active_count = 0
            churned_count = 0
            new_renew_count = 0
            mrr_total = 0.0
            active_order_names = []

            for order in orders:
                # Support both raw sale.order records and enriched subscription dicts
                end_date_val = self._parse_odoo_date(order.get("end_date"))
                is_churned = bool(end_date_val and end_date_val <= end)

                if is_churned:
                    churned_count += 1
                else:
                    active_count += 1
                    order_name = order.get("name") or order.get("order_name", "")
                    if order_name:
                        active_order_names.append(order_name)

                    recurring = order.get("recurring_monthly")
                    if recurring is None:
                        recurring = order.get("monthly_recurring_payment")
                    if recurring:
                        try:
                            mrr_total += float(recurring)
                        except (ValueError, TypeError):
                            pass

                start_date_val = self._parse_odoo_date(order.get("start_date")) or self._parse_odoo_date(order.get("first_contract_date"))
                if start_date_val and start <= start_date_val <= end:
                    new_renew_count += 1

            active_order_names = sorted(set(active_order_names))
            total_subscriptions = active_count + churned_count

            return {
                "active_count": active_count,
                "churned_count": churned_count,
                "new_renew_count": new_renew_count,
                "mrr": mrr_total,
                "mrr_display": f"AED {mrr_total:,.2f}" if mrr_total > 0 else "AED 0.00",
                "active_order_names": active_order_names,
                "total_subscriptions": total_subscriptions,
                "subscription_comparison": None,
            }

        current_stats = _compute_subscription_stats(month_start, month_end, subscriptions)

        previous_bounds = self._previous_month_bounds(month_start)
        if previous_bounds:
            prev_start, prev_end = previous_bounds
            previous_stats = _compute_subscription_stats(prev_start, prev_end)
            current_total = current_stats.get("total_subscriptions", 0)
            previous_total = previous_stats.get("total_subscriptions", 0)
            current_stats["subscription_comparison"] = self._calculate_comparison(current_total, previous_total)

        return current_stats
