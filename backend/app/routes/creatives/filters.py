"""Market/pool and BU/SBU/pod filter parsing and application."""
from __future__ import annotations

import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from dataclasses import dataclass
from calendar import month_name, monthrange
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Mapping, Optional, Set, Tuple
from flask import Blueprint, current_app, g, jsonify, render_template, request, session
from ...integrations.odoo_client import OdooClient, OdooUnavailableError
from ...services.assignment_service import (
    BusinessUnitAssignment,
    creative_matches_bu_assignment_filters,
    resolve_business_unit_for_month,
    split_assignment_field_tokens,
    use_business_unit_model,
)
from ...services.availability_service import AvailabilityService, AvailabilitySummary
from ...services.employee_service import EmployeeService
from ...services.external_hours_service import ExternalHoursService
from ...services.planning_service import PlanningService
from ...services.timesheet_service import TimesheetService
from ...services.utilization_service import (
    MONTHLY_UTILIZATION_CACHE_MIN,
    UtilizationService,
    _inclusive_month_tuple_sequence,
)
from ...services.supabase_cache_service import SupabaseCacheService
from ...services.sales_cache_service import SalesCacheService
from ...services.creative_market import (
    _get_creative_market_for_month,
    _normalize_market_name,
)
from ...services.comparison_service import ComparisonService
from ...services.email_settings_service import EmailSettingsService
from ...services.creative_hour_adjustments_service import CreativeHourAdjustmentsService
from ...services.strategy_and_external_hours_service import StrategyAndExternalHoursService
from ...services.email_service import EmailService
from ...services.alert_service import AlertService
from ...services.headcount_service import HeadcountService
from ...services.new_joiner_period import parse_joining_date, period_overlaps_new_joiner_ramp
from ..auth import require_sales_auth


def _filter_creatives_by_market_and_pool(
    creatives: List[Dict[str, object]],
    selected_markets: Optional[List[str]] = None,
    selected_pools: Optional[List[str]] = None,
) -> List[Dict[str, object]]:
    """Filter creatives by market and/or pool.
    
    Args:
        creatives: List of creative records
        selected_markets: List of market slugs to filter by (e.g., ['ksa', 'uae'])
        selected_pools: List of pool names to filter by
        
    Returns:
        Filtered list of creatives
    """
    if not selected_markets and not selected_pools:
        return creatives
    
    filtered = []
    for creative in creatives:
        market_slug = creative.get("market_slug")
        pool_name = creative.get("pool_name")

        # Market filter: if markets selected, creative must match one
        market_match = True
        if selected_markets:
            market_match = market_slug in selected_markets
        
        # Pool filter: if pools selected, creative must match one
        pool_match = True
        if selected_pools:
            pool_match = pool_name in selected_pools if pool_name else False
        
        # Both filters must pass (AND logic)
        if market_match and pool_match:
            filtered.append(creative)
    
    return filtered


def _get_available_markets_and_pools(
    creatives: List[Dict[str, object]]
) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    """Extract unique markets and pools from creatives.
    
    Returns:
        Tuple of (available_markets, available_pools) where each is a list of dicts
        with 'value' and 'label' keys
    """
    markets_set: set[str] = set()
    pools_set: set[str] = set()
    
    for creative in creatives:
        market_slug = creative.get("market_slug")
        market_display = creative.get("market_display")
        pool_name = creative.get("pool_name")
        
        if market_slug and market_display:
            markets_set.add(market_slug)
        
        if pool_name and pool_name != "No Pool":
            pools_set.add(pool_name)
    
    # Convert to sorted lists with display labels
    available_markets = []
    for market_slug in sorted(markets_set):
        # Find display name from first creative with this market
        display_name = None
        for creative in creatives:
            if creative.get("market_slug") == market_slug:
                display_name = creative.get("market_display")
                break
        
        available_markets.append({
            "value": market_slug,
            "label": display_name or market_slug.upper(),
        })
    
    available_pools = []
    for pool_name in sorted(pools_set):
        available_pools.append({
            "value": pool_name,
            "label": pool_name,
        })
    
    return available_markets, available_pools


