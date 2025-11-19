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
        selected_markets: Optional[List[str]] = None,
        selected_pools: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Calculate headcount metrics for the selected month.
        
        Args:
            selected_month: The month to calculate headcount for
            all_creatives: Optional list of all creatives from Odoo (if None, will fetch)
            processed_creatives: Optional list of creatives with availability data processed
                               (used for accurate available count calculation)
            selected_markets: Optional list of market slugs to filter by (e.g., ['ksa', 'uae'])
            selected_pools: Optional list of pool names to filter by
            
        Returns:
            Dictionary with headcount metrics:
            - total: Total number of creatives (filtered if filters applied)
            - available: Number of available creatives (those with market/pool, filtered if filters applied)
            - new_joiners: List of creatives who joined in the selected month (filtered if filters applied)
            - new_joiners_count: Count of new joiners
            - new_joiners_names: List of names of new joiners for tooltip
            - offboarded: List of creatives who were offboarded in the selected month (filtered if filters applied)
            - offboarded_count: Count of offboarded creatives
            - offboarded_names: List of names of offboarded creatives for tooltip
        """
        if all_creatives is None:
            all_creatives = self.employee_service.get_all_creatives(include_inactive=True)
        
        # Calculate month bounds
        month_start = date(selected_month.year, selected_month.month, 1)
        if selected_month.month == 12:
            month_end = date(selected_month.year + 1, 1, 1)
        else:
            month_end = date(selected_month.year, selected_month.month + 1, 1)
        
        # Helper function to check if a creative matches the filters
        def _matches_filters(creative: Dict[str, Any]) -> bool:
            """Check if creative matches market and pool filters."""
            if not selected_markets and not selected_pools:
                return True
            
            # Get market_slug and pool_name from processed_creatives if available
            # Otherwise try to get from raw creative data
            market_slug = creative.get("market_slug")
            pool_name = creative.get("pool_name")
            
            # If not in processed_creatives, try to get from raw fields
            if not market_slug:
                # Try to get market from current_market or other fields
                current_market = creative.get("current_market")
                if current_market:
                    # Convert market name to slug (basic conversion)
                    market_slug = current_market.lower().replace(" ", "-")
            
            if not pool_name:
                pool_name = creative.get("current_pool")
            
            # Market filter: if markets selected, creative must match one
            market_match = True
            if selected_markets:
                if not market_slug:
                    return False
                # Normalize market slug for comparison
                normalized_market = market_slug.lower() if isinstance(market_slug, str) else None
                market_match = normalized_market in [m.lower() for m in selected_markets]
            
            # Pool filter: if pools selected, creative must match one
            pool_match = True
            if selected_pools:
                if not pool_name:
                    return False
                pool_match = pool_name in selected_pools
            
            return market_match and pool_match
        
        # Available creatives: those with market/pool assigned AND available_hours > planned_hours
        # Use processed_creatives if provided (has market_display/pool_display), otherwise check raw data
        if processed_creatives:
            available_creatives = [
                c for c in processed_creatives
                if (c.get("market_display") or c.get("pool_display"))
                and (float(c.get("available_hours", 0) or 0) > float(c.get("planned_hours", 0) or 0))
            ]
            # Apply filters if provided
            if selected_markets or selected_pools:
                available_creatives = [c for c in available_creatives if _matches_filters(c)]
            available_count = len(available_creatives)
        else:
            # Fallback: check raw creatives for market/pool fields
            # Note: raw creatives might not have available_hours/planned_hours computed yet if not processed
            # But usually this method is called with processed_creatives in the dashboard route
            available_creatives = [
                c for c in all_creatives
                if (c.get("current_market") or c.get("current_pool"))
                and (float(c.get("available_hours", 0) or 0) > float(c.get("planned_hours", 0) or 0))
            ]
            # Apply filters if provided (but this is less accurate without processed_creatives)
            if selected_markets or selected_pools:
                available_creatives = [c for c in available_creatives if _matches_filters(c)]
            available_count = len(available_creatives)
        
        # Total creatives: those with market/pool assigned (and matching filters if provided)
        # This should NOT depend on the "available < planned" condition
        if processed_creatives:
            total_creatives_list = [
                c for c in processed_creatives
                if (c.get("market_display") or c.get("pool_display"))
            ]
            if selected_markets or selected_pools:
                total_creatives_list = [c for c in total_creatives_list if _matches_filters(c)]
            total_creatives = len(total_creatives_list)
        else:
            total_creatives_list = [
                c for c in all_creatives
                if (c.get("current_market") or c.get("current_pool"))
            ]
            if selected_markets or selected_pools:
                total_creatives_list = [c for c in total_creatives_list if _matches_filters(c)]
            total_creatives = len(total_creatives_list)
        
        # New joiners: creatives whose joining date falls within the selected month
        # AND match the filters (must be in the filtered market/pool)
        new_joiners = []
        # Use processed_creatives for filtering since they have market/pool info
        creatives_to_check = processed_creatives if processed_creatives else all_creatives
        for creative in creatives_to_check:
            joining_date = self._parse_joining_date(creative.get("x_studio_joining_date"))
            if joining_date and self._is_date_in_month(joining_date, month_start, month_end):
                # Check if creative matches filters
                if _matches_filters(creative):
                    new_joiners.append(creative)
        
        # Sort new joiners by name
        new_joiners.sort(key=lambda c: c.get("name", ""))
        
        # Offboarded: creatives whose contract end date falls within the selected month
        # AND match the filters (must be/were in the filtered market/pool)
        offboarded = []
        
        # Create a lookup map from processed_creatives by ID for market/pool info
        processed_lookup = {}
        if processed_creatives:
            for pc in processed_creatives:
                pc_id = pc.get("id")
                if isinstance(pc_id, int):
                    processed_lookup[pc_id] = {
                        "market_slug": pc.get("market_slug"),
                        "pool_name": pc.get("pool_name"),
                    }
        
        # Check all creatives (including inactive) for offboarded
        for creative in all_creatives:
            contract_end_date = self._parse_joining_date(creative.get("x_studio_rf_contract_end_date"))
            if contract_end_date and self._is_date_in_month(contract_end_date, month_start, month_end):
                creative_id = creative.get("id")
                
                # If creative is in processed_creatives, use that data (has market/pool info)
                if isinstance(creative_id, int) and creative_id in processed_lookup:
                    # Use market/pool from processed_creatives
                    market_pool_info = processed_lookup[creative_id]
                    creative_with_market = {
                        **creative,
                        "market_slug": market_pool_info["market_slug"],
                        "pool_name": market_pool_info["pool_name"],
                    }
                    if _matches_filters(creative_with_market):
                        offboarded.append(creative)
                else:
                    # For inactive creatives not in processed_creatives, try to match filters
                    # using raw data (less reliable but better than nothing)
                    if _matches_filters(creative):
                        offboarded.append(creative)
        
        # Sort offboarded by name
        offboarded.sort(key=lambda c: c.get("name", ""))
        
        return {
            "total": total_creatives,
            "available": available_count,
            "new_joiners": new_joiners,
            "new_joiners_count": len(new_joiners),
            "new_joiners_names": [c.get("name", "Unknown") for c in new_joiners],
            "offboarded": offboarded,
            "offboarded_count": len(offboarded),
            "offboarded_names": [c.get("name", "Unknown") for c in offboarded],
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

