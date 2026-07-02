"""Top-level sales statistics entry point."""
from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple
import re
from ...integrations.odoo_client import OdooClient


class SalesStatisticsMixin:
    """Top-level sales statistics entry point."""

    def calculate_sales_statistics(
        self,
        month_start: date,
        month_end: date,
        *,
        previous_period: Optional[Tuple[date, date]] = None,
    ) -> Dict[str, Any]:
        """Calculate sales statistics for the selected period (one month or one quarter).

        Args:
            month_start: First day of the period (inclusive)
            month_end: Last day of the period (inclusive)
            previous_period: Optional (start, end) for the comparison period (previous month
                or previous calendar quarter). When omitted, no MoM/QoQ comparison is returned.

        Returns:
            Dictionary with sales metrics:
            - invoice_count: Total number of invoices for the period
            - comparison: Period-over-period comparison data
            - invoices: List of invoice details for debugging
        """
        # Get current period invoices
        current_count = self._get_invoice_count(month_start, month_end)
        invoice_details = self._get_invoice_details(month_start, month_end)

        # Get current period sales orders
        sales_order_count = self._get_sales_order_count(month_start, month_end)
        sales_order_details = self._get_sales_order_details(month_start, month_end)

        comparison = None
        sales_order_comparison = None

        if previous_period:
            prev_start, prev_end = previous_period
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
