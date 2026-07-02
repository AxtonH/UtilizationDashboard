"""Market/pool resolution for creatives by month.

Extracted verbatim from ``routes/creatives.py`` so that services
(``alert_service``, ``comparison_service``) no longer import from a route
module. The route module re-exports these names for its own call sites.
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date
from typing import Any, Mapping, Optional, Tuple


def _get_creative_market_for_month(
    creative: Mapping[str, Any],
    target_month: date,
) -> Optional[Tuple[str, Optional[str]]]:
    """Determine which market and pool a creative was in for a given month.

    Logic:
    - Check current market first (x_studio_market)
    - If current market has no end date, they're still in it
    - Otherwise check previous market 1 (x_studio_market_1)
    - Then check previous market 2 (x_studio_market_2)
    - Then check previous market 3 (x_studio_market_3)
    - Returns (market_slug, pool_name) or None if no market matches

    Args:
        creative: Creative employee record with market fields
        target_month: The month to check (should be first day of month)
        debug: If True, log debug information

    Returns:
        Tuple of (market_slug, pool_name) or None if no market matches
    """
    if not creative:
        return None

    creative_name = creative.get("name", "Unknown")
    creative_id = creative.get("id", "Unknown")

    month_start = target_month.replace(day=1)  # Ensure it's the first day
    _, last_day = monthrange(month_start.year, month_start.month)
    month_end = month_start.replace(day=last_day)

    # Check current market first
    current_market = creative.get("current_market")
    current_start = creative.get("current_market_start")
    current_end = creative.get("current_market_end")
    current_pool = creative.get("current_pool")

    if current_market:
        # Only check current market if it has dates that overlap with target month
        if current_start and current_end:
            # Check if target month overlaps with current market period
            overlaps = current_start <= month_end and current_end >= month_start
            if overlaps:
                market_slug = _normalize_market_name(current_market)
                if market_slug:
                    return (market_slug, current_pool)
        elif current_start and not current_end:
            # Current market has no end date - only match if target month is on or after start date
            # This means they're currently in this market, so only match future/current months
            matches = target_month >= current_start.replace(day=1)
            if matches:
                market_slug = _normalize_market_name(current_market)
                if market_slug:
                    return (market_slug, current_pool)

    # Check previous market 1
    previous_market_1 = creative.get("previous_market_1")
    previous_start_1 = creative.get("previous_market_1_start")
    previous_end_1 = creative.get("previous_market_1_end")
    previous_pool_1 = creative.get("previous_pool_1")

    if previous_market_1:
        # If previous market 1 has no end date, they might still be in it
        if previous_start_1 and not previous_end_1:
            # Check if target month is on or after start date
            matches = target_month >= previous_start_1.replace(day=1)
            if matches:
                market_slug = _normalize_market_name(previous_market_1)
                if market_slug:
                    return (market_slug, previous_pool_1)
        # If previous market 1 has both dates, check if target month falls within range
        elif previous_start_1 and previous_end_1:
            # Check if target month overlaps with previous market 1 period
            # Use <= for end date comparison to include the last day of the period
            overlaps = previous_start_1 <= month_end and previous_end_1 >= month_start
            if overlaps:
                market_slug = _normalize_market_name(previous_market_1)
                if market_slug:
                    return (market_slug, previous_pool_1)

    # Check previous market 2
    previous_market_2 = creative.get("previous_market_2")
    previous_start_2 = creative.get("previous_market_2_start")
    previous_end_2 = creative.get("previous_market_2_end")
    previous_pool_2 = creative.get("previous_pool_2")

    if previous_market_2:
        # If previous market 2 has no end date, they might still be in it
        if previous_start_2 and not previous_end_2:
            # Check if target month is on or after start date
            matches = target_month >= previous_start_2.replace(day=1)
            if matches:
                market_slug = _normalize_market_name(previous_market_2)
                if market_slug:
                    return (market_slug, previous_pool_2)
        # If previous market 2 has both dates, check if target month falls within range
        elif previous_start_2 and previous_end_2:
            # Check if target month overlaps with previous market 2 period
            # Use <= for end date comparison to include the last day of the period
            overlaps = previous_start_2 <= month_end and previous_end_2 >= month_start
            if overlaps:
                market_slug = _normalize_market_name(previous_market_2)
                if market_slug:
                    return (market_slug, previous_pool_2)

    # Check previous market 3
    previous_market_3 = creative.get("previous_market_3")
    previous_start_3 = creative.get("previous_market_3_start")
    previous_end_3 = creative.get("previous_market_3_end")
    previous_pool_3 = creative.get("previous_pool_3")

    if previous_market_3:
        # If previous market 3 has no end date, they might still be in it
        if previous_start_3 and not previous_end_3:
            # Check if target month is on or after start date
            matches = target_month >= previous_start_3.replace(day=1)
            if matches:
                market_slug = _normalize_market_name(previous_market_3)
                if market_slug:
                    return (market_slug, previous_pool_3)
        # If previous market 3 has both dates, check if target month falls within range
        elif previous_start_3 and previous_end_3:
            # Check if target month overlaps with previous market 3 period
            # Use <= for end date comparison to include the last day of the period
            overlaps = previous_start_3 <= month_end and previous_end_3 >= month_start
            if overlaps:
                market_slug = _normalize_market_name(previous_market_3)
                if market_slug:
                    return (market_slug, previous_pool_3)

    return None


def _normalize_market_name(market_name: Optional[str]) -> Optional[str]:
    """Normalize market name to match pool definitions (case-insensitive).

    Args:
        market_name: Raw market name from Odoo

    Returns:
        Normalized market slug (ksa, uae) or None
    """
    if not market_name:
        return None

    normalized = str(market_name).strip().lower()

    # Map common variations to pool slugs
    market_mapping = {
        "ksa": "ksa",
        "saudi arabia": "ksa",
        "kingdom of saudi arabia": "ksa",
        "uae": "uae",
        "united arab emirates": "uae",
        "emirates": "uae",
        "shared": "shared",  # Add shared as a valid market
    }

    # Check for exact match first
    if normalized in market_mapping:
        return market_mapping[normalized]

    # Check for partial matches (e.g., "UAE Market" contains "uae")
    for key, value in market_mapping.items():
        if key in normalized or normalized in key:
            return value

    # If no match found, return None
    # This ensures only recognized markets are returned
    return None
