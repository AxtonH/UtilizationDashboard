"""Invoiced revenue: counts, totals, series, breakdowns."""
from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple
import re
from ...integrations.odoo_client import OdooClient
from ..cache_finality import SALES_CACHE_FINALIZE_GRACE_DAYS, cached_month_rows_are_final


class InvoicedMixin:
    """Invoiced revenue: counts, totals, series, breakdowns."""

    def _aggregate_invoice_breakdown(
        self, invoices: List[Dict[str, Any]], year: int, month: int
    ) -> List[Dict[str, Any]]:
        """Aggregate invoice breakdown by market/agreement/account for a month."""
        buckets: Dict[Tuple[str, str, str], Dict[str, Any]] = {}

        for inv in invoices:
            try:
                amount_override = inv.get("amount_override")
                raw_amount = amount_override if amount_override is not None else inv.get("x_studio_aed_total") or 0.0
                amount_val = float(raw_amount)
            except Exception:
                amount_val = 0.0

            market = inv.get("market") or "Unknown"
            agreement_type = self._canonical_agreement_label(inv.get("agreement_type"))
            tags = inv.get("tags") or []
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
                    "invoice_count": 0,
                }
            buckets[key]["amount_aed"] += amount_val
            buckets[key]["invoice_count"] += 1

        return list(buckets.values())

    def _get_invoice_details_generic(
        self,
        start_date: date,
        end_date: date,
        move_types: Iterable[str],
        payment_state_not_in: Optional[Iterable[str]] = None,
        payment_state_in: Optional[Iterable[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch invoice-like records with project metadata using a flexible domain.
        """
        domain = [
            "&",
            "&",
            ("move_type", "in", list(move_types)),
            ("partner_id", "not in", [10]),
            "&",
            ("invoice_date", ">=", start_date.isoformat()),
            ("invoice_date", "<=", end_date.isoformat()),
        ]

        if payment_state_not_in:
            domain = ["&"] + domain
            domain.append(("payment_state", "not in", list(payment_state_not_in)))
        if payment_state_in:
            domain = ["&"] + domain
            domain.append(("payment_state", "in", list(payment_state_in)))

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
                "x_studio_aed_total",
            ],
        )

        self._fetch_project_details(invoices)
        return invoices

    def _build_invoice_breakdown_with_sign(
        self, start_date: date, end_date: date, year: int, month: int
    ) -> List[Dict[str, Any]]:
        """
        Build breakdown rows using net formula:
        invoices_total - credit_notes_total + reversed_total.
        """
        # Regular invoices (positive)
        invoices = self._get_invoice_details_generic(
            start_date,
            end_date,
            move_types=["out_invoice"],
            payment_state_not_in=["reversed"],
        )
        for inv in invoices:
            inv["amount_override"] = inv.get("x_studio_aed_total") or 0.0

        # Credit notes (negative)
        credit_notes = self._get_invoice_details_generic(
            start_date,
            end_date,
            move_types=["out_refund"],
            payment_state_not_in=["reversed"],
        )
        for inv in credit_notes:
            try:
                amt = float(inv.get("x_studio_aed_total") or 0.0)
            except Exception:
                amt = 0.0
            inv["amount_override"] = -abs(amt)

        # Reversed invoices (add back)
        reversed_invoices = self._get_invoice_details_generic(
            start_date,
            end_date,
            move_types=["out_invoice"],
            payment_state_in=["reversed"],
        )
        for inv in reversed_invoices:
            try:
                amt = float(inv.get("x_studio_aed_total") or 0.0)
            except Exception:
                amt = 0.0
            inv["amount_override"] = abs(amt)

        combined = invoices + credit_notes + reversed_invoices
        if not combined:
            return []

        return self._aggregate_invoice_breakdown(combined, year, month)

    def get_monthly_invoiced_series_with_breakdown(
        self,
        year: int,
        upto_month: int,
        cache_service: Optional["SalesCacheService"] = None,
        include_previous_year: bool = True,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Return monthly invoiced series plus per-month breakdowns for filtering."""
        series_only = self.get_monthly_invoiced_series(
            year, upto_month, cache_service=cache_service, include_previous_year=include_previous_year
        )

        if not cache_service:
            # No Supabase cache available, return series with empty breakdowns
            return series_only, []

        # We need breakdowns for current year and previous year (for the overlay)
        years_to_fetch = [year]
        previous_year = year - 1
        if include_previous_year:
            years_to_fetch.append(previous_year)

        # Pull cached breakdowns per year
        breakdown_by_year: Dict[int, List[Dict[str, Any]]] = {}
        for yr in years_to_fetch:
            breakdown_by_year[yr] = cache_service.get_breakdown_for_year(yr)

        current_date = date.today()

        # Fill missing months and always refresh the current month for the current year
        for yr in years_to_fetch:
            # We only need months up to the selected month for both years (chart overlay stops there)
            months_needed = range(1, upto_month + 1)

            year_rows = breakdown_by_year.get(yr, [])
            # Helper to filter out a specific month before replacing it
            def _remove_month(rows: List[Dict[str, Any]], month_val: int) -> List[Dict[str, Any]]:
                return [r for r in rows if r.get("month") != month_val or r.get("year") != yr]

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

                month_breakdown = self._build_invoice_breakdown_with_sign(month_start, month_end, yr, month)

                if month_breakdown:
                    # Replace existing rows for that month with fresh data
                    year_rows = _remove_month(year_rows, month) + month_breakdown
                    cache_service.upsert_month_breakdown(month_breakdown)
                elif is_current_month:
                    # If we tried to refresh current month but got nothing, still clear stale cache for that month
                    year_rows = _remove_month(year_rows, month)

            breakdown_by_year[yr] = year_rows

        # Flatten and sort for deterministic order; include both years but only needed months
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
                invoice["tags"] = self._project_tags(found_project)

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
            month_start = date(year, month, 1)
            _, last_day = monthrange(year, month)
            month_end = date(year, month, last_day)

            # Fetch current year data
            cached_data = None
            invoices_total = None
            credit_notes_total = None
            reversed_total = None

            if cache_service and not is_current_month:
                cached_data = cache_service.get_month_data(year, month)
                # Provisional rows (written before the month settled) are
                # dropped so the month recomputes and re-caches with a
                # post-close timestamp — see services/cache_finality.py.
                if cached_data and not cached_month_rows_are_final(
                    [cached_data], month_end, SALES_CACHE_FINALIZE_GRACE_DAYS
                ):
                    cached_data = None

            if cached_data:
                amount = float(cached_data.get("amount_aed", 0.0))
            else:
                # Fetch from Odoo (for both current and past months)
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
                prev_month_start = date(previous_year, month, 1)
                _, prev_last_day = monthrange(previous_year, month)
                prev_month_end = date(previous_year, month, prev_last_day)

                previous_cached_data = None
                if cache_service:
                    previous_cached_data = cache_service.get_month_data(previous_year, month)
                    if previous_cached_data and not cached_month_rows_are_final(
                        [previous_cached_data], prev_month_end, SALES_CACHE_FINALIZE_GRACE_DAYS
                    ):
                        previous_cached_data = None

                if previous_cached_data:
                    previous_amount = float(previous_cached_data.get("amount_aed", 0.0))
                else:
                    # Fetch from Odoo

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

    def aggregate_monthly_series_to_quarterly(
        self, monthly_series: List[Dict[str, Any]], upto_quarter: int
    ) -> List[Dict[str, Any]]:
        """Roll up monthly series points into calendar quarters (Q1–Qn), preserving YoY columns."""
        if not monthly_series or upto_quarter < 1:
            return []
        by_month = {int(r["month"]): r for r in monthly_series if r.get("month") is not None}
        year = int(monthly_series[0]["year"])
        prev_year = int(monthly_series[0].get("previous_year", year - 1))
        has_prev_year = monthly_series[0].get("previous_year_amount_aed") is not None
        out: List[Dict[str, Any]] = []
        for q in range(1, upto_quarter + 1):
            m1, m2, m3 = (q - 1) * 3 + 1, (q - 1) * 3 + 2, (q - 1) * 3 + 3
            cy = 0.0
            py = 0.0
            for m in (m1, m2, m3):
                row = by_month.get(m)
                if not row:
                    continue
                cy += float(row.get("amount_aed") or 0.0)
                if has_prev_year:
                    py += float(row.get("previous_year_amount_aed") or 0.0)
            item: Dict[str, Any] = {
                "year": year,
                "quarter": q,
                "month": m3,
                "label": f"Q{q}",
                "amount_aed": cy,
                "amount_display": f"AED {cy:,.2f}",
            }
            if has_prev_year:
                item["previous_year"] = prev_year
                item["previous_year_amount_aed"] = py
                item["previous_year_amount_display"] = f"AED {py:,.2f}"
            out.append(item)
        return out

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
