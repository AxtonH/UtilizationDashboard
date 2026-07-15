"""Stats/aggregates/pool-stats computation, hour formatters, empty-state builders."""
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
from .deps import _get_comparison_service
from .view_period import DashboardViewPeriod, _month_part_options, _year_options


def _creatives_stats(
    creatives: List[Dict[str, object]],
    all_creatives_from_odoo: List[Dict[str, object]],
    market_anchor_month: date,
) -> Dict[str, int]:
    """Calculate creative statistics.

    Args:
        creatives: Filtered list of creatives (with market/pool for selected month)
        all_creatives_from_odoo: All creatives from Odoo (configured creative departments, e.g. Creative and Creative Strategy)
        market_anchor_month: Month used for market/pool assignment (end of period for quarters).

    Returns:
        Dictionary with total, available, and active counts
    """
    # Total Creatives: All creatives from Odoo in configured creative departments
    # Ensure we're using the full unfiltered list
    total = len(all_creatives_from_odoo) if all_creatives_from_odoo else 0
    
    # Available Creatives: Creatives with an assignment resolved for the selected month.
    # Pre-cutover this means market + pool; post-cutover (2026-04-01+) it means
    # a Business Unit slot whose dates contain the month.
    available = 0
    if all_creatives_from_odoo:
        if use_business_unit_model(market_anchor_month):
            for creative in all_creatives_from_odoo:
                bu = resolve_business_unit_for_month(creative, market_anchor_month)
                if bu is not None and (
                    bu.business_unit or bu.sub_business_unit or bu.pod
                ):
                    available += 1
        else:
            for creative in all_creatives_from_odoo:
                market_result = _get_creative_market_for_month(creative, market_anchor_month)
                if market_result is not None:
                    market_slug, pool_name = market_result
                    # Must have both market and pool (pool_name must not be None or empty)
                    if market_slug and pool_name:
                        available += 1

    # Active Creatives: Creatives with logged hours > 0 from the filtered list
    active = 0
    if creatives:
        for creative in creatives:
            logged_hours = float(creative.get("logged_hours", 0) or 0)
            if logged_hours > 0:
                active += 1

    return {"total": total, "available": available, "active": active}


