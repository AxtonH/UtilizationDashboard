"""External hours aggregation from sales orders."""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Tuple
from calendar import monthrange
import time
import os
import socket

from ..config import OdooSettings
from ..integrations.odoo_client import OdooClient, OdooUnavailableError
from .supabase_cache_service import SupabaseCacheService

_EXTERNAL_USED_HOURS_SERIES_CACHE: Dict[Tuple[int, Optional[int], Optional[int]], Dict[str, Any]] = {}
_EXTERNAL_USED_HOURS_SERIES_TTL_SECONDS = 60 * 10  # Cache for 10 minutes to avoid repeated Odoo calls.

class ExternalHoursService:
    """Retrieve sales orders and aggregate external hours by market and project."""

    HOURS_LABEL = "Hours"
    VALID_INVOICE_STATUSES = {"invoiced", "to invoice", "to_invoice", "no"}
    CONFIRMED_STATES = {"sale"}

    def __init__(self, client: OdooClient, cache_service: Optional[SupabaseCacheService] = None):
        self.client = client
        # Simple request-scoped caches to avoid repeated XML-RPC calls within
        # the same response lifecycle.
        self._project_cache: Dict[int, Dict[str, Any]] = {}
        self._tag_cache: Dict[int, str] = {}
        self._agreement_cache: Dict[int, str] = {}
        self._order_line_cache: Dict[int, Dict[str, Any]] = {}
        self._invoice_cache: Dict[int, Dict[str, Any]] = {}
        self._project_task_cache: Dict[int, Dict[str, Any]] = {}
        # Supabase cache service (optional - falls back to Odoo if not available)
        self._cache_service = cache_service

    @classmethod
    def from_settings(cls, settings: OdooSettings, cache_service: Optional[SupabaseCacheService] = None) -> "ExternalHoursService":
        """Create an ExternalHoursService instance from Odoo settings.
        
        Args:
            settings: Odoo connection settings
            cache_service: Optional Supabase cache service for caching monthly data
        """
        return cls(OdooClient(settings), cache_service=cache_service)

    def external_hours_for_month(self, month_start: date, month_end: date) -> Dict[str, Any]:
        start_dt = datetime.combine(month_start, datetime.min.time())
        # include end date inclusive
        end_dt = datetime.combine(month_end + timedelta(days=1), datetime.min.time())

        orders = self._fetch_orders(start_dt, end_dt)
        if not orders:
            return {"markets": [], "summary": self._empty_summary()}

        orders = [
            order
            for order in orders
            if self._is_sales_order(order) and self._is_confirmed_sale(order)
        ]
        if not orders:
            return {"markets": [], "summary": self._empty_summary()}

        project_ids = {order["project_id"][0] for order in orders if order.get("project_id")}
        projects = self._fetch_projects(project_ids) if project_ids else {}
        line_ids = {line_id for order in orders for line_id in order.get("order_line", [])}
        lines = self._fetch_order_lines(line_ids) if line_ids else {}

        order_hours: Dict[int, float] = {}
        order_line_counts: Dict[int, int] = {}
        for order in orders:
            hours_total = 0.0
            order_line_count = len(order.get("order_line", []))
            for line_id in order.get("order_line", []):
                line = lines.get(line_id)
                if not line:
                    continue
                if self._is_hours_uom(line.get("product_uom")):
                    hours_total += float(line.get("product_uom_qty") or 0.0)
            if hours_total > 0:
                order_hours[order["id"]] = hours_total
                order_line_counts[order["id"]] = order_line_count

        if not order_hours:
            return {"markets": [], "summary": self._empty_summary()}

        market_groups: MutableMapping[str, MutableMapping[str, Dict[str, Any]]] = defaultdict(dict)

        for order in orders:
            order_id = order["id"]
            hours = order_hours.get(order_id, 0.0)
            if hours <= 0:
                continue

            project_field = order.get("project_id")
            if isinstance(project_field, (list, tuple)) and len(project_field) >= 2:
                project_id = project_field[0]
                project_name = str(project_field[1])
            else:
                project_id = None
                project_name = "Unassigned Project"

            project_meta = projects.get(project_id) if project_id else {}
            market = self._market_label(project_meta)
            agreement_type = self._format_agreement_type(project_meta)
            tags = self._project_tags(project_meta)

            market_state = market_groups.setdefault(
                market,
                {
                    "market": market,
                    "projects": {},
                    "total_external_hours": 0.0,
                    "total_aed": 0.0,
                    "total_invoices": 0,
                },
            )

            project_key = project_name
            project_state = market_state["projects"].setdefault(
                project_key,
                {
                    "project_id": project_id if isinstance(project_id, int) else None,
                    "project_name": project_name,
                    "agreement_type": agreement_type,
                    "tags": tags,
                    "sales_orders": [],
                    "total_external_hours": 0.0,
                    "total_aed": 0.0,
                },
            )

            market_state["total_external_hours"] += hours
            project_state["total_external_hours"] += hours
            aed_total_value = self._safe_currency_float(order.get("x_studio_aed_total"))
            project_state["total_aed"] += aed_total_value
            order_id = order["id"]
            order_line_count = order_line_counts.get(order_id, 0)
            project_state["sales_orders"].append(
                {
                    "order_reference": order.get("name"),
                    "external_hours": hours,
                    "external_hours_display": self._format_hours(hours),
                    "order_line_count": order_line_count,
                    "aed_total": aed_total_value,
                    "aed_total_display": self._format_currency(aed_total_value),
                }
            )
            market_state["total_aed"] += aed_total_value
            market_state["total_invoices"] += 1

        markets: List[Dict[str, Any]] = []
        for market, state in market_groups.items():
            projects = sorted(
                state["projects"].values(),
                key=lambda item: item["project_name"].lower(),
            )
            for project in projects:
                project["sales_orders"].sort(key=lambda item: str(item["order_reference"]))
                project["external_hours_display"] = self._format_hours(project["total_external_hours"])
                project["total_aed_display"] = self._format_currency(project.get("total_aed", 0.0))

            markets.append(
                {
                    "market": market,
                    "projects": projects,
                    "total_external_hours": state["total_external_hours"],
                    "total_external_hours_display": self._format_hours(state["total_external_hours"]),
                    "total_aed": state.get("total_aed", 0.0),
                    "total_aed_display": self._format_currency(state.get("total_aed", 0.0)),
                    "total_invoices": state.get("total_invoices", 0),
                }
            )

        markets.sort(key=lambda item: item["market"].lower())

        total_projects = 0
        total_external_hours = 0.0
        total_revenue = 0.0
        total_invoices = 0
        total_orders = 0
        for state in market_groups.values():
            total_external_hours += state["total_external_hours"]
            total_invoices += state.get("total_invoices", 0)
            for project in state["projects"].values():
                total_projects += 1
                total_revenue += project.get("total_aed", 0.0)
                total_orders += len(project.get("sales_orders", []))

        summary = {
            "total_projects": total_projects,
            "total_external_hours": total_external_hours,
            "total_external_hours_display": self._format_hours(total_external_hours),
            "total_revenue_aed": total_revenue,
            "total_revenue_aed_display": self._format_currency(total_revenue),
            "total_invoices": total_invoices,
            "total_orders": total_orders,
        }

        return {"markets": markets, "summary": summary}

    def subscription_hours_for_month(self, month_start: date, month_end: date) -> Dict[str, Any]:
        """Aggregate subscription hours for posted invoices grouped by market."""
        start_dt = datetime.combine(month_start, datetime.min.time()).date()
        end_dt = month_end

        orders = self._fetch_subscription_orders(month_start, month_end)
        if not orders:
            return {"markets": [], "summary": self._empty_subscription_summary(), "top_clients": []}

        # Collect all invoice ids for the fetched orders
        invoice_ids: set[int] = set()
        for order in orders:
            for invoice_id in order.get("invoice_ids") or []:
                if isinstance(invoice_id, int):
                    invoice_ids.add(invoice_id)

        invoices = self._fetch_invoices(invoice_ids) if invoice_ids else {}

        def _first_contract(order: Mapping[str, Any]) -> Optional[date]:
            first_raw = order.get("first_contract_date")
            first_date = self._parse_odoo_date(first_raw)
            if first_date is not None:
                return first_date
            inv_ids = [inv_id for inv_id in order.get("invoice_ids") or [] if isinstance(inv_id, int)]
            candidates = []
            for inv_id in inv_ids:
                invoice = invoices.get(inv_id)
                if not invoice:
                    continue
                invoice_date = self._parse_odoo_date(invoice.get("invoice_date"))
                if invoice_date is not None:
                    candidates.append(invoice_date)
            if candidates:
                return min(candidates)
            return None

        active_orders: List[Dict[str, Any]] = []
        active_order_ids: set[int] = set()
        for order in orders:
            order_id = order.get("id")
            if not isinstance(order_id, int):
                continue
            first_contract = _first_contract(order)
            if first_contract and first_contract > end_dt:
                continue
            end_date = self._parse_odoo_date(order.get("end_date"))
            if end_date and end_date < start_dt:
                continue
            order["_first_contract_date"] = first_contract  # type: ignore[assignment]
            active_orders.append(order)
            active_order_ids.add(order_id)

        if not active_orders:
            empty = self._empty_subscription_summary()
            empty["total_subscriptions"] = 0
            return {"markets": [], "summary": empty, "top_clients": []}

        filtered_invoices: Dict[int, Dict[str, Any]] = {}
        for invoice_id, invoice in (invoices or {}).items():
            state = str(invoice.get("state") or "").lower()
            if state != "posted":
                continue
            invoice_date_raw = invoice.get("invoice_date")
            invoice_date = self._parse_odoo_date(invoice_date_raw)
            if invoice_date is None or invoice_date < start_dt or invoice_date > end_dt:
                continue
            filtered_invoices[invoice_id] = {
                **invoice,
                "_parsed_date": invoice_date,
            }

        project_ids = {
            order["project_id"][0]
            for order in active_orders
            if isinstance(order.get("project_id"), (list, tuple)) and len(order["project_id"]) >= 1
        }
        projects = self._fetch_projects(project_ids) if project_ids else {}
        project_task_summaries = (
            self._subscription_used_hours_for_projects(project_ids, month_start, month_end)
            if project_ids
            else {}
        )

        market_groups: MutableMapping[str, Dict[str, Any]] = {}
        counted_order_ids_global: set[int] = set()
        total_revenue = 0.0
        top_client_candidates: Dict[str, Dict[str, Any]] = {}

        def update_top_client(
            project_id: Optional[int],
            client_name: str,
            market_name: str,
            revenue_delta: float,
            request_count: int,
        ) -> None:
            safe_name = self._safe_str(client_name, default="Unassigned Project")
            safe_market = self._safe_str(market_name, default="Unassigned Market")
            key = (
                str(project_id)
                if isinstance(project_id, int)
                else f"name::{safe_market.lower()}::{safe_name.lower()}"
            )
            entry = top_client_candidates.setdefault(
                key,
                {
                    "project_id": project_id if isinstance(project_id, int) else None,
                    "client_name": safe_name,
                    "market": safe_market,
                    "total_revenue_aed": 0.0,
                    "request_count": 0,
                },
            )
            entry["total_revenue_aed"] += float(revenue_delta or 0.0)
            if not entry.get("market"):
                entry["market"] = safe_market
            if isinstance(request_count, (int, float)):
                entry["request_count"] = max(entry.get("request_count", 0), int(request_count))

        for order in active_orders:
            order_id = order.get("id")
            if not isinstance(order_id, int):
                continue

            order_invoice_ids = [
                inv_id for inv_id in order.get("invoice_ids") or [] if isinstance(inv_id, int)
            ]
            posted_invoices = [
                filtered_invoices[inv_id]
                for inv_id in order_invoice_ids
                if inv_id in filtered_invoices
            ]

            project_field = order.get("project_id")
            if isinstance(project_field, (list, tuple)) and len(project_field) >= 2:
                project_id = project_field[0]
                project_name = self._safe_str(project_field[1], default="Unassigned Project")
            else:
                project_id = None
                project_name = "Unassigned Project"

            project_meta = projects.get(project_id) if project_id else {}
            market = self._market_label(project_meta)
            agreement_type = self._format_agreement_type(project_meta)
            tags = self._project_tags(project_meta)
            monthly_hours_value = self._safe_float(order.get("x_studio_external_billable_hours_monthly"))
            monthly_hours_display = self._format_hours(monthly_hours_value)
            market_state = market_groups.setdefault(
                market,
                {
                    "market": market,
                    "subscriptions": [],
                    "total_monthly_hours": 0.0,
                    "total_aed": 0.0,
                    "total_subscription_used_hours": 0.0,
                    "_counted_orders": set(),
                    "_counted_used_orders": set(),
                },
            )
            project_task_summary = project_task_summaries.get(project_id, {})
            subscription_used_hours = float(project_task_summary.get("total_external_hours", 0.0) or 0.0)
            subscription_used_hours_display = project_task_summary.get(
                "total_external_hours_display", self._format_hours(subscription_used_hours)
            )
            subscription_parent_tasks = project_task_summary.get("parent_tasks", [])

            request_count_value = (
                len(subscription_parent_tasks)
                if isinstance(subscription_parent_tasks, list)
                else 0
            )

            if posted_invoices:
                for invoice in posted_invoices:
                    invoice_date = invoice["_parsed_date"]
                    invoice_reference = self._safe_str(invoice.get("name"), default="Invoice")
                    amount_total = self._safe_currency_float(
                        invoice.get("amount_total_signed") or invoice.get("amount_total")
                    )
                    total_revenue += amount_total
                    entry = {
                        "order_reference": self._safe_str(order.get("name"), default="Subscription"),
                        "invoice_reference": invoice_reference,
                        "invoice_date": invoice_date.isoformat(),
                        "invoice_date_display": self._format_date(invoice_date),
                        "monthly_billable_hours": monthly_hours_value,
                        "monthly_billable_hours_display": monthly_hours_display,
                        "aed_total": amount_total,
                        "aed_total_display": self._format_currency(amount_total),
                        "project_name": project_name,
                        "agreement_type": agreement_type,
                        "tags": tags,
                        "subscription_used_hours": subscription_used_hours,
                        "subscription_used_hours_display": subscription_used_hours_display,
                        "subscription_parent_tasks": subscription_parent_tasks,
                    }
                    market_state["subscriptions"].append(entry)
                    market_state["total_aed"] += amount_total
                    update_top_client(
                        project_id if isinstance(project_id, int) else None,
                        project_name,
                        market,
                        amount_total,
                        request_count_value,
                    )
            else:
                first_contract = order.get("_first_contract_date")
                contract_display = (
                    self._format_date(first_contract)
                    if isinstance(first_contract, date)
                    else "-"
                )
                entry = {
                    "order_reference": self._safe_str(order.get("name"), default="Subscription"),
                    "invoice_reference": "No Invoice",
                    "invoice_date": None,
                    "invoice_date_display": contract_display,
                    "monthly_billable_hours": monthly_hours_value,
                    "monthly_billable_hours_display": monthly_hours_display,
                    "aed_total": 0.0,
                    "aed_total_display": self._format_currency(0.0),
                    "project_name": project_name,
                    "agreement_type": agreement_type,
                    "tags": tags,
                    "subscription_used_hours": subscription_used_hours,
                    "subscription_used_hours_display": subscription_used_hours_display,
                    "subscription_parent_tasks": subscription_parent_tasks,
                }
                market_state["subscriptions"].append(entry)
                update_top_client(
                    project_id if isinstance(project_id, int) else None,
                    project_name,
                    market,
                    0.0,
                    request_count_value,
                )

            counted_orders: set[int] = market_state["_counted_orders"]
            if monthly_hours_value > 0 and order_id not in counted_orders:
                market_state["total_monthly_hours"] += monthly_hours_value
                counted_orders.add(order_id)
                counted_order_ids_global.add(order_id)
            counted_used_orders: set[int] = market_state["_counted_used_orders"]
            if subscription_used_hours > 0 and order_id not in counted_used_orders:
                market_state["total_subscription_used_hours"] += subscription_used_hours
                counted_used_orders.add(order_id)

        if not market_groups:
            return {"markets": [], "summary": self._empty_subscription_summary(), "top_clients": []}

        markets: List[Dict[str, Any]] = []
        for market, state in market_groups.items():
            subscriptions = state["subscriptions"]
            subscriptions.sort(
                key=lambda item: (
                    item["order_reference"].lower(),
                    item["invoice_date"],
                )
            )
            markets.append(
                {
                    "market": market,
                    "subscriptions": subscriptions,
                    "total_monthly_hours": state["total_monthly_hours"],
                    "total_monthly_hours_display": self._format_hours(state["total_monthly_hours"]),
                    "total_aed": state["total_aed"],
                    "total_aed_display": self._format_currency(state["total_aed"]),
                    "total_subscription_used_hours": state["total_subscription_used_hours"],
                    "total_subscription_used_hours_display": self._format_hours(
                        state["total_subscription_used_hours"]
                    ),
                }
            )

        markets.sort(key=lambda item: item["market"].lower())

        total_monthly_hours = sum(item["total_monthly_hours"] for item in markets)
        total_subscription_used_hours = sum(item["total_subscription_used_hours"] for item in markets)
        
        # Count total parent tasks across all subscriptions
        total_parent_tasks = 0
        for market_state in market_groups.values():
            for subscription in market_state.get("subscriptions", []):
                parent_tasks = subscription.get("subscription_parent_tasks", [])
                if isinstance(parent_tasks, list):
                    total_parent_tasks += len(parent_tasks)

        top_client_entries: List[Dict[str, Any]] = []
        for candidate in top_client_candidates.values():
            total_value = float(candidate.get("total_revenue_aed", 0.0) or 0.0)
            client_name = self._safe_str(candidate.get("client_name"), default="Unassigned Project")
            market_name = self._safe_str(candidate.get("market"), default="Unassigned Market")
            request_total = int(candidate.get("request_count", 0) or 0)
            top_client_entries.append(
                {
                    "project_id": candidate.get("project_id"),
                    "client_name": client_name,
                    "market": market_name,
                    "total_revenue_aed": total_value,
                    "total_revenue_aed_display": self._format_currency(total_value),
                    "request_count": request_total,
                }
            )

        top_clients = sorted(
            top_client_entries,
            key=lambda item: (-item["total_revenue_aed"], item["client_name"].lower()),
        )[:5]

        summary = {
            "total_subscriptions": len(active_order_ids),
            "total_monthly_hours": total_monthly_hours,
            "total_monthly_hours_display": self._format_hours(total_monthly_hours),
            "total_revenue_aed": total_revenue,
            "total_revenue_aed_display": self._format_currency(total_revenue),
            "total_subscription_used_hours": total_subscription_used_hours,
            "total_subscription_used_hours_display": self._format_hours(total_subscription_used_hours),
            "total_parent_tasks": total_parent_tasks,
        }

        summary["top_clients"] = top_clients

        return {"markets": markets, "summary": summary, "top_clients": top_clients}

    def external_used_hours_series(
        self,
        year: int,
        *,
        upto_month: Optional[int] = None,
        max_months: Optional[int] = None,
        force_refresh: bool = False,
    ) -> List[Dict[str, Any]]:
        """Return monthly external used hours (external + subscription used) for the specified year.

        Optionally limit the data to the months up to ``upto_month`` (inclusive) and cap the
        number of trailing months via ``max_months`` to avoid long-running Odoo queries.
        
        Args:
            year: The year to fetch data for
            upto_month: Optional month limit (inclusive)
            max_months: Optional limit on number of trailing months
            force_refresh: If True, refresh all months from Odoo (ignoring cache)
        """
        # Use Supabase cache if available (it handles caching internally)
        # Pass force_refresh to control whether to use cache or refresh from Odoo
        series = self._build_external_used_hours_series(
            year, upto_month=upto_month, max_months=max_months, force_refresh=force_refresh
        )
        
        # Fallback to in-memory cache only if Supabase is not available
        if not self._cache_service:
            cache_key = (year, upto_month, max_months)
            cache_entry = _EXTERNAL_USED_HOURS_SERIES_CACHE.get(cache_key)
            now = time.time()
            if cache_entry and now - cache_entry["timestamp"] < _EXTERNAL_USED_HOURS_SERIES_TTL_SECONDS and not force_refresh:
                return deepcopy(cache_entry["data"])
            _EXTERNAL_USED_HOURS_SERIES_CACHE[cache_key] = {"timestamp": now, "data": series}
        
        return series

    def _build_external_used_hours_series(
        self,
        year: int,
        *,
        upto_month: Optional[int] = None,
        max_months: Optional[int] = None,
        force_refresh: bool = False,
    ) -> List[Dict[str, Any]]:
        """Build external used hours series with Supabase caching support.
        
        Args:
            year: The year to fetch data for
            upto_month: Optional month limit (inclusive)
            max_months: Optional limit on number of trailing months
            force_refresh: If True, refresh all months from Odoo (ignoring cache)
        """
        today = date.today()
        max_month = upto_month or (today.month if year == today.year else 12)
        if max_month < 1:
            max_month = 1
        if year == today.year:
            max_month = min(max_month, today.month)
        else:
            max_month = min(max_month, 12)

        start_month = 1
        if max_months and max_months > 0:
            start_month = max(1, max_month - max_months + 1)

        series: List[Dict[str, Any]] = []
        current_month = today.month if year == today.year else None
        
        for month in range(start_month, max_month + 1):
            month_start = date(year, month, 1)
            _, last_day = monthrange(year, month)
            month_end = month_start.replace(day=last_day)

            # Always refresh current month, check cache for others unless force_refresh
            is_current_month = (year == today.year and month == current_month)
            should_refresh = force_refresh or is_current_month
            
            month_data = None
            if not should_refresh and self._cache_service:
                # Try to get from cache
                cached = self._cache_service.get_month_data(year, month)
                if cached:
                    month_data = self._cache_service.convert_cache_to_series_format(cached)
            
            # If not in cache or needs refresh, fetch from Odoo
            if month_data is None:
                external_snapshot = self.external_hours_for_month(month_start, month_end)
                subscription_snapshot = self.subscription_hours_for_month(month_start, month_end)

                external_total = float(
                    external_snapshot.get("summary", {}).get("total_external_hours", 0.0) or 0.0
                )
                subscription_total = float(
                    subscription_snapshot.get("summary", {}).get("total_subscription_used_hours", 0.0) or 0.0
                )
                combined_used_hours = external_total + subscription_total

                subscription_monthly_total = float(
                    subscription_snapshot.get("summary", {}).get("total_monthly_hours", 0.0) or 0.0
                )
                total_sold_hours = external_total + subscription_monthly_total

                month_data = {
                    "year": year,
                    "month": month,
                    "label": month_start.strftime("%b"),
                    "total_external_hours": external_total,
                    "total_external_hours_display": self._format_hours(external_total),
                    "total_subscription_used_hours": subscription_total,
                    "total_subscription_used_hours_display": self._format_hours(subscription_total),
                    "total_used_hours": combined_used_hours,
                    "total_used_hours_display": self._format_hours(combined_used_hours),
                    "total_monthly_subscription_hours": subscription_monthly_total,
                    "total_monthly_subscription_hours_display": self._format_hours(
                        subscription_monthly_total
                    ),
                    "total_sold_hours": total_sold_hours,
                    "total_sold_hours_display": self._format_hours(total_sold_hours),
                }
                
                # Save to cache if available
                if self._cache_service:
                    self._cache_service.save_month_data(
                        year=year,
                        month=month,
                        total_external_hours=external_total,
                        total_subscription_used_hours=subscription_total,
                        total_used_hours=combined_used_hours,
                        total_monthly_subscription_hours=subscription_monthly_total,
                        total_sold_hours=total_sold_hours,
                    )
            
            series.append(month_data)

        return series

    def _subscription_used_hours_for_projects(
        self,
        project_ids: Iterable[int],
        month_start: date,
        month_end: date,
    ) -> Dict[int, Dict[str, Any]]:
        ids = [project_id for project_id in project_ids if isinstance(project_id, int)]
        if not ids:
            return {}

        start_dt = datetime.combine(month_start, datetime.min.time())
        end_dt = datetime.combine(month_end + timedelta(days=1), datetime.min.time())
        domain = [
            ("project_id", "in", ids),
            ("parent_id", "=", False),
            ("x_studio_request_receipt_date_time", ">=", start_dt.isoformat(sep=" ")),
            ("x_studio_request_receipt_date_time", "<", end_dt.isoformat(sep=" ")),
        ]
        fields = ["id", "name", "project_id", "child_ids", "x_studio_request_receipt_date_time"]
        parent_tasks: List[Dict[str, Any]] = []
        
        try:
            for batch in self.client.search_read_chunked(
                "project.task",
                domain=domain,
                fields=fields,
                order="x_studio_request_receipt_date_time asc, id asc",
            ):
                parent_tasks.extend(batch)
        except (OdooUnavailableError, socket.timeout, Exception) as e:
            # Log error and return empty result to prevent full request failure
            # In production, you might want to log this to a monitoring service
            print(f"Error fetching subscription tasks: {e}")
            return {}

        if not parent_tasks:
            return {}

        child_ids: List[int] = []
        for parent in parent_tasks:
            raw_child_ids = parent.get("child_ids") or []
            for child_id in raw_child_ids:
                if isinstance(child_id, int):
                    child_ids.append(child_id)

        try:
            child_map = self._fetch_tasks_map(child_ids, ["id", "name", "parent_id", "x_studio_external_hours_2"])
        except (OdooUnavailableError, socket.timeout, Exception) as e:
            # Log error and continue with empty child map
            print(f"Error fetching child tasks: {e}")
            child_map = {}

        project_summaries: Dict[int, Dict[str, Any]] = {}
        for parent in parent_tasks:
            project_field = parent.get("project_id")
            if not (isinstance(project_field, (list, tuple)) and len(project_field) >= 2):
                continue
            project_id = project_field[0]
            if not isinstance(project_id, int):
                continue
            request_raw = parent.get("x_studio_request_receipt_date_time")
            request_dt = self._parse_odoo_datetime(request_raw)
            if request_dt is None or request_dt < start_dt or request_dt >= end_dt:
                continue

            child_entries: List[Dict[str, Any]] = []
            total_hours = 0.0
            for child_id in parent.get("child_ids") or []:
                if not isinstance(child_id, int):
                    continue
                child = child_map.get(child_id)
                if not child:
                    continue
                hours_value = self._safe_float(child.get("x_studio_external_hours_2"))
                if hours_value <= 0:
                    continue
                child_entries.append(
                    {
                        "task_id": child_id,
                        "task_name": self._safe_str(child.get("name"), default=f"Task {child_id}"),
                        "external_hours": hours_value,
                        "external_hours_display": self._format_hours(hours_value),
                    }
                )
                total_hours += hours_value

            if total_hours <= 0:
                continue

            parent_id = parent.get("id")
            parent_entry = {
                "task_id": parent_id if isinstance(parent_id, int) else None,
                "task_name": self._safe_str(parent.get("name"), default=f"Task {parent_id}"),
                "project_name": self._safe_str(project_field[1], default="Unassigned Project"),
                "request_datetime": request_dt.isoformat(),
                "request_datetime_display": self._format_datetime(request_dt),
                "external_hours": total_hours,
                "external_hours_display": self._format_hours(total_hours),
                "subtasks": child_entries,
            }

            summary = project_summaries.setdefault(
                project_id,
                {"total_external_hours": 0.0, "parent_tasks": []},
            )
            summary["parent_tasks"].append(parent_entry)
            summary["total_external_hours"] += total_hours

        for summary in project_summaries.values():
            total_hours = float(summary.get("total_external_hours", 0.0) or 0.0)
            summary["total_external_hours_display"] = self._format_hours(total_hours)
            summary["parent_tasks"].sort(
                key=lambda item: (
                    item.get("request_datetime") or "",
                    self._safe_str(item.get("task_name")).lower(),
                )
            )

        return project_summaries

    def _fetch_tasks_map(self, task_ids: Iterable[int], fields: Iterable[str]) -> Dict[int, Dict[str, Any]]:
        ids = [task_id for task_id in task_ids if isinstance(task_id, int)]
        if not ids:
            return {}
        result: Dict[int, Dict[str, Any]] = {}
        chunk = 80
        for start in range(0, len(ids), chunk):
            chunk_ids = ids[start : start + chunk]
            tasks = self.client.read("project.task", chunk_ids, fields)
            for task in tasks:
                task_id = task.get("id")
                if isinstance(task_id, int):
                    result[task_id] = task
        return result

    def _parse_odoo_datetime(self, value: Any) -> Optional[datetime]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, date) and not isinstance(value, datetime):
            return datetime.combine(value, datetime.min.time())
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
                    try:
                        return datetime.strptime(value, fmt)
                    except ValueError:
                        continue
        return None

    def _format_datetime(self, value: datetime) -> str:
        return value.strftime("%d %b %Y %H:%M")

    def _fetch_orders(self, start_dt: datetime, end_dt: datetime) -> List[Dict[str, Any]]:
        domain = [
            ("date_order", ">=", start_dt.isoformat(sep=" ")),
            ("date_order", "<", end_dt.isoformat(sep=" ")),
        ]
        fields = [
            "id",
            "name",
            "date_order",
            "project_id",
            "order_line",
            "invoice_status",
            "state",
            "x_studio_aed_total",
        ]
        orders: List[Dict[str, Any]] = []
        for batch in self.client.search_read_chunked(
            "sale.order",
            domain=domain,
            fields=fields,
            order="date_order asc, id asc",
        ):
            orders.extend(batch)
        return orders

    def _fetch_projects(self, project_ids: Iterable[int]) -> Dict[int, Dict[str, Any]]:
        ids = [project_id for project_id in project_ids if isinstance(project_id, int)]
        if not ids:
            return {}
        missing = [project_id for project_id in ids if project_id not in self._project_cache]
        if missing:
            fields = ["x_studio_market_2", "x_studio_agreement_type_1", "tag_ids", "name"]
            records = self.client.read("project.project", missing, fields)
            for record in records:
                project_id = record.get("id")
                if isinstance(project_id, int):
                    self._project_cache[project_id] = record
        project_map: Dict[int, Dict[str, Any]] = {project_id: self._project_cache[project_id] for project_id in ids if project_id in self._project_cache}
        tag_ids: set[int] = set()
        agreement_ids: set[int] = set()
        for record in project_map.values():
            project_id = record.get("id")
            if isinstance(project_id, int):
                for tag_id in record.get("tag_ids") or []:
                    if isinstance(tag_id, int):
                        tag_ids.add(tag_id)
                for agreement_id in record.get("x_studio_agreement_type_1") or []:
                    if isinstance(agreement_id, int):
                        agreement_ids.add(agreement_id)

        agreement_map = self._fetch_agreement_types(agreement_ids) if agreement_ids else {}
        tag_names = self._fetch_project_tags(tag_ids) if tag_ids else {}

        for project in project_map.values():
            ids = project.get("tag_ids") or []
            project["tag_names"] = [tag_names.get(tag_id, f"Tag {tag_id}") for tag_id in ids if isinstance(tag_id, int)]

            raw_agreements = project.get("x_studio_agreement_type_1") or []
            agreement_names = [agreement_map.get(agreement_id, f"Agreement {agreement_id}") for agreement_id in raw_agreements if isinstance(agreement_id, int)]
            project["agreement_type_names"] = [name for name in agreement_names if name]

        return project_map

    def _fetch_agreement_types(self, type_ids: Iterable[int]) -> Dict[int, str]:
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

    def _fetch_project_tags(self, tag_ids: Iterable[int]) -> Dict[int, str]:
        ids = [tag_id for tag_id in tag_ids if isinstance(tag_id, int)]
        if not ids:
            return {}
        missing = [tag_id for tag_id in ids if tag_id not in self._tag_cache]
        if missing:
            fields = ["name"]
            tags = self.client.read("project.tags", missing, fields)
            for tag in tags:
                tag_id = tag.get("id")
                if isinstance(tag_id, int):
                    self._tag_cache[tag_id] = str(tag.get("name", ""))
        return {tag_id: self._tag_cache.get(tag_id, f"Tag {tag_id}") for tag_id in ids}

    def _fetch_order_lines(self, line_ids: Iterable[int]) -> Dict[int, Dict[str, Any]]:
        ids = [line_id for line_id in line_ids if isinstance(line_id, int)]
        if not ids:
            return {}
        missing = [line_id for line_id in ids if line_id not in self._order_line_cache]
        if missing:
            fields = ["product_uom_qty", "product_uom"]
            lines = self.client.read("sale.order.line", missing, fields)
            for line in lines:
                line_id = line.get("id")
                if isinstance(line_id, int):
                    self._order_line_cache[line_id] = line
        return {line_id: self._order_line_cache[line_id] for line_id in ids if line_id in self._order_line_cache}

    def _fetch_subscription_orders(self, month_start: date, month_end: date) -> List[Dict[str, Any]]:
        domain = [
            ("state", "in", list(self.CONFIRMED_STATES)),
            ("x_studio_external_billable_hours_monthly", ">", 0),
            ("subscription_state", "in", ["3_progress", "6_churn"]),
            "|",
            ("end_date", "=", False),
            ("end_date", ">=", month_start.isoformat()),
        ]
        fields = [
            "id",
            "name",
            "project_id",
            "invoice_ids",
            "x_studio_external_billable_hours_monthly",
            "first_contract_date",
            "end_date",
            "subscription_state",
        ]
        orders: List[Dict[str, Any]] = []
        for batch in self.client.search_read_chunked(
            "sale.order",
            domain=domain,
            fields=fields,
            order="id asc",
        ):
            orders.extend(batch)
        return orders

    def _fetch_invoices(self, invoice_ids: Iterable[int]) -> Dict[int, Dict[str, Any]]:
        ids = list(invoice_ids)
        if not ids:
            return {}
        fields = [
            "id",
            "name",
            "invoice_date",
            "state",
            "amount_total",
            "amount_total_signed",
            "move_type",
            "invoice_origin",
        ]
        missing = [invoice_id for invoice_id in ids if invoice_id not in self._invoice_cache]
        if missing:
            invoices = self.client.read("account.move", missing, fields)
            for invoice in invoices:
                invoice_id = invoice.get("id")
                if not isinstance(invoice_id, int):
                    continue
                move_type = str(invoice.get("move_type") or "").lower()
                if move_type not in {"out_invoice", "out_receipt"}:
                    continue
                self._invoice_cache[invoice_id] = invoice
        return {invoice_id: self._invoice_cache[invoice_id] for invoice_id in ids if invoice_id in self._invoice_cache}

    def _is_hours_uom(self, value: Any) -> bool:
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            return str(value[1]).strip().lower() == self.HOURS_LABEL.lower()
        if isinstance(value, str):
            return value.strip().lower() == self.HOURS_LABEL.lower()
        return False

    def _is_sales_order(self, order: Mapping[str, Any]) -> bool:
        raw_status = order.get("invoice_status")
        if raw_status is None:
            return False
        normalized = str(raw_status).strip().lower()
        return normalized in self.VALID_INVOICE_STATUSES

    def _is_confirmed_sale(self, order: Mapping[str, Any]) -> bool:
        raw_state = order.get("state")
        if raw_state is None:
            return False
        normalized = str(raw_state).strip().lower()
        return normalized in self.CONFIRMED_STATES

    def _market_label(self, project: Optional[Mapping[str, Any]]) -> str:
        if not project:
            return "Unassigned Market"
        raw = project.get("x_studio_market_2")
        if isinstance(raw, (list, tuple)) and len(raw) >= 2:
            return self._safe_str(raw[1], default="Unassigned Market")
        return self._safe_str(raw, default="Unassigned Market")

    def _project_tags(self, project: Optional[Mapping[str, Any]]) -> List[str]:
        if not project:
            return []
        names = project.get("tag_names")
        if isinstance(names, list):
            return [str(name) for name in names if isinstance(name, str)]
        return []

    def _safe_str(self, value: Any, *, default: str = "") -> str:
        if value is None:
            return default
        return str(value).strip() or default

    def _format_hours(self, value: float) -> str:
        return f"{value:,.1f}h" if value % 1 else f"{int(value)}h"

    def _format_agreement_type(self, project: Mapping[str, Any] | None) -> str:
        if not project:
            return "Unknown"
        names = project.get("agreement_type_names")
        if isinstance(names, list):
            cleaned = [self._safe_str(name).strip() for name in names if isinstance(name, str)]
            cleaned = [name for name in cleaned if name]
            if cleaned:
                return ", ".join(cleaned)
        raw = project.get("x_studio_agreement_type_1")
        if isinstance(raw, (list, tuple)):
            cleaned = [self._safe_str(item).strip() for item in raw if isinstance(item, (str, int))]
            cleaned = [name for name in cleaned if name and name not in {"0", "[]"}]
            if cleaned:
                return ", ".join(cleaned)
        if isinstance(raw, (str, int)):
            value = self._safe_str(raw).strip()
            if value and value not in {"0", "[]"}:
                return value
        return "Unknown"

    def _format_currency(self, value: float) -> str:
        return f"{value:,.2f} AED"

    def _safe_currency_float(self, value: Any) -> float:
        if value is None:
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            cleaned = "".join(ch for ch in value if ch.isdigit() or ch in ".-")
            if not cleaned:
                return 0.0
            try:
                return float(cleaned)
            except ValueError:
                return 0.0
        return 0.0

    def _safe_float(self, value: Any) -> float:
        if value is None:
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                return 0.0
        return 0.0

    def _parse_odoo_date(self, value: Any) -> Optional[date]:
        if value is None:
            return None
        if isinstance(value, date):
            return value
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, str):
            try:
                # Odoo typically returns YYYY-MM-DD for dates
                return datetime.fromisoformat(value).date()
            except ValueError:
                try:
                    return datetime.strptime(value, "%Y-%m-%d").date()
                except ValueError:
                    return None
        return None

    def _format_date(self, value: date) -> str:
        return value.strftime("%d %b %Y")

    def _empty_summary(self) -> Dict[str, Any]:
        return {
            "total_projects": 0,
            "total_external_hours": 0.0,
            "total_external_hours_display": self._format_hours(0.0),
            "total_revenue_aed": 0.0,
            "total_revenue_aed_display": self._format_currency(0.0),
            "total_invoices": 0,
            "total_orders": 0,
        }

    def _empty_subscription_summary(self) -> Dict[str, Any]:
        return {
            "total_subscriptions": 0,
            "total_monthly_hours": 0.0,
            "total_monthly_hours_display": self._format_hours(0.0),
            "total_revenue_aed": 0.0,
            "total_revenue_aed_display": self._format_currency(0.0),
            "total_subscription_used_hours": 0.0,
            "total_subscription_used_hours_display": self._format_hours(0.0),
        }
