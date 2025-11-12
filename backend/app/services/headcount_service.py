"""Business logic for calculating creative headcount metrics."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from .employee_service import EmployeeService


class HeadcountService:
    """Encapsulates headcount calculation logic for the dashboard."""

    def __init__(self, employee_service: EmployeeService):
        self.employee_service = employee_service

    def calculate_headcount(
        self,
        selected_month: date,
        all_creatives: Optional[List[Dict[str, Any]]] = None,
        processed_creatives: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Calculate headcount metrics for the selected month.
        
        Args:
            selected_month: The month to calculate headcount for
            all_creatives: Optional list of all creatives from Odoo (if None, will fetch)
            processed_creatives: Optional list of creatives with availability data processed
                               (used for accurate available count calculation)
            
        Returns:
            Dictionary with headcount metrics:
            - total: Total number of creatives
            - available: Number of available creatives (those with market/pool)
            - new_joiners: List of creatives who joined in the selected month
            - new_joiners_count: Count of new joiners
            - new_joiners_names: List of names of new joiners for tooltip
        """
        if all_creatives is None:
            all_creatives = self.employee_service.get_all_creatives(include_inactive=True)
        
        # Calculate month bounds
        month_start = date(selected_month.year, selected_month.month, 1)
        if selected_month.month == 12:
            month_end = date(selected_month.year + 1, 1, 1)
        else:
            month_end = date(selected_month.year, selected_month.month + 1, 1)
        
        # Total creatives (all from Odoo, including inactive)
        total_creatives = len(all_creatives)
        
        # Available creatives (those with market/pool assigned)
        # Use processed_creatives if provided (has market_display/pool_display), otherwise check raw data
        if processed_creatives:
            available_creatives = [
                c for c in processed_creatives
                if c.get("market_display") or c.get("pool_display")
            ]
            available_count = len(available_creatives)
        else:
            # Fallback: check raw creatives for market/pool fields
            available_creatives = [
                c for c in all_creatives
                if c.get("current_market") or c.get("current_pool")
            ]
            available_count = len(available_creatives)
        
        # New joiners: creatives whose joining date falls within the selected month
        new_joiners = []
        for creative in all_creatives:
            joining_date = self._parse_joining_date(creative.get("x_studio_joining_date"))
            if joining_date and self._is_date_in_month(joining_date, month_start, month_end):
                new_joiners.append(creative)
        
        # Sort new joiners by name
        new_joiners.sort(key=lambda c: c.get("name", ""))
        
        return {
            "total": total_creatives,
            "available": available_count,
            "new_joiners": new_joiners,
            "new_joiners_count": len(new_joiners),
            "new_joiners_names": [c.get("name", "Unknown") for c in new_joiners],
        }
    
    def _parse_joining_date(self, value: Any) -> Optional[date]:
        """Parse joining date from various formats.
        
        Args:
            value: Date value from Odoo (can be string, date, or None)
            
        Returns:
            Parsed date object or None if invalid/missing
        """
        if value is None:
            return None
        
        # If already a date object
        if isinstance(value, date):
            return value
        
        # If it's a datetime object
        if isinstance(value, datetime):
            return value.date()
        
        # If it's a string, try to parse it
        if isinstance(value, str):
            try:
                # Try ISO format first (YYYY-MM-DD)
                return datetime.fromisoformat(value).date()
            except (ValueError, AttributeError):
                try:
                    # Try other common formats
                    return datetime.strptime(value, "%Y-%m-%d").date()
                except (ValueError, AttributeError):
                    return None
        
        return None
    
    def _is_date_in_month(self, check_date: date, month_start: date, month_end: date) -> bool:
        """Check if a date falls within a month range.
        
        Args:
            check_date: Date to check
            month_start: First day of the month (inclusive)
            month_end: First day of next month (exclusive)
            
        Returns:
            True if date is within the month range
        """
        return month_start <= check_date < month_end