def _creatives_aggregates(
    creatives: List[Dict[str, object]],
    view: Optional[DashboardViewPeriod] = None,
    include_comparison: bool = True,
    selected_markets: Optional[List[str]] = None,
    selected_pools: Optional[List[str]] = None,
    *,
    use_bu_assignment_filters: bool = False,
    selected_business_units: Optional[List[str]] = None,
    selected_sub_business_units: Optional[List[str]] = None,
    selected_pods: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Calculate aggregates with optional comparison to the previous month or quarter."""

    market_filter = {m.lower() for m in selected_markets or []} or None
    pool_filter = set(selected_pools or []) or None

    def _matches_filters(creative: Dict[str, object]) -> bool:
        if use_bu_assignment_filters:
            return creative_matches_bu_assignment_filters(
                creative,
                selected_business_units,
                selected_sub_business_units,
                selected_pods,
            )
        market_slug = creative.get("market_slug")
        pool_name = creative.get("pool_name")
        normalized_market = market_slug.lower() if isinstance(market_slug, str) else None
        if market_filter and (not normalized_market or normalized_market not in market_filter):
            return False
        if pool_filter:
            if not pool_name:
                return False
            if pool_name not in pool_filter:
                return False
        return True

    filtered_creatives = [c for c in creatives if _matches_filters(c)]

    totals = {"planned": 0.0, "logged": 0.0, "available": 0.0}
    for creative in filtered_creatives:
        totals["planned"] += float(creative.get("planned_hours", 0.0) or 0.0)
        totals["logged"] += float(creative.get("logged_hours", 0.0) or 0.0)
        totals["available"] += float(creative.get("available_hours", 0.0) or 0.0)
    max_value = max(totals.values()) if totals else 0.0
    display = {key: _format_hours_minutes(value) for key, value in totals.items()}

    result: Dict[str, Any] = {**totals, "max": max_value, "display": display}

    def _aggregate_previous_totals() -> Optional[Dict[str, float]]:
        previous_totals = {"planned": 0.0, "logged": 0.0, "available": 0.0}
        has_data = False
        for creative in creatives:
            if use_bu_assignment_filters:
                prev_proxy: Dict[str, object] = {
                    "business_unit": creative.get("previous_business_unit"),
                    "sub_business_unit": creative.get("previous_sub_business_unit"),
                    "pod": creative.get("previous_pod"),
                }
                if not creative_matches_bu_assignment_filters(
                    prev_proxy,
                    selected_business_units,
                    selected_sub_business_units,
                    selected_pods,
                ):
                    continue
            elif not _matches_filters(
                {
                    "business_unit": None,
                    "market_slug": creative.get("previous_market_slug"),
                    "pool_name": creative.get("previous_pool_name"),
                }
            ):
                continue
            prev_available = creative.get("previous_available_hours")
            prev_planned = creative.get("previous_planned_hours")
            prev_logged = creative.get("previous_logged_hours")
            if prev_available is None and prev_planned is None and prev_logged is None:
                continue
            has_data = True
            previous_totals["available"] += float(prev_available or 0.0)
            previous_totals["planned"] += float(prev_planned or 0.0)
            previous_totals["logged"] += float(prev_logged or 0.0)
        return previous_totals if has_data else None

    def _calculate_comparison_from_totals(
        current_totals: Dict[str, float], previous_totals: Dict[str, float]
    ) -> Dict[str, Any]:
        def _change(current_value: float, previous_value: float) -> Optional[float]:
            if previous_value == 0:
                return None if current_value == 0 else 100.0
            return ((current_value - previous_value) / previous_value) * 100.0

        current_available = current_totals.get("available", 0.0)
        current_logged = current_totals.get("logged", 0.0)
        current_planned = current_totals.get("planned", 0.0)

        previous_available = previous_totals.get("available", 0.0)
        previous_logged = previous_totals.get("logged", 0.0)
        previous_planned = previous_totals.get("planned", 0.0)

        current_utilization = (current_logged / current_available * 100.0) if current_available > 0 else 0.0
        previous_utilization = (previous_logged / previous_available * 100.0) if previous_available > 0 else 0.0

        current_booking = (current_planned / current_available * 100.0) if current_available > 0 else 0.0
        previous_booking = (previous_planned / previous_available * 100.0) if previous_available > 0 else 0.0

        return {
            "available": {
                "value": current_available,
                "change": _change(current_available, previous_available),
            },
            "planned": {
                "value": current_planned,
                "change": _change(current_planned, previous_planned),
            },
            "logged": {
                "value": current_logged,
                "change": _change(current_logged, previous_logged),
            },
            "utilization": {
                "value": current_utilization,
                "change": _change(current_utilization, previous_utilization),
            },
            "booking_capacity": {
                "value": current_booking,
                "change": _change(current_booking, previous_booking),
            },
        }

    def _empty_comparison() -> Dict[str, Any]:
        return {
            "available": {"value": totals["available"], "change": None},
            "planned": {"value": totals["planned"], "change": None},
            "logged": {"value": totals["logged"], "change": None},
            "utilization": {"value": None, "change": None},
            "booking_capacity": {"value": None, "change": None},
        }

    if include_comparison and view:
        comparison: Optional[Dict[str, Any]] = None
        if view.has_previous_period:
            previous_totals = _aggregate_previous_totals()
            if previous_totals is not None:
                comparison = _calculate_comparison_from_totals(totals, previous_totals)
            else:
                try:
                    comparison_service = _get_comparison_service()
                    prev_anchor = date(
                        view.previous_period_end.year, view.previous_period_end.month, 1
                    )
                    previous_aggregates = comparison_service.calculate_aggregates_for_date_range(
                        view.previous_period_start,
                        view.previous_period_end,
                        prev_anchor,
                        filtered_creatives,
                    )
                    if previous_aggregates is not None:
                        comparison = comparison_service.calculate_comparison(totals, previous_aggregates)
                    else:
                        comparison = _empty_comparison()
                except Exception as exc:
                    current_app.logger.warning(
                        f"Failed to calculate comparison via service: {exc}", exc_info=True
                    )
                    comparison = _empty_comparison()
        else:
            comparison = _empty_comparison()

        result["comparison"] = comparison

    return result


def _pool_stats(creatives: List[Dict[str, object]], selected_month: date) -> List[Dict[str, Any]]:
    """Calculate market statistics based on market assignments for the selected month.
    
    Uses market fields (x_studio_rf_market_1 and x_studio_rf_market_2) with date-based
    logic to determine which market each creative belongs to for the selected month.
    Only includes market-based pools (KSA, UAE).
    
    Args:
        creatives: List of creative employee records (already filtered to only include those with markets)
        selected_month: The month being viewed (first day of month)
        
    Returns:
        List of market statistics dictionaries
    """
    # Only include market-based pools (KSA, UAE)
    market_pools = [
        {"name": "KSA", "slug": "ksa"},
        {"name": "UAE", "slug": "uae"},
    ]

    results: List[Dict[str, Any]] = []
    
    # Process market-based pools using market_slug from creatives
    for pool in market_pools:
        pool_slug = pool["slug"]
        members = [
            creative
            for creative in creatives
            if creative.get("market_slug") == pool_slug
        ]
        
        total = len(members)
        available = sum(1 for creative in members if float(creative.get("available_hours", 0) or 0) > 0)
        active = sum(1 for creative in members if float(creative.get("logged_hours", 0) or 0) > 0)
        total_available_hours = sum(float(creative.get("available_hours", 0) or 0) for creative in members)
        total_planned_hours = sum(float(creative.get("planned_hours", 0) or 0) for creative in members)
        total_logged_hours = sum(float(creative.get("logged_hours", 0) or 0) for creative in members)
        
        results.append(
            {
                "name": pool["name"],
                "slug": pool["slug"],
                "total_creatives": total,
                "available_creatives": available,
                "active_creatives": active,
                "available_hours": total_available_hours,
                "available_hours_display": _format_hours_minutes(total_available_hours),
                "planned_hours": total_planned_hours,
                "planned_hours_display": _format_hours_minutes(total_planned_hours),
                "logged_hours": total_logged_hours,
                "logged_hours_display": _format_hours_minutes(total_logged_hours),
            }
        )
    
    return results


def _format_hours_minutes(value: float) -> str:
    total_minutes = int(round(value * 60))
    hours, minutes = divmod(total_minutes, 60)
    if minutes == 0:
        return f"{hours}h"
    return f"{hours}h {minutes:02d}m"


def _calculate_utilization(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return round((numerator / denominator) * 100, 1)


def _format_percentage(value: float) -> str:
    rounded = round(value, 1)
    if float(rounded).is_integer():
        return f"{int(rounded)}%"
    return f"{rounded:.1f}%"


def _utilization_status(planned_percent: float, logged_percent: float) -> str:
    if planned_percent < 50 or logged_percent < 50:
        return "critical"
    if planned_percent < 75 or logged_percent < 75:
        return "warning"
    return "healthy"


def _format_hours_display(value: float) -> str:
    if not value or abs(value) < 1e-6:
        return "0h"
    rounded = round(value, 1)
    if abs(rounded - round(rounded)) < 0.1:
        return f"{int(round(rounded)):,}h"
    return f"{rounded:,.1f}h"


def _base_dashboard_state(selected_month: date) -> Dict[str, Any]:
    """Provide a minimal dashboard state when downstream services are unavailable."""
    zero_display = _format_hours_minutes(0.0)
    aggregates = {
        "planned": 0.0,
        "logged": 0.0,
        "available": 0.0,
        "max": 0.0,
        "display": {
            "planned": zero_display,
            "logged": zero_display,
            "available": zero_display,
        },
    }
    state: Dict[str, Any] = {
        "creatives": [],
        "stats": {"total": 0, "available": 0, "active": 0},
        "aggregates": aggregates,
        "pool_stats": _pool_stats([], selected_month),
        "odoo_unavailable": True,
    }
    return state


def _empty_dashboard_context(view: DashboardViewPeriod, error_message: str) -> Dict[str, Any]:
    """Compose the context for rendering the dashboard when Odoo is unreachable."""
    context = _base_dashboard_state(view.market_anchor_month)
    selected_part = f"Q{view.quarter}" if view.is_quarter and view.quarter else f"{view.period_start.month:02d}"
    context.update(
        {
            "month_part_options": _month_part_options(),
            "year_options": _year_options(view.period_start),
            "selected_month_part": selected_part,
            "selected_year": str(view.period_start.year),
            "period_kind": "quarter" if view.is_quarter else "month",
            "selected_month": view.selected_month_key,
            "readable_month": view.display_label,
            "has_previous_month": view.has_previous_period,
            "odoo_error_message": error_message,
            "show_creatives_market_filter": bool(session.get("dashboard_market_filter_visible")),
            "dashboard_authenticated": bool(session.get("dashboard_authenticated")),
        }
    )
    return context


def _empty_utilization_summary() -> Dict[str, Any]:
    """Provide default utilization metrics when backend data cannot be loaded."""
    zero_hours = _format_hours_display(0.0)
    return {
        "available_creatives": 0,
        "total_available_hours": 0.0,
        "total_planned_hours": 0.0,
        "total_logged_hours": 0.0,
        "total_external_used_hours": 0.0,
        "available_hours_display": zero_hours,
        "planned_hours_display": zero_hours,
        "logged_hours_display": zero_hours,
        "external_used_hours_display": zero_hours,
        "pool_stats": [],
    }
