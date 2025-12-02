"""Sales statistics service for invoice data."""
from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional, Tuple, Iterable, List
import re

from ..integrations.odoo_client import OdooClient


class SalesService:
    """Calculate sales statistics from Odoo invoices."""

    def __init__(self, odoo_client: OdooClient):
        self.odoo_client = odoo_client
        self._project_cache: Dict[int, Dict[str, Any]] = {}
        self._agreement_cache: Dict[int, str] = {}
        self._tag_cache: Dict[int, str] = {}

    def calculate_sales_statistics(
        self,
        month_start: date,
        month_end: date,
    ) -> Dict[str, Any]:
        """Calculate sales statistics for the selected month.
        
        Args:
            month_start: First day of the month
            month_end: Last day of the month
            
        Returns:
            Dictionary with sales metrics:
            - invoice_count: Total number of invoices for the month
            - comparison: Month-over-month comparison data
            - invoices: List of invoice details for debugging
        """
        # Get current month invoices
        current_count = self._get_invoice_count(month_start, month_end)
        invoice_details = self._get_invoice_details(month_start, month_end)
        
        # Get current month sales orders
        sales_order_count = self._get_sales_order_count(month_start, month_end)
        sales_order_details = self._get_sales_order_details(month_start, month_end)
        
        # Get previous month for comparison
        previous_bounds = self._previous_month_bounds(month_start)
        comparison = None
        sales_order_comparison = None
        
        if previous_bounds:
            prev_start, prev_end = previous_bounds
            previous_count = self._get_invoice_count(prev_start, prev_end)
            comparison = self._calculate_comparison(current_count, previous_count)
            
            previous_so_count = self._get_sales_order_count(prev_start, prev_end)
            sales_order_comparison = self._calculate_comparison(sales_order_count, previous_so_count)
        
        return {
            "invoice_count": current_count,
            "comparison": comparison,
            "invoices": invoice_details,
            "sales_order_count": sales_order_count,
            "sales_order_comparison": sales_order_comparison,
            "sales_orders": sales_order_details,
        }

    def _get_invoice_count(self, start_date: date, end_date: date) -> int:
        """Get count of invoices for a date range with filters applied.
        
        Filters:
        - move_type in ["out_invoice"] (Customer Invoice)
        - payment_state not in ["reversed"]
        - partner_id != 10 (Prezlab Digital Design Firm L.L.C - O.P.C)
        - invoice_date within date range
        
        Args:
            start_date: Start of date range (inclusive)
            end_date: End of date range (inclusive)
            
        Returns:
            Count of invoices matching the criteria
        """
        # Build Odoo domain filter
        domain = [
            "&", "&", "&",
            ("move_type", "in", ["out_invoice"]),
            ("payment_state", "not in", ["reversed"]),
            ("partner_id", "not in", [10]),
            "&",
            ("invoice_date", ">=", start_date.isoformat()),
            ("invoice_date", "<=", end_date.isoformat()),
        ]
        
        # Search for invoice IDs matching the criteria
        invoice_ids = self.odoo_client.search(
            model="account.move",
            domain=domain,
        )
        
        return len(invoice_ids)

    def _get_invoice_details(self, start_date: date, end_date: date) -> list:
        """Get detailed invoice information for debugging.
        
        Returns list of invoices with name, date, partner, state, payment_state, move_type,
        and project details (Market, Agreement, Tags, AED Total).
        """
        # Build Odoo domain filter
        domain = [
            "&", "&", "&",
            ("move_type", "in", ["out_invoice"]),
            ("payment_state", "not in", ["reversed"]),
            ("partner_id", "not in", [10]),
            "&",
            ("invoice_date", ">=", start_date.isoformat()),
            ("invoice_date", "<=", end_date.isoformat()),
        ]
        
        # Fetch invoice details including invoice_line_ids and x_studio_aed_total
        invoices = self.odoo_client.search_read_all(
            model="account.move",
            domain=domain,
            fields=[
                "name", 
                "invoice_date", 
                "partner_id", 
                "state", 
                "payment_state", 
                "move_type",
                "invoice_line_ids",
                "x_studio_aed_total"
            ],
        )
        
        # Enrich invoices with project details
        self._fetch_project_details(invoices)
        
        return invoices

    def _fetch_project_details(self, invoices: List[Dict[str, Any]]) -> None:
        """Fetch and attach project details to invoices.
        
        Traverses: Invoice -> Invoice Lines -> Sale Lines -> Order -> Project
        """
        # 1. Collect all invoice line IDs
        invoice_line_ids = set()
        for invoice in invoices:
            lines = invoice.get("invoice_line_ids") or []
            for line_id in lines:
                if isinstance(line_id, int):
                    invoice_line_ids.add(line_id)
        
        if not invoice_line_ids:
            return

        # 2. Fetch invoice lines to get sale_line_ids
        invoice_lines = self.odoo_client.read(
            "account.move.line", 
            list(invoice_line_ids), 
            ["sale_line_ids"]
        )
        invoice_line_map = {line["id"]: line for line in invoice_lines}

        # 3. Collect sale line IDs
        sale_line_ids = set()
        for line in invoice_lines:
            s_lines = line.get("sale_line_ids") or []
            for s_id in s_lines:
                if isinstance(s_id, int):
                    sale_line_ids.add(s_id)
        
        if not sale_line_ids:
            return

        # 4. Fetch sale lines to get order_id
        sale_lines = self.odoo_client.read(
            "sale.order.line", 
            list(sale_line_ids), 
            ["order_id"]
        )
        sale_line_map = {line["id"]: line for line in sale_lines}

        # 5. Collect order IDs
        order_ids = set()
        for line in sale_lines:
            order_field = line.get("order_id")
            if isinstance(order_field, (list, tuple)) and len(order_field) >= 1:
                order_ids.add(order_field[0])
        
        if not order_ids:
            return

        # 6. Fetch orders to get project_id
        orders = self.odoo_client.read(
            "sale.order", 
            list(order_ids), 
            ["project_id"]
        )
        order_map = {order["id"]: order for order in orders}

        # 7. Collect project IDs
        project_ids = set()
        for order in orders:
            project_field = order.get("project_id")
            if isinstance(project_field, (list, tuple)) and len(project_field) >= 1:
                project_ids.add(project_field[0])
        
        # 8. Fetch project details
        projects = self._fetch_projects(project_ids)

        # 9. Map details back to invoices
        for invoice in invoices:
            # Default values
            invoice["project_name"] = "Unassigned Project"
            invoice["market"] = "Unassigned Market"
            invoice["agreement_type"] = "Unknown"
            invoice["tags"] = []
            
            # Find linked project
            found_project = None
            inv_lines = invoice.get("invoice_line_ids") or []
            
            # Traverse back to find project
            for line_id in inv_lines:
                if found_project:
                    break
                line = invoice_line_map.get(line_id)
                if not line:
                    continue
                
                s_lines = line.get("sale_line_ids") or []
                for s_id in s_lines:
                    if found_project:
                        break
                    s_line = sale_line_map.get(s_id)
                    if not s_line:
                        continue
                    
                    order_field = s_line.get("order_id")
                    if isinstance(order_field, (list, tuple)) and len(order_field) >= 1:
                        order = order_map.get(order_field[0])
                        if order:
                            project_field = order.get("project_id")
                            if isinstance(project_field, (list, tuple)) and len(project_field) >= 2:
                                project_id = project_field[0]
                                found_project = projects.get(project_id)
            
            if found_project:
                invoice["project_name"] = found_project.get("name", "Unassigned Project")
                invoice["market"] = self._market_label(found_project)
                invoice["agreement_type"] = self._format_agreement_type(found_project)
                invoice["agreement_type"] = self._format_agreement_type(found_project)
                invoice["tags"] = self._project_tags(found_project)

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
        
        domain = [
            "&", "&",
            ("state", "=", "sale"),
            ("date_order", ">=", start_dt.isoformat(sep=" ")),
            ("date_order", "<", end_dt.isoformat(sep=" ")),
        ]
        
        # Fetch orders with date_order field to filter by GMT+3 date
        orders = self.odoo_client.search_read_all(
            model="sale.order",
            domain=domain,
            fields=["date_order"],
        )
        
        # Filter orders by converting UTC date_order to GMT+3 and checking if date matches
        count = 0
        gmt3_offset = timedelta(hours=gmt3_offset_hours)
        
        for order in orders:
            date_order_str = order.get("date_order")
            if not date_order_str:
                continue
                
            # Parse the datetime from Odoo (stored in UTC)
            try:
                # Handle different datetime formats from Odoo
                if isinstance(date_order_str, str):
                    # Remove timezone info if present and parse
                    date_order_str_clean = date_order_str.replace("T", " ").split(".")[0]
                    order_dt_utc = datetime.strptime(date_order_str_clean, "%Y-%m-%d %H:%M:%S")
                elif isinstance(date_order_str, datetime):
                    order_dt_utc = date_order_str
                else:
                    continue
                
                # Convert UTC to GMT+3
                order_dt_gmt3 = order_dt_utc + gmt3_offset
                order_date_gmt3 = order_dt_gmt3.date()
                
                # Check if order date (in GMT+3) falls within our range
                if start_date <= order_date_gmt3 <= end_date:
                    count += 1
            except (ValueError, TypeError, AttributeError):
                # If parsing fails, skip this order
                continue
        
        return count

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
        
        domain = [
            "&", "&",
            ("state", "=", "sale"),
            ("date_order", ">=", start_dt.isoformat(sep=" ")),
            ("date_order", "<", end_dt.isoformat(sep=" ")),
        ]
        
        fields = [
            "name",
            "date_order",
            "x_studio_aed_total",
            "project_id",
            "state",
        ]
        
        orders = self.odoo_client.search_read_all(
            model="sale.order",
            domain=domain,
            fields=fields,
        )
        
        # Filter orders by converting UTC date_order to GMT+3 and checking if date matches
        gmt3_offset = timedelta(hours=3)
        filtered_orders = []
        
        for order in orders:
            date_order_str = order.get("date_order")
            if not date_order_str:
                continue
                
            # Parse the datetime from Odoo (stored in UTC)
            try:
                # Handle different datetime formats from Odoo
                if isinstance(date_order_str, str):
                    # Remove timezone info if present and parse
                    date_order_str_clean = date_order_str.replace("T", " ").split(".")[0]
                    order_dt_utc = datetime.strptime(date_order_str_clean, "%Y-%m-%d %H:%M:%S")
                elif isinstance(date_order_str, datetime):
                    order_dt_utc = date_order_str
                else:
                    continue
                
                # Convert UTC to GMT+3
                order_dt_gmt3 = order_dt_utc + gmt3_offset
                order_date_gmt3 = order_dt_gmt3.date()
                
                # Check if order date (in GMT+3) falls within our range
                if start_date <= order_date_gmt3 <= end_date:
                    filtered_orders.append(order)
            except (ValueError, TypeError, AttributeError):
                # If parsing fails, skip this order
                continue
        
        self._enrich_sales_orders(filtered_orders)
        
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

    def _fetch_projects(self, project_ids: Iterable[int]) -> Dict[int, Dict[str, Any]]:
        ids = [project_id for project_id in project_ids if isinstance(project_id, int)]
        if not ids:
            return {}
        
        missing = [pid for pid in ids if pid not in self._project_cache]
        if missing:
            fields = ["x_studio_market_2", "x_studio_agreement_type_1", "tag_ids", "name"]
            records = self.odoo_client.read("project.project", missing, fields)
            for record in records:
                if isinstance(record.get("id"), int):
                    self._project_cache[record["id"]] = record
        
        project_map = {pid: self._project_cache[pid] for pid in ids if pid in self._project_cache}
        
        # Fetch related tags and agreement types
        tag_ids = set()
        agreement_ids = set()
        for record in project_map.values():
            for tag_id in record.get("tag_ids") or []:
                if isinstance(tag_id, int):
                    tag_ids.add(tag_id)
            for ag_id in record.get("x_studio_agreement_type_1") or []:
                if isinstance(ag_id, int):
                    agreement_ids.add(ag_id)
        
        agreement_map = self._fetch_agreement_types(agreement_ids) if agreement_ids else {}
        tag_names = self._fetch_project_tags(tag_ids) if tag_ids else {}
        
        # Enrich projects with names
        for project in project_map.values():
            ids = project.get("tag_ids") or []
            project["tag_names"] = [tag_names.get(tid, f"Tag {tid}") for tid in ids if isinstance(tid, int)]
            
            raw_agreements = project.get("x_studio_agreement_type_1") or []
            agreement_names = [agreement_map.get(aid, f"Agreement {aid}") for aid in raw_agreements if isinstance(aid, int)]
            project["agreement_type_names"] = [name for name in agreement_names if name]
            
        return project_map

    def _fetch_agreement_types(self, type_ids: Iterable[int]) -> Dict[int, str]:
        ids = [tid for tid in type_ids if isinstance(tid, int)]
        if not ids:
            return {}
        
        missing = [tid for tid in ids if tid not in self._agreement_cache]
        if missing:
            records = self.odoo_client.read("x_agreement_type", missing, ["display_name", "x_name"])
            for record in records:
                tid = record.get("id")
                if isinstance(tid, int):
                    name = record.get("display_name") or record.get("x_name")
                    self._agreement_cache[tid] = self._safe_str(name, default=f"Agreement {tid}")
        
        return {tid: self._agreement_cache[tid] for tid in ids if tid in self._agreement_cache}

    def _fetch_project_tags(self, tag_ids: Iterable[int]) -> Dict[int, str]:
        ids = [tid for tid in tag_ids if isinstance(tid, int)]
        if not ids:
            return {}
        
        missing = [tid for tid in ids if tid not in self._tag_cache]
        if missing:
            tags = self.odoo_client.read("project.tags", missing, ["name"])
            for tag in tags:
                tid = tag.get("id")
                if isinstance(tid, int):
                    self._tag_cache[tid] = str(tag.get("name", ""))
        
        return {tid: self._tag_cache.get(tid, f"Tag {tid}") for tid in ids if tid in self._tag_cache}

    def _market_label(self, project: Optional[Dict[str, Any]]) -> str:
        if not project:
            return "Unassigned Market"
        raw = project.get("x_studio_market_2")
        if isinstance(raw, (list, tuple)) and len(raw) >= 2:
            return self._safe_str(raw[1], default="Unassigned Market")
        return self._safe_str(raw, default="Unassigned Market")

    def _format_agreement_type(self, project: Optional[Dict[str, Any]]) -> str:
        if not project:
            return "Unknown"
        names = project.get("agreement_type_names")
        if isinstance(names, list):
            cleaned = [self._safe_str(name).strip() for name in names if isinstance(name, str)]
            cleaned = [name for name in cleaned if name]
            if cleaned:
                return ", ".join(cleaned)
        return "Unknown"

    def _project_tags(self, project: Optional[Dict[str, Any]]) -> List[str]:
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

    def _previous_month_bounds(self, current_month_start: date) -> Optional[Tuple[date, date]]:
        """Return the start and end dates for the previous month.
        
        Args:
            current_month_start: First day of current month
            
        Returns:
            Tuple of (prev_month_start, prev_month_end) or None
        """
        if current_month_start.month == 1:
            prev_month = date(current_month_start.year - 1, 12, 1)
        else:
            prev_month = date(current_month_start.year, current_month_start.month - 1, 1)
        
        _, last_day = monthrange(prev_month.year, prev_month.month)
        prev_end = date(prev_month.year, prev_month.month, last_day)
        
        return prev_month, prev_end

    def _calculate_comparison(self, current: int, previous: int) -> Optional[Dict[str, Any]]:
        """Calculate comparison between current and previous month counts.
        
        Args:
            current: Current month count
            previous: Previous month count
            
        Returns:
            Dictionary with change_percentage and trend, or None if no comparison
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


    def get_monthly_invoiced_series(
        self,
        year: int,
        upto_month: int,
        cache_service: Optional['SalesCacheService'] = None,
        include_previous_year: bool = True
    ) -> List[Dict[str, Any]]:
        """Get monthly invoiced totals for the year up to the specified month.
        
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
            
            # Fetch current year data
            cached_data = None
            invoices_total = None
            credit_notes_total = None
            reversed_total = None
            
            if cache_service and not is_current_month:
                cached_data = cache_service.get_month_data(year, month)
            
            if cached_data:
                amount = float(cached_data.get("amount_aed", 0.0))
            else:
                # Fetch from Odoo (for both current and past months)
                month_start = date(year, month, 1)
                _, last_day = monthrange(year, month)
                month_end = date(year, month, last_day)
                
                # Calculate components and total
                invoices_total = self._get_invoices_total(month_start, month_end)
                credit_notes_total = self._get_credit_notes_total(month_start, month_end)
                reversed_total = self._get_reversed_total(month_start, month_end)
                amount = invoices_total - credit_notes_total + reversed_total
                
                # Update cache with component breakdown
                if cache_service:
                    cache_service.save_month_data(
                        year, month, amount,
                        invoices_total=invoices_total,
                        credit_notes_total=credit_notes_total,
                        reversed_total=reversed_total
                    )

            # Fetch previous year data if requested
            if include_previous_year:
                previous_cached_data = None
                if cache_service:
                    previous_cached_data = cache_service.get_month_data(previous_year, month)
                
                if previous_cached_data:
                    previous_amount = float(previous_cached_data.get("amount_aed", 0.0))
                else:
                    # Fetch from Odoo
                    prev_month_start = date(previous_year, month, 1)
                    _, prev_last_day = monthrange(previous_year, month)
                    prev_month_end = date(previous_year, month, prev_last_day)
                    
                    # Calculate components and total for previous year
                    prev_invoices_total = self._get_invoices_total(prev_month_start, prev_month_end)
                    prev_credit_notes_total = self._get_credit_notes_total(prev_month_start, prev_month_end)
                    prev_reversed_total = self._get_reversed_total(prev_month_start, prev_month_end)
                    previous_amount = prev_invoices_total - prev_credit_notes_total + prev_reversed_total
                    
                    # Update cache
                    if cache_service:
                        cache_service.save_month_data(
                            previous_year, month, previous_amount,
                            invoices_total=prev_invoices_total,
                            credit_notes_total=prev_credit_notes_total,
                            reversed_total=prev_reversed_total
                        )

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

    def _get_monthly_total_from_odoo(self, start_date: date, end_date: date) -> float:
        """Calculate total invoiced amount in AED for a date range from Odoo.
        
        Formula: Total AED from invoices - Total AED from Credit Notes + Total Reserved Amount
        
        Args:
            start_date: Start of date range
            end_date: End of date range
            
        Returns:
            Total AED amount calculated as: invoices - credit_notes + reversed_amount
        """
        # Calculate each component
        invoices_total = self._get_invoices_total(start_date, end_date)
        credit_notes_total = self._get_credit_notes_total(start_date, end_date)
        reversed_total = self._get_reversed_total(start_date, end_date)
        
        # Apply formula: invoices - credit_notes + reversed
        total = invoices_total - credit_notes_total + reversed_total
        
        return total
    
    def _get_invoices_total(self, start_date: date, end_date: date) -> float:
        """Get total AED from invoices (out_invoice, not reversed, partner_id not 10).
        
        Args:
            start_date: Start of date range
            end_date: End of date range
            
        Returns:
            Total AED amount from invoices
        """
        domain = [
            "&", "&", "&",
            ("move_type", "in", ["out_invoice"]),
            ("payment_state", "not in", ["reversed"]),
            ("partner_id", "not in", [10]),
            "&",
            ("invoice_date", ">=", start_date.isoformat()),
            ("invoice_date", "<=", end_date.isoformat()),
        ]
        
        fields = ["x_studio_aed_total"]
        invoices = self.odoo_client.search_read_all(
            model="account.move",
            domain=domain,
            fields=fields,
        )
        
        total = 0.0
        for inv in invoices:
            val = inv.get("x_studio_aed_total")
            if val:
                try:
                    total += float(val)
                except (ValueError, TypeError):
                    pass
                    
        return total
    
    def _get_credit_notes_total(self, start_date: date, end_date: date) -> float:
        """Get total AED from credit notes (out_refund, not reversed, partner_id not 10).
        
        Credit notes are treated as negative amounts, so we sum their absolute values.
        
        Args:
            start_date: Start of date range
            end_date: End of date range
            
        Returns:
            Total AED amount from credit notes (as positive value, will be subtracted)
        """
        domain = [
            "&", "&", "&",
            ("move_type", "in", ["out_refund"]),  # Customer Credit Note
            ("payment_state", "not in", ["reversed"]),
            ("partner_id", "not in", [10]),
            "&",
            ("invoice_date", ">=", start_date.isoformat()),
            ("invoice_date", "<=", end_date.isoformat()),
        ]
        
        fields = ["x_studio_aed_total"]
        credit_notes = self.odoo_client.search_read_all(
            model="account.move",
            domain=domain,
            fields=fields,
        )
        
        total = 0.0
        for cn in credit_notes:
            val = cn.get("x_studio_aed_total")
            if val:
                try:
                    # Credit notes are typically negative, but we want the absolute value
                    # since we'll subtract it in the formula
                    total += abs(float(val))
                except (ValueError, TypeError):
                    pass
                    
        return total
    
    def _get_reversed_total(self, start_date: date, end_date: date) -> float:
        """Get total AED from reversed invoices (out_invoice, payment_state = reversed, partner_id not 10).
        
        Args:
            start_date: Start of date range
            end_date: End of date range
            
        Returns:
            Total AED amount from reversed invoices
        """
        domain = [
            "&", "&", "&",
            ("move_type", "in", ["out_invoice"]),
            ("payment_state", "=", "reversed"),
            ("partner_id", "not in", [10]),
            "&",
            ("invoice_date", ">=", start_date.isoformat()),
            ("invoice_date", "<=", end_date.isoformat()),
        ]
        
        fields = ["x_studio_aed_total"]
        reversed_invoices = self.odoo_client.search_read_all(
            model="account.move",
            domain=domain,
            fields=fields,
        )
        
        total = 0.0
        for inv in reversed_invoices:
            val = inv.get("x_studio_aed_total")
            if val:
                try:
                    total += float(val)
                except (ValueError, TypeError):
                    pass
                    
        return total

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
            
            # Fetch current year data
            cached_data = None
            if cache_service and not is_current_month:
                cached_data = cache_service.get_sales_order_month_data(year, month)
            
            if cached_data:
                amount = float(cached_data.get("total_amount_aed", 0.0))
            else:
                # Fetch from Odoo
                month_start = date(year, month, 1)
                _, last_day = monthrange(year, month)
                month_end = date(year, month, last_day)
                
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
                previous_cached_data = None
                if cache_service:
                    previous_cached_data = cache_service.get_sales_order_month_data(previous_year, month)
                
                if previous_cached_data:
                    previous_amount = float(previous_cached_data.get("total_amount_aed", 0.0))
                else:
                    # Fetch from Odoo
                    prev_month_start = date(previous_year, month, 1)
                    _, prev_last_day = monthrange(previous_year, month)
                    prev_month_end = date(previous_year, month, prev_last_day)
                    
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
        
        # Build Odoo domain filter for Sales Orders with state='sale'
        domain = [
            "&", "&",
            ("state", "=", "sale"),
            ("date_order", ">=", start_dt.isoformat(sep=" ")),
            ("date_order", "<", end_dt.isoformat(sep=" ")),
        ]
        
        # Fetch all sales orders with date_order field for filtering
        fields = ["x_studio_aed_total", "date_order"]
        orders = self.odoo_client.search_read_all(
            model="sale.order",
            domain=domain,
            fields=fields,
        )
        
        # Filter orders by converting UTC date_order to GMT+3 and checking if date matches
        total = 0.0
        gmt3_offset = timedelta(hours=gmt3_offset_hours)
        
        for order in orders:
            date_order_str = order.get("date_order")
            if not date_order_str:
                continue
                
            # Parse the datetime from Odoo (stored in UTC)
            try:
                # Handle different datetime formats from Odoo
                if isinstance(date_order_str, str):
                    # Remove timezone info if present and parse
                    date_order_str_clean = date_order_str.replace("T", " ").split(".")[0]
                    order_dt_utc = datetime.strptime(date_order_str_clean, "%Y-%m-%d %H:%M:%S")
                elif isinstance(date_order_str, datetime):
                    order_dt_utc = date_order_str
                else:
                    continue
                
                # Convert UTC to GMT+3
                order_dt_gmt3 = order_dt_utc + gmt3_offset
                order_date_gmt3 = order_dt_gmt3.date()
                
                # Check if order date (in GMT+3) falls within our range
                if start_date <= order_date_gmt3 <= end_date:
                    val = order.get("x_studio_aed_total")
                    if val:
                        try:
                            total += float(val)
                        except (ValueError, TypeError):
                            pass
            except (ValueError, TypeError, AttributeError):
                # If parsing fails, skip this order
                continue
                    
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

    def get_invoice_totals_by_agreement_type(
        self,
        month_start: date,
        month_end: date,
    ) -> Dict[str, float]:
        """Get total invoiced amounts grouped by agreement type for the selected month.
        
        Formula: invoices_total - credit_notes_total + reversed_total (per agreement type)
        
        Args:
            month_start: First day of the month
            month_end: Last day of the month
            
        Returns:
            Dictionary with agreement types as keys and total AED amounts as values.
            Keys: "Retainer", "Framework", "Ad Hoc", "Unknown"
        """
        # Initialize totals for each agreement type
        invoice_totals = {
            "Retainer": 0.0,
            "Framework": 0.0,
            "Ad Hoc": 0.0,
            "Unknown": 0.0,
        }
        credit_note_totals = {
            "Retainer": 0.0,
            "Framework": 0.0,
            "Ad Hoc": 0.0,
            "Unknown": 0.0,
        }
        reversed_totals = {
            "Retainer": 0.0,
            "Framework": 0.0,
            "Ad Hoc": 0.0,
            "Unknown": 0.0,
        }
        
        # Get invoices (out_invoice, not reversed, partner_id != 10)
        invoices = self._get_invoice_details(month_start, month_end)
        for invoice in invoices:
            agreement_type = invoice.get("agreement_type", "Unknown")
            tags = invoice.get("tags", [])
            category = self._categorize_agreement_type(agreement_type, tags)
            aed_total = invoice.get("x_studio_aed_total")
            amount = 0.0
            if aed_total:
                try:
                    amount = float(aed_total)
                except (ValueError, TypeError):
                    pass
            invoice_totals[category] += amount
        
        # Get credit notes (out_refund, not reversed, partner_id != 10)
        credit_notes = self._get_credit_note_details(month_start, month_end)
        for credit_note in credit_notes:
            agreement_type = credit_note.get("agreement_type", "Unknown")
            tags = credit_note.get("tags", [])
            category = self._categorize_agreement_type(agreement_type, tags)
            aed_total = credit_note.get("x_studio_aed_total")
            amount = 0.0
            if aed_total:
                try:
                    # Credit notes are typically negative, but we want absolute value
                    amount = abs(float(aed_total))
                except (ValueError, TypeError):
                    pass
            credit_note_totals[category] += amount
        
        # Get reversed invoices (out_invoice, payment_state=reversed, partner_id != 10)
        reversed_invoices = self._get_reversed_invoice_details(month_start, month_end)
        for reversed_inv in reversed_invoices:
            agreement_type = reversed_inv.get("agreement_type", "Unknown")
            tags = reversed_inv.get("tags", [])
            category = self._categorize_agreement_type(agreement_type, tags)
            aed_total = reversed_inv.get("x_studio_aed_total")
            amount = 0.0
            if aed_total:
                try:
                    amount = float(aed_total)
                except (ValueError, TypeError):
                    pass
            reversed_totals[category] += amount
        
        # Calculate final totals: invoices - credit_notes + reversed
        totals = {
            "Retainer": invoice_totals["Retainer"] - credit_note_totals["Retainer"] + reversed_totals["Retainer"],
            "Framework": invoice_totals["Framework"] - credit_note_totals["Framework"] + reversed_totals["Framework"],
            "Ad Hoc": invoice_totals["Ad Hoc"] - credit_note_totals["Ad Hoc"] + reversed_totals["Ad Hoc"],
            "Unknown": invoice_totals["Unknown"] - credit_note_totals["Unknown"] + reversed_totals["Unknown"],
        }
        
        return totals
    
    def _get_credit_note_details(self, start_date: date, end_date: date) -> list:
        """Get detailed credit note information with project details.
        
        Returns list of credit notes with name, date, partner, state, payment_state, move_type,
        and project details (Market, Agreement, Tags, AED Total).
        """
        # Build Odoo domain filter for credit notes
        domain = [
            "&", "&", "&",
            ("move_type", "in", ["out_refund"]),  # Customer Credit Note
            ("payment_state", "not in", ["reversed"]),
            ("partner_id", "not in", [10]),
            "&",
            ("invoice_date", ">=", start_date.isoformat()),
            ("invoice_date", "<=", end_date.isoformat()),
        ]
        
        # Fetch credit note details including invoice_line_ids and x_studio_aed_total
        credit_notes = self.odoo_client.search_read_all(
            model="account.move",
            domain=domain,
            fields=[
                "name", 
                "invoice_date", 
                "partner_id", 
                "state", 
                "payment_state", 
                "move_type",
                "invoice_line_ids",
                "x_studio_aed_total"
            ],
        )
        
        # Enrich credit notes with project details (same traversal as invoices)
        self._fetch_project_details(credit_notes)
        
        return credit_notes
    
    def _get_reversed_invoice_details(self, start_date: date, end_date: date) -> list:
        """Get detailed reversed invoice information with project details.
        
        Returns list of reversed invoices with name, date, partner, state, payment_state, move_type,
        and project details (Market, Agreement, Tags, AED Total).
        """
        # Build Odoo domain filter for reversed invoices
        domain = [
            "&", "&", "&",
            ("move_type", "in", ["out_invoice"]),
            ("payment_state", "=", "reversed"),  # Reversed invoices
            ("partner_id", "not in", [10]),
            "&",
            ("invoice_date", ">=", start_date.isoformat()),
            ("invoice_date", "<=", end_date.isoformat()),
        ]
        
        # Fetch reversed invoice details including invoice_line_ids and x_studio_aed_total
        reversed_invoices = self.odoo_client.search_read_all(
            model="account.move",
            domain=domain,
            fields=[
                "name", 
                "invoice_date", 
                "partner_id", 
                "state", 
                "payment_state", 
                "move_type",
                "invoice_line_ids",
                "x_studio_aed_total"
            ],
        )
        
        # Enrich reversed invoices with project details (same traversal as invoices)
        self._fetch_project_details(reversed_invoices)
        
        return reversed_invoices
    
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
        # We need to filter subscriptions that overlap with the month:
        # - first_contract_date <= month_end (started before or during month)
        # - end_date >= month_start OR end_date is False (ends after or during month, or is ongoing)
        # - subscription_state in ["3_progress", "6_churn"] (In Progress or Churned)
        domain = [
            "&", "&",
            ("first_contract_date", "<=", month_end.isoformat()),
            ("subscription_state", "in", ["3_progress", "6_churn"]),
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
            "subscription_state",
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
        external_hours_used_map = self._calculate_external_hours_used(project_ids, month_start, month_end)
        
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
            
            # Get market from project
            project_field = order.get("project_id")
            market = "Unassigned Market"
            project_id = None
            project_name = "Unassigned Project"
            
            if isinstance(project_field, (list, tuple)) and len(project_field) >= 1:
                project_id = project_field[0]
                project = projects.get(project_id)
                if project:
                    market = self._market_label(project)
                    project_name = project.get("name", "Unassigned Project")
            
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
            end_date = self._parse_odoo_date(order.get("end_date"))
            
            # Get external hours used for this project
            external_hours_used = 0.0
            if project_id:
                external_hours_used = external_hours_used_map.get(project_id, 0.0)
            
            subscriptions.append({
                "order_id": order_id,
                "order_name": order_name,
                "customer_name": customer_name,
                "market": market,
                "project_id": project_id,
                "project_name": project_name,
                "external_sold_hours": external_sold_hours,
                "external_sold_hours_display": f"{external_sold_hours:.1f}h" if external_sold_hours > 0 else "0h",
                "external_hours_used": external_hours_used,
                "external_hours_used_display": f"{external_hours_used:.1f}h" if external_hours_used > 0 else "0h",
                "monthly_recurring_payment": monthly_recurring_payment,
                "monthly_recurring_payment_display": f"AED {monthly_recurring_payment:,.2f}" if monthly_recurring_payment > 0 else "AED 0.00",
                "first_contract_date": first_contract_date.isoformat() if first_contract_date else None,
                "end_date": end_date.isoformat() if end_date else None,
                "is_ongoing": end_date is None,
            })
        
        # Sort by customer name, then by order name
        subscriptions.sort(key=lambda x: (x["customer_name"].lower(), x["order_name"]))
        
        return subscriptions
    
    def get_subscription_statistics(
        self,
        month_start: date,
        month_end: date,
    ) -> Dict[str, Any]:
        """Calculate subscription statistics for the selected month.
        
        Args:
            month_start: First day of the month
            month_end: Last day of the month
            
        Returns:
            Dictionary with:
            - active_count: Number of subscriptions with state "3_progress"
            - churned_count: Number of subscriptions with state "6_churn"
            - new_renew_count: Number of subscriptions where start_date is in the month
            - mrr: Total monthly recurring revenue (sum of recurring_monthly)
        """
        # Build domain filter - same as get_subscriptions_for_month but we need all subscriptions
        # that overlap with the month
        domain = [
            "&", "&",
            ("first_contract_date", "<=", month_end.isoformat()),
            ("subscription_state", "in", ["3_progress", "6_churn"]),
            "|",
            ("end_date", "=", False),
            ("end_date", ">=", month_start.isoformat()),
        ]
        
        fields = [
            "id",
            "name",
            "subscription_state",
            "start_date",
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
            return {
                "active_count": 0,
                "churned_count": 0,
                "new_renew_count": 0,
                "mrr": 0.0,
                "mrr_display": "AED 0.00",
                "active_order_names": [],
            }
        
        active_count = 0
        churned_count = 0
        new_renew_count = 0
        mrr_total = 0.0
        active_order_names = []
        
        for order in orders:
            subscription_state = order.get("subscription_state")
            
            # Count active (In Progress) and collect order names
            if subscription_state == "3_progress":
                active_count += 1
                order_name = order.get("name", "")
                if order_name:
                    active_order_names.append(order_name)
            
            # Count churned
            if subscription_state == "6_churn":
                churned_count += 1
            
            # Check if new/renew (start_date in the month)
            start_date = self._parse_odoo_date(order.get("start_date"))
            if start_date and month_start <= start_date <= month_end:
                new_renew_count += 1
            
            # Sum MRR
            recurring = order.get("recurring_monthly")
            if recurring:
                try:
                    mrr_total += float(recurring)
                except (ValueError, TypeError):
                    pass
        
        # Sort order names
        active_order_names = sorted(set(active_order_names))
        
        return {
            "active_count": active_count,
            "churned_count": churned_count,
            "new_renew_count": new_renew_count,
            "mrr": mrr_total,
            "mrr_display": f"AED {mrr_total:,.2f}" if mrr_total > 0 else "AED 0.00",
            "active_order_names": active_order_names,
        }
    
    def _calculate_external_hours_used(
        self,
        project_ids: Iterable[int],
        month_start: date,
        month_end: date,
    ) -> Dict[int, float]:
        """Calculate external hours used for projects based on subtask client due dates.
        
        For each project:
        1. Get all tasks under that project
        2. Get all subtasks for each task
        3. For subtasks where x_studio_client_due_date_3 is within the month, 
           sum x_studio_external_hours_2
        
        Args:
            project_ids: List of project IDs
            month_start: First day of the month
            month_end: Last day of the month
            
        Returns:
            Dictionary mapping project_id to total external hours used
        """
        ids = [pid for pid in project_ids if isinstance(pid, int)]
        if not ids:
            return {}
        
        # Get all tasks for these projects
        domain = [
            ("project_id", "in", ids),
        ]
        fields = ["id", "project_id", "child_ids"]
        
        try:
            tasks = self.odoo_client.search_read_all(
                model="project.task",
                domain=domain,
                fields=fields,
            )
        except Exception as e:
            print(f"Error fetching tasks for external hours calculation: {e}")
            return {}
        
        if not tasks:
            return {}
        
        # Collect all subtask IDs
        subtask_ids = []
        task_project_map = {}  # Map task_id to project_id
        
        for task in tasks:
            task_id = task.get("id")
            if not isinstance(task_id, int):
                continue
                
            project_field = task.get("project_id")
            if isinstance(project_field, (list, tuple)) and len(project_field) >= 1:
                project_id = project_field[0]
                if isinstance(project_id, int):
                    task_project_map[task_id] = project_id
            
            child_ids = task.get("child_ids") or []
            for child_id in child_ids:
                if isinstance(child_id, int):
                    subtask_ids.append(child_id)
        
        if not subtask_ids:
            return {}
        
        # Fetch subtasks with client due date and external hours
        try:
            subtasks = self.odoo_client.read(
                "project.task",
                subtask_ids,
                ["id", "x_studio_client_due_date_3", "x_studio_external_hours_2", "parent_id"]
            )
        except Exception as e:
            print(f"Error fetching subtasks for external hours calculation: {e}")
            return {}
        
        # Calculate totals per project
        project_totals: Dict[int, float] = {}
        
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
            
            # Check if client due date is within the month
            client_due_date = self._parse_odoo_date(subtask.get("x_studio_client_due_date_3"))
            if not client_due_date:
                continue
            
            if client_due_date < month_start or client_due_date > month_end:
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
                except (ValueError, TypeError):
                    pass
        
        return project_totals
    
    def _parse_odoo_date(self, value: Any) -> Optional[date]:
        """Parse Odoo date value to Python date object.
        
        Args:
            value: Odoo date value (string in YYYY-MM-DD format or False/None)
            
        Returns:
            date object or None if invalid/False
        """
        if not value or value is False:
            return None
        
        if isinstance(value, date):
            return value
        
        if isinstance(value, str):
            try:
                return datetime.strptime(value.split()[0], "%Y-%m-%d").date()
            except (ValueError, AttributeError):
                pass
        
        return None

    def _categorize_agreement_type(self, agreement_type: Any, tags: Any = None) -> str:
        """Categorize agreement type into Retainer, Framework, Ad Hoc, or Unknown.
        
        Args:
            agreement_type: The agreement type string or value
            tags: Optional list of tags
            
        Returns:
            One of: "Retainer", "Framework", "Ad Hoc", "Unknown"
        """
        tokens = self._extract_agreement_tokens(agreement_type)
        if isinstance(tags, (list, tuple, set)):
            for tag in tags:
                tokens.extend(self._extract_agreement_tokens(tag))
        
        normalized = [token.lower() for token in tokens if token]
        
        # Check for retainer
        for token in normalized:
            if any(key in token for key in ("retainer", "subscription", "subscr")):
                return "Retainer"
        
        # Check for framework
        for token in normalized:
            if "framework" in token:
                return "Framework"
        
        # Check for ad hoc
        for token in normalized:
            if "ad-hoc" in token or "adhoc" in token or "ad hoc" in token:
                return "Ad Hoc"
        
        return "Unknown"

    def _extract_agreement_tokens(self, raw: Any) -> List[str]:
        """Extract tokens from agreement type string.
        
        Args:
            raw: Agreement type value (string, list, etc.)
            
        Returns:
            List of token strings
        """
        if raw is None:
            return []
        if isinstance(raw, str):
            stripped = raw.strip()
            if not stripped:
                return []
            parts = re.split(r"[,/&|]+", stripped)
            return [part.strip() for part in parts if part.strip()]
        if isinstance(raw, (list, tuple, set)):
            tokens: List[str] = []
            for item in raw:
                tokens.extend(self._extract_agreement_tokens(item))
            return tokens
        return []
