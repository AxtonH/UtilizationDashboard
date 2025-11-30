"""Sales statistics service for invoice data."""
from __future__ import annotations

from calendar import monthrange
from datetime import date
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
        domain = [
            "&", "&",
            ("state", "=", "sale"),
            ("date_order", ">=", start_date.isoformat()),
            ("date_order", "<=", end_date.isoformat()),
        ]
        
        order_ids = self.odoo_client.search(
            model="sale.order",
            domain=domain,
        )
        
        return len(order_ids)

    def _get_sales_order_details(self, start_date: date, end_date: date) -> list:
        """Get detailed sales order information for debugging.
        
        Returns list of orders with name, date, total, and project details.
        """
        domain = [
            "&", "&",
            ("state", "=", "sale"),
            ("date_order", ">=", start_date.isoformat()),
            ("date_order", "<=", end_date.isoformat()),
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
        
        self._enrich_sales_orders(orders)
        
        return orders

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
            if cache_service and not is_current_month:
                cached_data = cache_service.get_month_data(year, month)
            
            if cached_data:
                amount = float(cached_data.get("amount_aed", 0.0))
            else:
                # Fetch from Odoo
                month_start = date(year, month, 1)
                _, last_day = monthrange(year, month)
                month_end = date(year, month, last_day)
                
                # We need the total amount, not just count
                amount = self._get_monthly_total_from_odoo(month_start, month_end)
                
                # Update cache
                if cache_service:
                    # If current month, check if cache needs update (or just upsert)
                    # If past month, definitely save
                    cache_service.save_month_data(year, month, amount)
            
            # For current month, if we have a cache service, we should also check if the Odoo value 
            # is different from what might be in cache (though we skipped reading it above)
            # and update it. The logic above fetches from Odoo for current month, so we just save it.
            if is_current_month and cache_service:
                 cache_service.save_month_data(year, month, amount)

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
                    
                    previous_amount = self._get_monthly_total_from_odoo(prev_month_start, prev_month_end)
                    
                    # Update cache
                    if cache_service:
                        cache_service.save_month_data(previous_year, month, previous_amount)

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
        
        Args:
            start_date: Start of date range
            end_date: End of date range
            
        Returns:
            Total AED amount
        """
        # Build Odoo domain filter (same as _get_invoice_count but we need the sum)
        domain = [
            "&", "&", "&",
            ("move_type", "in", ["out_invoice"]),
            ("payment_state", "not in", ["reversed"]),
            ("partner_id", "not in", [10]),
            "&",
            ("invoice_date", ">=", start_date.isoformat()),
            ("invoice_date", "<=", end_date.isoformat()),
        ]
        
        # We need to fetch all invoices and sum x_studio_aed_total
        # Optimization: We could use read_group if Odoo client supports it, but search_read is safer with current client
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

    def get_invoice_totals_by_agreement_type(
        self,
        month_start: date,
        month_end: date,
    ) -> Dict[str, float]:
        """Get total invoiced amounts grouped by agreement type for the selected month.
        
        Args:
            month_start: First day of the month
            month_end: Last day of the month
            
        Returns:
            Dictionary with agreement types as keys and total AED amounts as values.
            Keys: "Retainer", "Framework", "Ad Hoc", "Unknown"
        """
        # Get invoice details (already includes project details with agreement_type)
        invoices = self._get_invoice_details(month_start, month_end)
        
        # Initialize totals for each agreement type
        totals = {
            "Retainer": 0.0,
            "Framework": 0.0,
            "Ad Hoc": 0.0,
            "Unknown": 0.0,
        }
        
        # Process each invoice
        for invoice in invoices:
            agreement_type = invoice.get("agreement_type", "Unknown")
            tags = invoice.get("tags", [])
            
            # Categorize agreement type
            category = self._categorize_agreement_type(agreement_type, tags)
            
            # Get invoice amount
            aed_total = invoice.get("x_studio_aed_total")
            amount = 0.0
            if aed_total:
                try:
                    amount = float(aed_total)
                except (ValueError, TypeError):
                    pass
            
            # Add to appropriate category
            totals[category] += amount
        
        return totals

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