def _parse_filter_params(request_args: Any) -> Tuple[List[str], List[str]]:
    """Parse market and pool filter parameters from request.
    
    Args:
        request_args: Flask request.args object
        
    Returns:
        Tuple of (selected_markets, selected_pools) as lists of strings
    """
    # Get market filter (can be multiple values)
    market_param = request_args.get("market")
    if market_param:
        if isinstance(market_param, str):
            selected_markets = [m.strip() for m in market_param.split(",") if m.strip()]
        elif isinstance(market_param, list):
            selected_markets = [m.strip() for m in market_param if isinstance(m, str) and m.strip()]
        else:
            selected_markets = []
    else:
        selected_markets = []
    
    # Get pool filter (can be multiple values)
    pool_param = request_args.get("pool")
    if pool_param:
        if isinstance(pool_param, str):
            selected_pools = [p.strip() for p in pool_param.split(",") if p.strip()]
        elif isinstance(pool_param, list):
            selected_pools = [p.strip() for p in pool_param if isinstance(p, str) and p.strip()]
        else:
            selected_pools = []
    else:
        selected_pools = []
    
    return selected_markets, selected_pools


def _parse_bu_assignment_filter_params(request_args: Any) -> Tuple[List[str], List[str], List[str]]:
    """Parse BU / SBU / pod filter query parameters (comma-separated or repeated)."""

    def _split_param(key: str) -> List[str]:
        raw = request_args.get(key)
        if not raw:
            return []
        if isinstance(raw, str):
            return [p.strip() for p in raw.split(",") if p.strip()]
        if isinstance(raw, list):
            return [str(p).strip() for p in raw if p is not None and str(p).strip()]
        return []

    return _split_param("bu"), _split_param("sbu"), _split_param("pod")


def _filter_creatives_by_bu_assignment(
    creatives: List[Dict[str, object]],
    selected_business_units: Optional[List[str]] = None,
    selected_sub_business_units: Optional[List[str]] = None,
    selected_pods: Optional[List[str]] = None,
) -> List[Dict[str, object]]:
    if not selected_business_units and not selected_sub_business_units and not selected_pods:
        return creatives
    return [
        c
        for c in creatives
        if creative_matches_bu_assignment_filters(
            c,
            selected_business_units,
            selected_sub_business_units,
            selected_pods,
        )
    ]


def _get_available_bu_assignment_options(
    creatives: List[Dict[str, object]],
) -> Tuple[List[Dict[str, str]], List[Dict[str, str]], List[Dict[str, str]]]:
    """Unique BU / SBU / Pod tokens from enriched assignment strings."""
    bu_tokens: Set[str] = set()
    sbu_tokens: Set[str] = set()
    pod_tokens: Set[str] = set()
    for creative in creatives:
        bu_tokens.update(split_assignment_field_tokens(creative.get("business_unit")))
        sbu_tokens.update(split_assignment_field_tokens(creative.get("sub_business_unit")))
        pod_tokens.update(split_assignment_field_tokens(creative.get("pod")))

    def _to_options(tokens: Set[str]) -> List[Dict[str, str]]:
        return [{"value": t, "label": t} for t in sorted(tokens)]

    return _to_options(bu_tokens), _to_options(sbu_tokens), _to_options(pod_tokens)


def _series_window(selected_month: date) -> int:
    """Determine how many trailing months of used-hours series to request."""
    # By default, include every month from January through the selected month.
    default_window = max(1, min(12, selected_month.month))
    override = os.getenv("CLIENT_SERIES_MONTH_WINDOW")
    if override is None:
        return default_window
    try:
        configured = int(override)
    except ValueError:
        return default_window
    return max(1, min(default_window, configured))
