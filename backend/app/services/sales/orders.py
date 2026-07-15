"""Sales orders: domains, fetch/enrichment, series, dimension totals."""
from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple
import re
from ...integrations.odoo_client import OdooClient
from ..cache_finality import SALES_CACHE_FINALIZE_GRACE_DAYS, cached_month_rows_are_final
from .common import EXCLUDED_ORDER_LINE_PRODUCT_IDS, EXTERNAL_HOURS_SOL_LINE_DATETIME_FIELD, _datetime_in_gmt3_month, _parent_order_date_in_gmt3_month, _parse_odoo_datetime_field


class SalesOrdersMixin:
    """Sales orders: domains, fetch/enrichment, series, dimension totals."""

    def _fetch_sol_datetimes_by_order_id(
        self, orders: List[Dict[str, Any]], line_datetime_field: str
    ) -> Dict[int, List[datetime]]:
        """Read a datetime field from each order's ``sale.order.line`` rows."""
        line_ids: List[int] = []
        for order in orders:
            ol = order.get("order_line")
            if not ol or not isinstance(ol, list):
                continue
            for item in ol:
                if isinstance(item, int):
                    line_ids.append(item)
                elif isinstance(item, (list, tuple)) and len(item) >= 1 and isinstance(item[0], int):
                    line_ids.append(item[0])
        if not line_ids:
            return {}
        unique = list(dict.fromkeys(line_ids))
        by_order: Dict[int, List[datetime]] = {}
        chunk_size = 400
        for i in range(0, len(unique), chunk_size):
            chunk = unique[i : i + chunk_size]
            try:
                lines = self.odoo_client.read(
                    "sale.order.line",
                    chunk,
                    ["order_id", line_datetime_field],
                )
            except Exception:
                lines = []
            for line in lines:
                order_field = line.get("order_id")
                oid = order_field[0] if isinstance(order_field, (list, tuple)) and len(order_field) >= 1 else None
                if not isinstance(oid, int):
                    continue
                dt = _parse_odoo_datetime_field(line.get(line_datetime_field))
                if dt is not None:
                    by_order.setdefault(oid, []).append(dt)
        return by_order

    def _filter_orders_by_date_order_month(
        self,
        orders: List[Dict[str, Any]],
        start_date: date,
        end_date: date,
    ) -> List[Dict[str, Any]]:
        """GMT+3 calendar month using ``sale.order.date_order`` (standard dashboard scope)."""
        return [o for o in orders if _parent_order_date_in_gmt3_month(o, start_date, end_date)]

    def _filter_orders_by_sol_line_month(
        self,
        orders: List[Dict[str, Any]],
        start_date: date,
        end_date: date,
        line_datetime_field: str,
    ) -> List[Dict[str, Any]]:
        """GMT+3 month: keep orders that have at least one line whose SOL datetime falls in range."""
        sol_by_order = self._fetch_sol_datetimes_by_order_id(orders, line_datetime_field)
        keep: List[Dict[str, Any]] = []
        for o in orders:
            oid = o.get("id")
            if not isinstance(oid, int):
                continue
            for dt in sol_by_order.get(oid, []):
                if _datetime_in_gmt3_month(dt, start_date, end_date):
                    keep.append(o)
                    break
        return keep

    def _aggregate_sales_order_breakdown(
        self, orders: List[Dict[str, Any]], year: int, month: int
    ) -> List[Dict[str, Any]]:
        """Aggregate sales order breakdown by market/agreement/account for a month."""
        buckets: Dict[Tuple[str, str, str], Dict[str, Any]] = {}

        for order in orders or []:
            try:
                amount = order.get("x_studio_aed_total") or 0.0
                amount_val = float(amount)
            except Exception:
                amount_val = 0.0

            market = order.get("market") or "Unknown"
            agreement_type = self._canonical_agreement_label(order.get("agreement_type"))
            tags = order.get("tags") or []
            account_type = self._infer_account_type(tags)

            key = (market, agreement_type, account_type)
            if key not in buckets:
                buckets[key] = {
                    "year": year,
                    "month": month,
                    "market": market,
                    "agreement_type": agreement_type,
                    "account_type": account_type,
                    "amount_aed": 0.0,
                    "order_count": 0,
                }
            buckets[key]["amount_aed"] += amount_val
            buckets[key]["order_count"] += 1

        return list(buckets.values())

    def _build_sales_orders_breakdown(
        self, start_date: date, end_date: date, year: int, month: int
    ) -> List[Dict[str, Any]]:
        """Build sales orders breakdown rows for a month."""
        orders = self._get_sales_order_details(start_date, end_date)
        if not orders:
            return []
        return self._aggregate_sales_order_breakdown(orders, year, month)

    @staticmethod
    def _sales_order_dashboard_odoo_domain(start_dt_iso: str, end_dt_iso: str) -> List[Any]:
        """Domain for general sales dashboard ``sale.order`` queries (uses ``date_order``)."""
        return [
            "&",
            "&",
            "&",
            ("state", "=", "sale"),
            ("date_order", ">=", start_dt_iso),
            ("date_order", "<", end_dt_iso),
            ("order_line.product_id", "not in", list(EXCLUDED_ORDER_LINE_PRODUCT_IDS)),
        ]

    @staticmethod
    def _sales_order_dashboard_odoo_domain_external_hours_sol(start_dt_iso: str, end_dt_iso: str) -> List[Any]:
        """Domain for external-hours scope only — Order Date SOL v1 lives on ``sale.order.line``."""
        leaf = f"order_line.{EXTERNAL_HOURS_SOL_LINE_DATETIME_FIELD}"
        return [
            "&",
            "&",
            "&",
            ("state", "=", "sale"),
            (leaf, ">=", start_dt_iso),
            (leaf, "<", end_dt_iso),
            ("order_line.product_id", "not in", list(EXCLUDED_ORDER_LINE_PRODUCT_IDS)),
        ]

    def _get_sales_order_count(self, start_date: date, end_date: date) -> int:
        """Get count of sales orders with state='sale' for a date range.
        
        Args:
            start_date: Start of date range (inclusive)
            end_date: End of date range (inclusive)
            
        Returns:
            Count of sales orders matching the criteria
        """
        # Query with a wider range to account for timezone issues, then filter in Python
        # Odoo stores datetimes in UTC, but we need to filter by GMT+3 dates
        gmt3_offset_hours = 3
        # Start: beginning of start_date minus 1 day and 3 hours to be safe
        start_dt = datetime.combine(start_date - timedelta(days=1), datetime.min.time()) - timedelta(hours=gmt3_offset_hours)
        # End: beginning of end_date + 2 days (exclusive comparison)
        end_dt = datetime.combine(end_date + timedelta(days=2), datetime.min.time())
        
        domain = self._sales_order_dashboard_odoo_domain(
            start_dt.isoformat(sep=" "),
            end_dt.isoformat(sep=" "),
        )

        orders = self.odoo_client.search_read_all(
            model="sale.order",
            domain=domain,
            fields=["date_order"],
        )
        filtered = self._filter_orders_by_date_order_month(orders, start_date, end_date)
        return len(filtered)

    def _get_sales_order_details(self, start_date: date, end_date: date) -> list:
        """Get detailed sales order information for debugging.
        
        Returns list of orders with name, date, total, and project details.
        """
        # Query with a wider range to account for timezone issues, then filter in Python
        # Odoo stores datetimes in UTC, but we need to filter by GMT+3 dates
        gmt3_offset_hours = 3
        # Start: beginning of start_date minus 1 day and 3 hours to be safe
        start_dt = datetime.combine(start_date - timedelta(days=1), datetime.min.time()) - timedelta(hours=gmt3_offset_hours)
        # End: beginning of end_date + 2 days (exclusive comparison)
        end_dt = datetime.combine(end_date + timedelta(days=2), datetime.min.time())
        
        domain = self._sales_order_dashboard_odoo_domain(
            start_dt.isoformat(sep=" "),
            end_dt.isoformat(sep=" "),
        )

        fields = [
            "name",
            "date_order",
            "x_studio_aed_total",
            "project_id",
            "state",
            "order_line",
        ]
        
        orders = self.odoo_client.search_read_all(
            model="sale.order",
            domain=domain,
            fields=fields,
        )
        
        filtered_orders = self._filter_orders_by_date_order_month(orders, start_date, end_date)
        
        self._enrich_sales_orders(filtered_orders)
        self._calculate_external_hours_for_orders(filtered_orders)
        self._calculate_internal_hours_for_orders(filtered_orders, start_date, end_date)

        return filtered_orders

    def _get_sales_order_details_for_external_hours(self, start_date: date, end_date: date) -> list:
        """Orders counted toward Ext. Hrs SOLD from SO lines — date = Order Date SOL v1 on lines."""
        gmt3_offset_hours = 3
        start_dt = datetime.combine(start_date - timedelta(days=1), datetime.min.time()) - timedelta(
            hours=gmt3_offset_hours
        )
        end_dt = datetime.combine(end_date + timedelta(days=2), datetime.min.time())

        domain = self._sales_order_dashboard_odoo_domain_external_hours_sol(
            start_dt.isoformat(sep=" "),
            end_dt.isoformat(sep=" "),
        )
        fields = [
            "name",
            "date_order",
            "x_studio_aed_total",
            "project_id",
            "state",
            "order_line",
        ]
        orders = self.odoo_client.search_read_all(
            model="sale.order",
            domain=domain,
            fields=fields,
        )
        filtered_orders = self._filter_orders_by_sol_line_month(
            orders,
            start_date,
            end_date,
            EXTERNAL_HOURS_SOL_LINE_DATETIME_FIELD,
        )
        self._enrich_sales_orders(filtered_orders)
        self._calculate_external_hours_for_orders(filtered_orders)
        return filtered_orders

    def _enrich_sales_orders(self, orders: List[Dict[str, Any]]) -> None:
        """Fetch and attach project details to sales orders."""
        if not orders:
            return
            
        # Collect project IDs
        project_ids = set()
        for order in orders:
            project_field = order.get("project_id")
            if isinstance(project_field, (list, tuple)) and len(project_field) >= 1:
                project_ids.add(project_field[0])
        
        # Fetch project details
        projects = self._fetch_projects(project_ids)
        
        # Map details back to orders
        for order in orders:
            # Default values
            order["project_name"] = "Unassigned Project"
            order["market"] = "Unassigned Market"
            order["agreement_type"] = "Unknown"
            order["tags"] = []
            
            project_field = order.get("project_id")
            if isinstance(project_field, (list, tuple)) and len(project_field) >= 1:
                project_id = project_field[0]
                found_project = projects.get(project_id)
                
                if found_project:
                    order["project_name"] = found_project.get("name", "Unassigned Project")
                    order["market"] = self._market_label(found_project)
                    order["agreement_type"] = self._format_agreement_type(found_project)
                    order["tags"] = self._project_tags(found_project)

    def _calculate_external_hours_for_orders(self, orders: List[Dict[str, Any]]) -> None:
        """Calculate external hours for sales orders by summing order line quantities where UoM = Hours.
        
        For each sales order:
        1. Get all order lines
        2. Filter lines where product_uom = "Hours"
        3. Sum product_uom_qty for those lines
        4. Add external_hours to the order
        
        Args:
            orders: List of sales order dictionaries to enrich with external_hours
        """
        if not orders:
            return
        
        # Collect all order line IDs from all orders
        order_line_ids = []
        order_to_lines_map = {}  # Map order_id -> list of order_line_ids
        
        for order in orders:
            order_id = order.get("id")
            if not isinstance(order_id, int):
                continue
                
            order_line_field = order.get("order_line")
            if not order_line_field:
                order_to_lines_map[order_id] = []
                continue
            
            # Handle both list of IDs and list of tuples (id, name)
            line_ids = []
            if isinstance(order_line_field, list):
                for item in order_line_field:
                    if isinstance(item, int):
                        line_ids.append(item)
                    elif isinstance(item, (list, tuple)) and len(item) >= 1:
                        line_id = item[0]
                        if isinstance(line_id, int):
                            line_ids.append(line_id)
            
            order_to_lines_map[order_id] = line_ids
            order_line_ids.extend(line_ids)
        
        if not order_line_ids:
            # No order lines, set external_hours to 0 for all orders
            for order in orders:
                order["external_hours"] = 0.0
            return
        
        # Fetch all order lines in batch
        try:
            order_lines = self.odoo_client.read(
                "sale.order.line",
                order_line_ids,
                ["id", "product_uom", "product_uom_qty"]
            )
        except Exception as e:
            print(f"Error fetching order lines for external hours calculation: {e}")
            # On error, set external_hours to 0 for all orders
            for order in orders:
                order["external_hours"] = 0.0
            return
        
        # Create a map of order_line_id -> order_line data
        order_line_map = {}
        for line in order_lines:
            line_id = line.get("id")
            if isinstance(line_id, int):
                order_line_map[line_id] = line
        
        # Calculate external hours for each order
        for order in orders:
            order_id = order.get("id")
            if not isinstance(order_id, int):
                order["external_hours"] = 0.0
                continue
            
            line_ids = order_to_lines_map.get(order_id, [])
            external_hours_total = 0.0
            
            for line_id in line_ids:
                line_data = order_line_map.get(line_id)
                if not line_data:
                    continue
                
                # Check if UoM is "Hours"
                product_uom_field = line_data.get("product_uom")
                
                # Handle different formats: tuple (id, name) or string
                is_hours_uom = False
                if isinstance(product_uom_field, (list, tuple)) and len(product_uom_field) >= 2:
                    uom_name = str(product_uom_field[1]).strip().lower()
                    is_hours_uom = uom_name == "hours"
                elif isinstance(product_uom_field, str):
                    uom_name = product_uom_field.strip().lower()
                    is_hours_uom = uom_name == "hours"
                
                if is_hours_uom:
                    # Get quantity
                    quantity = line_data.get("product_uom_qty")
                    if quantity:
                        try:
                            qty_value = float(quantity)
                            if qty_value > 0:
                                external_hours_total += qty_value
                        except (ValueError, TypeError):
                            pass
            
            order["external_hours"] = external_hours_total

    def _calculate_internal_hours_for_orders(
        self, 
        orders: List[Dict[str, Any]], 
        month_start: date, 
        month_end: date
    ) -> None:
        """Calculate internal hours for sales orders by summing unit_amount from account.analytic.line.
        
        All analytic line hours linked to a sales order line contribute to that order
        as long as the sales order itself is within the viewed month (orders are already
        filtered before this method).
        
        Args:
            orders: List of sales order dictionaries to enrich with internal_hours
            month_start: Start date of the month (not used for filtering analytic lines)
            month_end: End date of the month (not used for filtering analytic lines)
        """
        if not orders:
            return
        
        # Normalize order lines for each order and map sale order line -> order id
        order_line_ids: List[int] = []
        line_to_order: Dict[int, int] = {}
        order_hours_map: Dict[int, float] = {}
        
        for order in orders:
            order_id = order.get("id")
            if isinstance(order_id, int):
                order_hours_map[order_id] = 0.0
            order["internal_hours"] = 0.0  # default
            
            if not isinstance(order_id, int):
                continue
            
            lines_field = order.get("order_line") or []
            for line in lines_field:
                line_id = None
                if isinstance(line, int):
                    line_id = line
                elif isinstance(line, (list, tuple)) and len(line) >= 1 and isinstance(line[0], int):
                    line_id = line[0]
                
                if line_id is None:
                    continue
                
                order_line_ids.append(line_id)
                line_to_order[line_id] = order_id
        
        if not order_line_ids:
            return
        
        try:
            domain = [
                ("so_line", "in", list(set(order_line_ids))),
            ]
            fields = ["so_line", "unit_amount"]
            
            for batch in self.odoo_client.search_read_chunked(
                "account.analytic.line",
                domain=domain,
                fields=fields,
            ):
                for record in batch:
                    so_line_field = record.get("so_line")
                    so_line_id = None
                    if isinstance(so_line_field, (list, tuple)) and len(so_line_field) >= 1:
                        candidate = so_line_field[0]
                        if isinstance(candidate, int):
                            so_line_id = candidate
                    elif isinstance(so_line_field, int):
                        so_line_id = so_line_field
                    
                    if so_line_id is None:
                        continue
                    
                    order_id = line_to_order.get(so_line_id)
                    if order_id is None:
                        continue
                    
                    unit_amount = record.get("unit_amount")
                    try:
                        hours = float(unit_amount or 0.0)
                    except (TypeError, ValueError):
                        hours = 0.0
                    
                    if hours <= 0:
                        continue
                    
                    order_hours_map[order_id] = order_hours_map.get(order_id, 0.0) + hours
            
            for order in orders:
                order_id = order.get("id")
                if isinstance(order_id, int):
                    order["internal_hours"] = order_hours_map.get(order_id, 0.0)
        except Exception as e:
            print(f"Error fetching internal hours for sales orders: {e}")

    def get_monthly_sales_orders_series(
        self,
        year: int,
        upto_month: int,
        cache_service: Optional['SalesCacheService'] = None,
        include_previous_year: bool = True
    ) -> List[Dict[str, Any]]:
        """Get monthly Sales Orders totals for the year up to the specified month.
        
        Args:
            year: The year to fetch data for
            upto_month: The last month to include (1-12)
            cache_service: Optional cache service to use
            include_previous_year: If True, also fetch previous year data for comparison
            
        Returns:
            List of dictionaries with month, label, amount_aed, and optionally previous_year_amount_aed
        """
        series = []
        previous_year = year - 1
        
        for month in range(1, upto_month + 1):
            amount = 0.0
            previous_amount = 0.0
            
            # Logic:
            # 1. If current month (or future), ALWAYS fetch from Odoo and update cache
            # 2. If past month:
            #    a. Check cache
            #    b. If in cache, use it
            #    c. If not in cache, fetch from Odoo and save to cache
            
            is_current_month = (year == date.today().year and month == date.today().month)
            month_start = date(year, month, 1)
            _, last_day = monthrange(year, month)
            month_end = date(year, month, last_day)

            # Fetch current year data
            cached_data = None
            if cache_service and not is_current_month:
                cached_data = cache_service.get_sales_order_month_data(year, month)
                # Provisional rows (written before the month settled) are
                # dropped so the month recomputes and re-caches with a
                # post-close timestamp — see services/cache_finality.py.
                if cached_data and not cached_month_rows_are_final(
                    [cached_data], month_end, SALES_CACHE_FINALIZE_GRACE_DAYS
                ):
                    cached_data = None

            if cached_data:
                amount = float(cached_data.get("total_amount_aed", 0.0))
            else:
                # Fetch from Odoo
                # Get total Sales Orders amount
                amount = self._get_monthly_sales_orders_total_from_odoo(month_start, month_end)
                
                # Update cache
                if cache_service:
                    cache_service.save_sales_order_month_data(year, month, amount)
            
            # For current month, always update cache with fresh data
            if is_current_month and cache_service:
                cache_service.save_sales_order_month_data(year, month, amount)

            # Fetch previous year data if requested
            if include_previous_year:
                prev_month_start = date(previous_year, month, 1)
                _, prev_last_day = monthrange(previous_year, month)
                prev_month_end = date(previous_year, month, prev_last_day)

                previous_cached_data = None
                if cache_service:
                    previous_cached_data = cache_service.get_sales_order_month_data(previous_year, month)
                    if previous_cached_data and not cached_month_rows_are_final(
                        [previous_cached_data], prev_month_end, SALES_CACHE_FINALIZE_GRACE_DAYS
                    ):
                        previous_cached_data = None

                if previous_cached_data:
                    previous_amount = float(previous_cached_data.get("total_amount_aed", 0.0))
                else:
                    # Fetch from Odoo

                    previous_amount = self._get_monthly_sales_orders_total_from_odoo(prev_month_start, prev_month_end)
                    
                    # Update cache
                    if cache_service:
                        cache_service.save_sales_order_month_data(previous_year, month, previous_amount)

            series_item = {
                "year": year,
                "month": month,
                "label": date(year, month, 1).strftime("%b"),
                "amount_aed": amount,
                "amount_display": f"AED {amount:,.2f}",
            }
            
            if include_previous_year:
                series_item["previous_year"] = previous_year
                series_item["previous_year_amount_aed"] = previous_amount
                series_item["previous_year_amount_display"] = f"AED {previous_amount:,.2f}"
            
            series.append(series_item)
            
        return series

    def get_monthly_sales_orders_series_with_breakdown(
        self,
        year: int,
        upto_month: int,
        cache_service: Optional['SalesCacheService'] = None,
        include_previous_year: bool = True
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Return sales orders series plus per-month breakdowns (market/agreement/account)."""
        series_only = self.get_monthly_sales_orders_series(
            year, upto_month, cache_service=cache_service, include_previous_year=include_previous_year
        )

        if not cache_service:
            return series_only, []

        years_to_fetch = [year]
        previous_year = year - 1
        if include_previous_year:
            years_to_fetch.append(previous_year)

        breakdown_by_year: Dict[int, List[Dict[str, Any]]] = {}
        for yr in years_to_fetch:
            breakdown_by_year[yr] = cache_service.get_sales_order_breakdown_year(yr)

        current_date = date.today()

        for yr in years_to_fetch:
            months_needed = range(1, upto_month + 1)

            year_rows = breakdown_by_year.get(yr, [])

            def _remove_month(rows: List[Dict[str, Any]], month_val: int) -> List[Dict[str, Any]]:
                return [r for r in rows if not (r.get("year") == yr and r.get("month") == month_val)]

            for month in months_needed:
                is_current_month = (yr == current_date.year and month == current_date.month)
                month_start = date(yr, month, 1)
                _, last_day = monthrange(yr, month)
                month_end = date(yr, month, last_day)
                month_rows = [
                    r for r in year_rows
                    if r.get("year") == yr and r.get("month") == month
                ]

                # Refresh rule: always refresh current month of current year;
                # otherwise fill when missing OR when the cached rows are
                # provisional (written before the month settled).
                if (
                    month_rows
                    and not is_current_month
                    and cached_month_rows_are_final(
                        month_rows, month_end, SALES_CACHE_FINALIZE_GRACE_DAYS
                    )
                ):
                    continue

                month_breakdown = self._build_sales_orders_breakdown(month_start, month_end, yr, month)

                if month_breakdown:
                    year_rows = _remove_month(year_rows, month) + month_breakdown
                    cache_service.upsert_sales_order_breakdown(month_breakdown)
                elif is_current_month:
                    year_rows = _remove_month(year_rows, month)

            breakdown_by_year[yr] = year_rows

        all_rows: List[Dict[str, Any]] = []
        for yr in years_to_fetch:
            for row in breakdown_by_year.get(yr, []):
                m = row.get("month", 0)
                if 1 <= m <= upto_month:
                    all_rows.append(row)

        all_rows.sort(
            key=lambda r: (
                r.get("year", 0),
                r.get("month", 0),
                r.get("market") or "",
                r.get("agreement_type") or "",
                r.get("account_type") or "",
            )
        )

        return series_only, all_rows

    def _get_monthly_sales_orders_total_from_odoo(self, start_date: date, end_date: date) -> float:
        """Calculate total Sales Orders amount in AED for a date range from Odoo.
        
        Args:
            start_date: Start of date range
            end_date: End of date range
            
        Returns:
            Total AED amount
        """
        # Query with a wider range to account for timezone issues, then filter in Python
        # Odoo stores datetimes in UTC, but we need to filter by GMT+3 dates
        # Query from start_date - 1 day to end_date + 1 day to ensure we capture everything
        gmt3_offset_hours = 3
        # Start: beginning of start_date minus 1 day and 3 hours to be safe
        start_dt = datetime.combine(start_date - timedelta(days=1), datetime.min.time()) - timedelta(hours=gmt3_offset_hours)
        # End: beginning of end_date + 2 days (exclusive comparison)
        end_dt = datetime.combine(end_date + timedelta(days=2), datetime.min.time())
        
        domain = self._sales_order_dashboard_odoo_domain(
            start_dt.isoformat(sep=" "),
            end_dt.isoformat(sep=" "),
        )
        
        fields = ["x_studio_aed_total", "date_order"]
        orders = self.odoo_client.search_read_all(
            model="sale.order",
            domain=domain,
            fields=fields,
        )

        filtered = self._filter_orders_by_date_order_month(orders, start_date, end_date)
        total = 0.0
        for order in filtered:
            val = order.get("x_studio_aed_total")
            if val:
                try:
                    total += float(val)
                except (ValueError, TypeError):
                    pass

        return total

    def get_sales_orders_totals_by_agreement_type(
        self,
        month_start: date,
        month_end: date,
    ) -> Dict[str, float]:
        """Get total Sales Orders amounts grouped by agreement type for the selected month.
        
        Args:
            month_start: First day of the month
            month_end: Last day of the month
            
        Returns:
            Dictionary with agreement types as keys and total AED amounts as values.
            Keys: "Retainer", "Framework", "Ad Hoc", "Unknown"
        """
        # Get sales order details (already includes project details with agreement_type)
        orders = self._get_sales_order_details(month_start, month_end)
        
        # Initialize totals for each agreement type
        totals = {
            "Retainer": 0.0,
            "Framework": 0.0,
            "Ad Hoc": 0.0,
            "Unknown": 0.0,
        }
        
        # Process each order
        for order in orders:
            agreement_type = order.get("agreement_type", "Unknown")
            tags = order.get("tags", [])
            
            # Categorize agreement type
            category = self._categorize_agreement_type(agreement_type, tags)
            
            # Get order amount
            aed_total = order.get("x_studio_aed_total")
            amount = 0.0
            if aed_total:
                try:
                    amount = float(aed_total)
                except (ValueError, TypeError):
                    pass
            
            # Add to appropriate category
            totals[category] += amount
        
        return totals

    def get_sales_orders_totals_by_project(
        self,
        month_start: date,
        month_end: date,
        top_n: int = 5,
    ) -> List[Dict[str, Any]]:
        """Get top N Sales Orders totals grouped by project for the selected month.
        
        Args:
            month_start: First day of the month
            month_end: Last day of the month
            top_n: Number of top projects to return (default: 5)
            
        Returns:
            List of dictionaries with project_name and total_amount_aed, sorted by amount descending.
            Excludes "Unassigned Project".
        """
        # Get sales order details (already includes project details)
        orders = self._get_sales_order_details(month_start, month_end)
        
        # Aggregate totals by project
        project_totals: Dict[str, float] = {}
        
        # Process each order
        for order in orders:
            project_name = order.get("project_name", "Unassigned Project")
            
            # Skip Unassigned Project
            if project_name == "Unassigned Project":
                continue
            
            # Get order amount
            aed_total = order.get("x_studio_aed_total")
            amount = 0.0
            if aed_total:
                try:
                    amount = float(aed_total)
                except (ValueError, TypeError):
                    pass
            
            # Add to project total
            if project_name not in project_totals:
                project_totals[project_name] = 0.0
            project_totals[project_name] += amount
        
        # Sort by total amount descending and take top N
        sorted_projects = sorted(
            project_totals.items(),
            key=lambda x: x[1],
            reverse=True
        )[:top_n]
        
        # Convert to list of dictionaries
        result = [
            {
                "project_name": project_name,
                "total_amount_aed": total_amount,
            }
            for project_name, total_amount in sorted_projects
        ]
        
        return result
