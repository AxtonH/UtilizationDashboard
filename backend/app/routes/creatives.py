"""Routes for creatives dashboard."""
from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from dataclasses import dataclass
from calendar import month_name, monthrange
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Mapping, Optional, Set, Tuple

from flask import Blueprint, current_app, g, jsonify, render_template, request, session

from ..integrations.odoo_client import OdooClient, OdooUnavailableError
from ..services.assignment_service import (
    BusinessUnitAssignment,
    creative_matches_bu_assignment_filters,
    resolve_business_unit_for_month,
    split_assignment_field_tokens,
    use_business_unit_model,
)
from ..services.availability_service import AvailabilityService, AvailabilitySummary
from ..services.employee_service import EmployeeService
from ..services.external_hours_service import ExternalHoursService
from ..services.planning_service import PlanningService
from ..services.timesheet_service import TimesheetService
from ..services.utilization_service import UtilizationService
from ..services.supabase_cache_service import SupabaseCacheService
from ..services.sales_cache_service import SalesCacheService
from ..services.comparison_service import ComparisonService
from ..services.email_settings_service import EmailSettingsService
from ..services.creative_hour_adjustments_service import CreativeHourAdjustmentsService
from ..services.email_service import EmailService
from ..services.alert_service import AlertService
from ..services.headcount_service import HeadcountService
from ..services.new_joiner_period import parse_joining_date, period_overlaps_new_joiner_ramp
from .auth import require_sales_auth

creatives_bp = Blueprint("creatives", __name__)


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


def _get_odoo_client() -> OdooClient:
    settings = current_app.config["ODOO_SETTINGS"]
    if "odoo_client" not in g:
        g.odoo_client = OdooClient(settings)
    return g.odoo_client


def _get_employee_service() -> EmployeeService:
    if "employee_service" not in g:
        g.employee_service = EmployeeService(_get_odoo_client())
    return g.employee_service


def _get_availability_service() -> AvailabilityService:
    if "availability_service" not in g:
        g.availability_service = AvailabilityService(_get_odoo_client())
    return g.availability_service


def _get_planning_service() -> PlanningService:
    if "planning_service" not in g:
        g.planning_service = PlanningService(_get_odoo_client())
    return g.planning_service


def _get_timesheet_service() -> TimesheetService:
    if "timesheet_service" not in g:
        g.timesheet_service = TimesheetService(_get_odoo_client())
    return g.timesheet_service


def _get_external_hours_service() -> ExternalHoursService:
    if "external_hours_service" not in g:
        cache_service = None
        try:
            # Try to initialize Supabase cache service if credentials are available
            cache_service = SupabaseCacheService.from_env()
            current_app.logger.info("Supabase cache service initialized successfully")
        except RuntimeError as e:
            # If Supabase is not configured, continue without cache
            error_msg = str(e)
            if "SUPABASE_URL and SUPABASE_KEY" in error_msg:
                current_app.logger.debug(
                    "Supabase cache not configured: Missing SUPABASE_URL or SUPABASE_KEY environment variables. "
                    "Using Odoo directly. See SUPABASE_SETUP.md for configuration instructions."
                )
            elif "supabase-py is not available" in error_msg or "Import error" in error_msg:
                current_app.logger.warning(
                    f"Supabase cache not available: {error_msg}. "
                    "Using Odoo directly. Make sure supabase is installed in the same Python environment as your Flask app."
                )
            elif "supabase-py is not installed" in error_msg:
                current_app.logger.warning(
                    "Supabase cache not available: supabase-py library not installed. "
                    "Install with: pip install supabase. Using Odoo directly."
                )
            else:
                current_app.logger.debug(f"Supabase cache not available: {error_msg}. Using Odoo directly.")
        except Exception as e:
            # Catch any other unexpected errors
            current_app.logger.warning(
                f"Failed to initialize Supabase cache service: {e}. "
                "Using Odoo directly. Check your Supabase configuration."
            )
        g.external_hours_service = ExternalHoursService(
            _get_odoo_client(), cache_service=cache_service
        )
    return g.external_hours_service


def _client_external_hours_markets_for_period(
    month_start: date,
    month_end: date,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Sales-order external hours + subscription used hours, grouped by market (Company Wide Utilization)."""
    try:
        service = _get_external_hours_service()
        ext = service.external_hours_for_month(month_start, month_end)
        sub = service.subscription_hours_for_month(month_start, month_end)
        markets_ext = ext.get("markets") if isinstance(ext.get("markets"), list) else []
        markets_sub = sub.get("markets") if isinstance(sub.get("markets"), list) else []
        return markets_ext, markets_sub
    except Exception:
        current_app.logger.warning(
            "Could not load client external hours markets for period",
            exc_info=True,
        )
        return [], []


def _get_comparison_service() -> ComparisonService:
    if "comparison_service" not in g:
        g.comparison_service = ComparisonService(
            _get_employee_service(),
            _get_availability_service(),
            _get_planning_service(),
            _get_timesheet_service(),
        )
    return g.comparison_service


def _get_headcount_service() -> HeadcountService:
    if "headcount_service" not in g:
        g.headcount_service = HeadcountService(_get_employee_service())
    return g.headcount_service


def _get_tasks_service() -> "TasksService":
    if "tasks_service" not in g:
        from ..services.tasks_service import TasksService
        g.tasks_service = TasksService.from_comparison_service(_get_comparison_service())
    return g.tasks_service


def _get_overtime_service() -> "OvertimeService":
    if "overtime_service" not in g:
        from ..services.overtime_service import OvertimeService
        g.overtime_service = OvertimeService.from_settings(current_app.config["ODOO_SETTINGS"])
    return g.overtime_service


def _get_utilization_service() -> UtilizationService:
    if "utilization_service" not in g:
        g.utilization_service = UtilizationService(
            _get_employee_service(),
            _get_availability_service(),
            _get_planning_service(),
            _get_timesheet_service(),
            _get_external_hours_service(),
        )
    return g.utilization_service


def _get_sales_service() -> "SalesService":
    if "sales_service" not in g:
        from ..services.sales_service import SalesService
        g.sales_service = SalesService(_get_odoo_client())
    return g.sales_service


def _new_sales_service(settings: Optional[OdooSettings] = None) -> "SalesService":
    """Create a fresh SalesService with its own OdooClient (for safe parallel calls).
    
    Args:
        settings: Optional pre-fetched OdooSettings to avoid relying on flask context inside threads.
    """
    from ..services.sales_service import SalesService
    odoo_settings = settings or current_app.config["ODOO_SETTINGS"]
    return SalesService(OdooClient(odoo_settings))


def _get_sales_cache_service() -> Optional[SalesCacheService]:
    if "sales_cache_service" not in g:
        try:
            g.sales_cache_service = SalesCacheService.from_env()
        except Exception as e:
            current_app.logger.warning(f"Failed to initialize SalesCacheService: {e}")
            g.sales_cache_service = None
    return g.sales_cache_service


@creatives_bp.before_app_request
def _inject_service_into_app_context() -> None:
    """Ensure Odoo settings dataclass is available via config for reuse."""
    if "ODOO_SETTINGS" not in current_app.config:
        from ..config import Config

        current_app.config["ODOO_SETTINGS"] = Config.odoo_settings()


@creatives_bp.teardown_app_request
def _cleanup_services(_: BaseException | None) -> None:
    """Release shared Odoo client when the request finishes."""
    client = g.pop("odoo_client", None)
    if client is not None:
        try:
            client.close()
        except Exception:
            current_app.logger.debug("Failed to close Odoo client cleanly", exc_info=True)

    g.pop("employee_service", None)
    g.pop("availability_service", None)
    g.pop("planning_service", None)
    g.pop("timesheet_service", None)
    g.pop("external_hours_service", None)
    g.pop("utilization_service", None)
    g.pop("sales_service", None)
    g.pop("sales_cache_service", None)



@creatives_bp.route("/")
def dashboard():
    view = _resolve_view_period()
    month_start, month_end = view.period_start, view.period_end
    has_previous_period = view.has_previous_period
    try:
        # Get all creatives from Odoo FIRST (before any filtering) for total creatives count
        # Use get_all_creatives() to include inactive creatives in the total count
        employee_service = _get_employee_service()
        all_creatives_from_odoo = employee_service.get_all_creatives(include_inactive=True)
        
        # Now get creatives with availability (this filters to only those with market/pool)
        # Pass the same list to avoid double-fetching
        all_creatives = _creatives_with_availability(view, all_creatives_from_odoo)
        
        use_bu_assignment_filters = use_business_unit_model(view.market_anchor_month)
        selected_business_units, selected_sub_business_units, selected_pods = (
            _parse_bu_assignment_filter_params(request.args)
        )
        selected_markets, selected_pools = _parse_filter_params(request.args)
        if not session.get("dashboard_market_filter_visible"):
            selected_markets = []

        if use_bu_assignment_filters:
            creatives = _filter_creatives_by_bu_assignment(
                all_creatives,
                selected_business_units if selected_business_units else None,
                selected_sub_business_units if selected_sub_business_units else None,
                selected_pods if selected_pods else None,
            )
            available_business_units, available_sub_business_units, available_pods_opts = (
                _get_available_bu_assignment_options(all_creatives)
            )
            available_markets, available_pools = [], []
        else:
            creatives = _filter_creatives_by_market_and_pool(
                all_creatives,
                selected_markets if selected_markets else None,
                selected_pools if selected_pools else None,
            )
            available_markets, available_pools = _get_available_markets_and_pools(all_creatives)
            available_business_units = []
            available_sub_business_units = []
            available_pods_opts = []
        
        # Parallelize independent operations to reduce load time
        # Capture app context and settings before threading
        app = current_app._get_current_object()
        settings = current_app.config["ODOO_SETTINGS"]
        agreement_type = request.args.get("agreement_type")
        account_type = request.args.get("account_type")
        
        def _compute_stats_with_context():
            with app.app_context():
                return _creatives_stats(creatives, all_creatives_from_odoo, view.market_anchor_month)
        
        def _compute_aggregates_with_context():
            with app.app_context():
                if use_bu_assignment_filters:
                    return _creatives_aggregates(
                        all_creatives,
                        view,
                        include_comparison=True,
                        use_bu_assignment_filters=True,
                        selected_business_units=selected_business_units if selected_business_units else None,
                        selected_sub_business_units=(
                            selected_sub_business_units if selected_sub_business_units else None
                        ),
                        selected_pods=selected_pods if selected_pods else None,
                    )
                return _creatives_aggregates(
                    all_creatives,
                    view,
                    include_comparison=True,
                    selected_markets=selected_markets if selected_markets else None,
                    selected_pools=selected_pools if selected_pools else None,
                )
        
        def _compute_pool_stats_with_context():
            with app.app_context():
                return _pool_stats(creatives, view.market_anchor_month)
        
        def _compute_headcount_with_context():
            with app.app_context():
                headcount_service = HeadcountService(_get_employee_service())
                if use_bu_assignment_filters:
                    return headcount_service.calculate_headcount(
                        view.period_start,
                        all_creatives_from_odoo,
                        all_creatives,
                        use_bu_assignment_filters=True,
                        selected_business_units=(
                            selected_business_units if selected_business_units else None
                        ),
                        selected_sub_business_units=(
                            selected_sub_business_units if selected_sub_business_units else None
                        ),
                        selected_pods=selected_pods if selected_pods else None,
                        period_end_inclusive=month_end,
                    )
                return headcount_service.calculate_headcount(
                    view.period_start,
                    all_creatives_from_odoo,
                    all_creatives,
                    selected_markets=selected_markets if selected_markets else None,
                    selected_pools=selected_pools if selected_pools else None,
                    period_end_inclusive=month_end,
                )
        
        def _compute_overtime_stats_with_context():
            with app.app_context():
                from ..services.overtime_service import OvertimeService
                overtime_service = OvertimeService.from_settings(settings)
                return overtime_service.calculate_overtime_statistics(
                    month_start, 
                    month_end,
                    creatives=all_creatives,
                )
        
        def _compute_utilization_series_with_context():
            with app.app_context():
                utilization_service = _get_utilization_service()
                utilization_cache_service = None
                try:
                    from ..services.utilization_cache_service import UtilizationCacheService
                    utilization_cache_service = UtilizationCacheService.from_env()
                except Exception as e:
                    current_app.logger.debug(f"Utilization cache not available: {e}")
                
                return utilization_service.calculate_monthly_utilization_series(
                    view.series_anchor_month,
                    cache_service=utilization_cache_service,
                )
        
        def _compute_client_external_with_context():
            with app.app_context():
                return _client_external_hours_markets_for_period(month_start, month_end)

        # Execute all computations in parallel with smart dependency handling
        with ThreadPoolExecutor(max_workers=8) as executor:
            future_stats = executor.submit(_compute_stats_with_context)
            future_aggregates = executor.submit(_compute_aggregates_with_context)
            future_pool_stats = executor.submit(_compute_pool_stats_with_context)
            future_headcount = executor.submit(_compute_headcount_with_context)
            future_overtime_stats = executor.submit(_compute_overtime_stats_with_context)
            future_utilization_series = executor.submit(_compute_utilization_series_with_context)
            future_client_external = executor.submit(_compute_client_external_with_context)
            
            # Start tasks calculation as soon as headcount is ready
            def _compute_tasks_after_headcount():
                with app.app_context():
                    # Wait for headcount to complete
                    hc = future_headcount.result()
                    tasks_service = _get_tasks_service()
                    return tasks_service.calculate_tasks_statistics(
                        all_creatives,
                        month_start,
                        month_end,
                        hc.get("total", 0),
                    )
            
            future_tasks = executor.submit(_compute_tasks_after_headcount)
            
            # Wait for all results
            stats = future_stats.result()
            aggregates = future_aggregates.result()
            pool_stats = future_pool_stats.result()
            headcount = future_headcount.result()
            overtime_stats = future_overtime_stats.result()
            tasks_stats = future_tasks.result()
            monthly_utilization_series = future_utilization_series.result()
            client_external_hours_all, client_subscription_hours_all = future_client_external.result()

        selected_part = f"Q{view.quarter}" if view.is_quarter and view.quarter else f"{view.period_start.month:02d}"
        context = {
            "creatives": creatives,
            "month_part_options": _month_part_options(),
            "year_options": _year_options(view.period_start),
            "selected_month_part": selected_part,
            "selected_year": str(view.period_start.year),
            "period_kind": "quarter" if view.is_quarter else "month",
            "selected_month": view.selected_month_key,
            "readable_month": view.display_label,
            "stats": stats,
            "aggregates": aggregates,
            "pool_stats": pool_stats,
            "headcount": headcount,
            "tasks_stats": tasks_stats,
            "overtime_stats": overtime_stats,
            "monthly_utilization_series": monthly_utilization_series,
            "available_markets": available_markets,
            "available_pools": available_pools,
            "available_business_units": available_business_units,
            "available_sub_business_units": available_sub_business_units,
            "available_pods": available_pods_opts,
            "selected_markets": selected_markets,
            "selected_pools": selected_pools,
            "selected_business_units": selected_business_units,
            "selected_sub_business_units": selected_sub_business_units,
            "selected_pods": selected_pods,
            "creatives_use_bu_assignment_filters": use_bu_assignment_filters,
            "has_previous_month": has_previous_period,
            "odoo_unavailable": False,
            "odoo_error_message": None,
            "show_creatives_market_filter": bool(session.get("dashboard_market_filter_visible")),
            "client_external_hours_all": client_external_hours_all,
            "client_subscription_hours_all": client_subscription_hours_all,
        }
        return render_template("creatives/dashboard.html", **context)
    except OdooUnavailableError as exc:
        current_app.logger.warning("Odoo unavailable while rendering dashboard", exc_info=True)
        context = _empty_dashboard_context(
            _resolve_view_period(),
            error_message=str(exc) if str(exc) else "Unable to connect to Odoo. Please try again shortly.",
        )
        context["available_markets"] = []
        context["available_pools"] = []
        context["available_business_units"] = []
        context["available_sub_business_units"] = []
        context["available_pods"] = []
        context["selected_markets"] = []
        context["selected_pools"] = []
        context["selected_business_units"] = []
        context["selected_sub_business_units"] = []
        context["selected_pods"] = []
        context["creatives_use_bu_assignment_filters"] = use_business_unit_model(
            _resolve_view_period().market_anchor_month
        )
        context["show_creatives_market_filter"] = bool(session.get("dashboard_market_filter_visible"))
        context["client_external_hours_all"] = []
        context["client_subscription_hours_all"] = []
        return render_template("creatives/dashboard.html", **context), 503


@creatives_bp.route("/api/creatives")
def creatives_api():
    view = _resolve_view_period()
    month_start, month_end = view.period_start, view.period_end
    has_previous_period = view.has_previous_period
    try:
        # Get all creatives from Odoo FIRST (before any filtering) for total creatives count
        # Use get_all_creatives() to include inactive creatives in the total count
        employee_service = _get_employee_service()
        all_creatives_from_odoo = employee_service.get_all_creatives(include_inactive=True)
        
        # Now get creatives with availability (this filters to only those with market/pool)
        # Pass the same list to avoid double-fetching
        all_creatives = _creatives_with_availability(view, all_creatives_from_odoo)
        
        # Assignment filters (market/pool or BU/SBU/pod) are applied client-side; the API
        # returns the full enriched list plus filter option metadata for the viewed month.
        _parse_filter_params(request.args)
        _parse_bu_assignment_filter_params(request.args)

        creatives = all_creatives

        use_bu_assignment_filters = use_business_unit_model(view.market_anchor_month)
        if use_bu_assignment_filters:
            available_markets, available_pools = [], []
            available_business_units, available_sub_business_units, available_pods_opts = (
                _get_available_bu_assignment_options(all_creatives)
            )
        else:
            available_markets, available_pools = _get_available_markets_and_pools(all_creatives)
            available_business_units = []
            available_sub_business_units = []
            available_pods_opts = []
        
        
        # Parallelize computations for faster API response
        app = current_app._get_current_object()
        settings = current_app.config["ODOO_SETTINGS"]
        agreement_type = request.args.get("agreement_type")
        account_type = request.args.get("account_type")
        
        def _compute_stats_api():
            with app.app_context():
                return _creatives_stats(creatives, all_creatives_from_odoo, view.market_anchor_month)
        
        def _compute_aggregates_api():
            with app.app_context():
                # No market/pool filtering for aggregates since we return all creatives
                return _creatives_aggregates(
                    all_creatives,
                    view,
                    include_comparison=True,
                    selected_markets=None,
                    selected_pools=None,
                )
        
        def _compute_pool_stats_api():
            with app.app_context():
                return _pool_stats(creatives, view.market_anchor_month)
        
        def _compute_headcount_api():
            with app.app_context():
                headcount_service = HeadcountService(_get_employee_service())
                # No market/pool filtering for headcount since we return all creatives
                return headcount_service.calculate_headcount(
                    view.period_start,
                    all_creatives_from_odoo, 
                    all_creatives,
                    selected_markets=None,
                    selected_pools=None,
                    period_end_inclusive=month_end,
                )
        
        def _compute_overtime_api():
            with app.app_context():
                from ..services.overtime_service import OvertimeService
                overtime_service = OvertimeService.from_settings(settings)
                # Return overtime for all creatives - filtering happens client-side
                return overtime_service.calculate_overtime_statistics(
                    month_start, 
                    month_end,
                    creatives=all_creatives,
                )

        def _compute_client_external_api():
            with app.app_context():
                return _client_external_hours_markets_for_period(month_start, month_end)
        
        with ThreadPoolExecutor(max_workers=7) as executor:
            future_stats = executor.submit(_compute_stats_api)
            future_aggregates = executor.submit(_compute_aggregates_api)
            future_pool_stats = executor.submit(_compute_pool_stats_api)
            future_headcount = executor.submit(_compute_headcount_api)
            future_overtime = executor.submit(_compute_overtime_api)
            future_client_external = executor.submit(_compute_client_external_api)
            
            # Tasks depends on headcount
            def _compute_tasks_api():
                with app.app_context():
                    hc = future_headcount.result()
                    tasks_service = _get_tasks_service()
                    # Return tasks for all creatives - filtering happens client-side
                    return tasks_service.calculate_tasks_statistics(
                        all_creatives,
                        month_start,
                        month_end,
                        hc.get("total", 0),
                    )
            
            future_tasks = executor.submit(_compute_tasks_api)
            
            # Collect results
            stats = future_stats.result()
            aggregates = future_aggregates.result()
            pool_stats = future_pool_stats.result()
            headcount = future_headcount.result()
            overtime_stats = future_overtime.result()
            tasks_stats = future_tasks.result()
            client_external_hours_all, client_subscription_hours_all = future_client_external.result()

        
        response_payload: Dict[str, Any] = {
            "creatives": creatives,
            "selected_month": view.selected_month_key,
            "readable_month": view.display_label,
            "period_kind": "quarter" if view.is_quarter else "month",
            "quarter": view.quarter,
            "stats": stats,
            "aggregates": aggregates,
            "pool_stats": pool_stats,
            "headcount": headcount,
            "tasks_stats": tasks_stats,
            "overtime_stats": overtime_stats,
            "available_markets": available_markets,
            "available_pools": available_pools,
            "available_business_units": available_business_units,
            "available_sub_business_units": available_sub_business_units,
            "available_pods": available_pods_opts,
            "use_bu_assignment_filters": use_bu_assignment_filters,
            "selected_markets": [],  # Client-side filtering only
            "selected_pools": [],    # Client-side filtering only
            "client_external_hours_all": client_external_hours_all,
            "client_subscription_hours_all": client_subscription_hours_all,
            "has_previous_month": has_previous_period,
            "odoo_unavailable": False,
        }
        return jsonify(response_payload)
    except OdooUnavailableError as exc:
        current_app.logger.warning("Odoo unavailable while serving creatives API", exc_info=True)
        error_message = str(exc) if str(exc) else "Unable to connect to Odoo. Please try again later."
        v = _resolve_view_period()
        fallback_state = _base_dashboard_state(v.market_anchor_month)
        response_payload = {
            **fallback_state,
            "selected_month": v.selected_month_key,
            "readable_month": v.display_label,
            "period_kind": "quarter" if v.is_quarter else "month",
            "quarter": v.quarter,
            "available_markets": [],
            "available_pools": [],
            "available_business_units": [],
            "available_sub_business_units": [],
            "available_pods": [],
            "use_bu_assignment_filters": use_business_unit_model(v.market_anchor_month),
            "selected_markets": [],
            "selected_pools": [],
            "client_external_hours_all": [],
            "client_subscription_hours_all": [],
            "has_previous_month": v.has_previous_period,
            "error": "odoo_unavailable",
            "message": error_message,
            "odoo_unavailable": True,
        }
        return jsonify(response_payload), 503


@creatives_bp.route("/api/utilization")
def utilization_api():
    view = _resolve_view_period()
    try:
        month_start, month_end = view.period_start, view.period_end
        utilization_service = _get_utilization_service()
        summary = utilization_service.get_utilization_summary(
            month_start, month_end, pool_assignment_month=view.market_anchor_month
        )
        summary["odoo_unavailable"] = False
        summary["selected_month"] = view.selected_month_key
        summary["readable_month"] = view.display_label
        return jsonify(summary)
    except OdooUnavailableError as exc:
        current_app.logger.warning("Odoo unavailable while serving utilization API", exc_info=True)
        error_message = str(exc) if str(exc) else "Unable to connect to Odoo. Please try again later."
        v = _resolve_view_period()
        summary = _empty_utilization_summary()
        summary.update(
            {
                "selected_month": v.selected_month_key,
                "readable_month": v.display_label,
                "error": "odoo_unavailable",
                "message": error_message,
                "odoo_unavailable": True,
            }
        )
        return jsonify(summary), 503


@creatives_bp.route("/api/sales")
@require_sales_auth
def sales_api():
    """Sales stats and charts for the selected calendar month or quarter (same window as creatives)."""
    view = _resolve_view_period()
    period_start, period_end = view.period_start, view.period_end
    sales_anchor = view.market_anchor_month
    upto_month_for_series = (view.quarter * 3) if view.is_quarter and view.quarter else sales_anchor.month
    try:
        cache_service = _get_sales_cache_service()

        # Run lookups in parallel using separate Odoo clients per worker to avoid XML-RPC thread issues
        from concurrent.futures import ThreadPoolExecutor

        # Capture settings once in the main Flask context
        odoo_settings = current_app.config["ODOO_SETTINGS"]

        def svc_call(method_name, *args, **kwargs):
            svc = _new_sales_service(odoo_settings)
            return getattr(svc, method_name)(*args, **kwargs)

        previous_period = None
        if view.has_previous_period:
            previous_period = (view.previous_period_start, view.previous_period_end)

        def run_sales_statistics():
            svc = _new_sales_service(odoo_settings)
            return svc.calculate_sales_statistics(
                period_start, period_end, previous_period=previous_period
            )

        def run_invoiced_series():
            svc = _new_sales_service(odoo_settings)
            series, breakdown = svc.get_monthly_invoiced_series_with_breakdown(
                view.period_start.year,
                upto_month_for_series,
                cache_service,
            )
            if view.is_quarter and view.quarter:
                series = svc.aggregate_monthly_series_to_quarterly(series, view.quarter)
            return series, breakdown

        def run_sales_orders_series():
            svc = _new_sales_service(odoo_settings)
            series, breakdown = svc.get_monthly_sales_orders_series_with_breakdown(
                view.period_start.year,
                upto_month_for_series,
                cache_service,
            )
            if view.is_quarter and view.quarter:
                series = svc.aggregate_monthly_series_to_quarterly(series, view.quarter)
            return series, breakdown

        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = {
                "sales_stats": executor.submit(run_sales_statistics),
                "invoiced": executor.submit(run_invoiced_series),
                "sales_orders_series": executor.submit(run_sales_orders_series),
                "agreement_totals": executor.submit(
                    svc_call, "get_invoice_totals_by_agreement_type", period_start, period_end
                ),
                "sales_orders_agreement_totals": executor.submit(
                    svc_call, "get_sales_orders_totals_by_agreement_type", period_start, period_end
                ),
                "sales_orders_project_totals": executor.submit(
                    svc_call, "get_sales_orders_totals_by_project", period_start, period_end, 6
                ),
                "subscriptions": executor.submit(
                    svc_call, "get_subscriptions_for_month", period_start, period_end
                ),
            }

            sales_stats = futures["sales_stats"].result()
            invoiced_series, invoiced_series_breakdown = futures["invoiced"].result()
            sales_orders_series, sales_orders_series_breakdown = futures["sales_orders_series"].result()
            agreement_totals = futures["agreement_totals"].result()
            sales_orders_agreement_totals = futures["sales_orders_agreement_totals"].result()
            sales_orders_project_totals = futures["sales_orders_project_totals"].result()
            subscriptions = futures["subscriptions"].result()
            
            # Reuse fetched data to avoid duplicate Odoo calls
            base_service = _get_sales_service()
            subscription_stats = base_service.get_subscription_statistics(period_start, period_end, subscriptions=subscriptions)
            sales_orders_for_month = sales_stats.get("sales_orders") if isinstance(sales_stats, dict) else None
            external_hours_totals = base_service.get_external_hours_totals(
                period_start,
                period_end,
                subscriptions=subscriptions,
                sales_orders=sales_orders_for_month,
                previous_period=previous_period,
            )
            external_hours_by_agreement = base_service.get_external_hours_by_agreement_type(
                period_start, period_end, subscriptions=subscriptions, sales_orders=sales_orders_for_month
            )


        response_payload = {
            "sales_stats": sales_stats,
            "invoiced_series": invoiced_series,
            "invoiced_series_breakdown": invoiced_series_breakdown,
            "sales_orders_series": sales_orders_series,
            "sales_orders_series_breakdown": sales_orders_series_breakdown,
            "agreement_type_totals": agreement_totals,
            "sales_orders_agreement_type_totals": sales_orders_agreement_totals,
            "sales_orders_project_totals": sales_orders_project_totals,
            "subscriptions": subscriptions,
            "subscription_stats": subscription_stats,
            "external_hours_totals": external_hours_totals,
            "external_hours_by_agreement": external_hours_by_agreement,
            "selected_month": view.selected_month_key,
            "readable_month": view.display_label,
            "period_kind": "quarter" if view.is_quarter else "month",
            "quarter": view.quarter,
            "odoo_unavailable": False,
        }
        return jsonify(response_payload)
    except OdooUnavailableError as exc:
        current_app.logger.warning("Odoo unavailable while serving sales API", exc_info=True)
        error_message = str(exc) if str(exc) else "Unable to connect to Odoo. Please try again later."
        err_view = _resolve_view_period()
        response_payload = {
            "sales_stats": {
                "invoice_count": 0,
                "comparison": None,
            },
            "invoiced_series": [],
            "invoiced_series_breakdown": [],
            "sales_orders_series": [],
            "sales_orders_series_breakdown": [],
            "agreement_type_totals": {
                "Retainer": 0.0,
                "Framework": 0.0,
                "Ad Hoc": 0.0,
                "Unknown": 0.0,
            },
            "sales_orders_agreement_type_totals": {
                "Retainer": 0.0,
                "Framework": 0.0,
                "Ad Hoc": 0.0,
                "Unknown": 0.0,
            },
            "sales_orders_project_totals": [],
            "subscriptions": [],
            "subscription_stats": {
                "active_count": 0,
                "churned_count": 0,
                "new_renew_count": 0,
                "mrr": 0.0,
                "mrr_display": "AED 0.00",
                "active_order_names": [],
                "total_subscriptions": 0,
                "subscription_comparison": None,
            },
            "external_hours_totals": {
                "external_hours_sold": 0.0,
                "external_hours_used": 0.0,
                "comparison_sold": None,
                "comparison_used": None,
            },
            "external_hours_by_agreement": {
                "sold": {
                    "Retainer": 0.0,
                    "Framework": 0.0,
                    "Ad Hoc": 0.0,
                    "Unknown": 0.0,
                },
                "used": {
                    "Retainer": 0.0,
                    "Framework": 0.0,
                    "Ad Hoc": 0.0,
                    "Unknown": 0.0,
                },
            },
            "selected_month": err_view.selected_month_key,
            "readable_month": err_view.display_label,
            "period_kind": "quarter" if err_view.is_quarter else "month",
            "quarter": err_view.quarter,
            "error": "odoo_unavailable",
            "message": error_message,
            "odoo_unavailable": True,
        }
        return jsonify(response_payload), 503


@creatives_bp.route("/api/utilization/refresh-monthly", methods=["POST"])
def refresh_monthly_utilization_api():
    """Refresh all monthly utilization data from Odoo and update Supabase cache."""
    try:
        selected_month = _resolve_month()
        utilization_service = _get_utilization_service()
        utilization_cache_service = None
        
        try:
            from ..services.utilization_cache_service import UtilizationCacheService
            utilization_cache_service = UtilizationCacheService.from_env()
        except Exception as e:
            current_app.logger.debug(f"Utilization cache not available: {e}")
            return jsonify({
                "error": "Cache service not available",
                "message": "Supabase is not configured"
            }), 500
        
        if not utilization_cache_service:
            return jsonify({
                "error": "Cache service not available",
                "message": "Supabase is not configured"
            }), 500
        
        # Force refresh by recalculating from Odoo and updating cache
        monthly_series = utilization_service.calculate_monthly_utilization_series(
            selected_month,
            cache_service=utilization_cache_service,
            force_refresh=True
        )
        
        return jsonify({
            "success": True,
            "monthly_utilization_series": monthly_series,
            "message": f"Refreshed utilization data for {selected_month.strftime('%B %Y')}"
        })
        
    except OdooUnavailableError as exc:
        current_app.logger.warning("Odoo unavailable while refreshing utilization data", exc_info=True)
        error_message = str(exc) if str(exc) else "Unable to connect to Odoo. Please try again later."
        return jsonify({
            "error": "odoo_unavailable",
            "message": error_message
        }), 503
    except Exception as exc:
        current_app.logger.error("Error refreshing utilization data", exc_info=True)
        return jsonify({
            "error": "server_error",
            "message": str(exc)
        }), 500


@creatives_bp.route("/api/sales/refresh-invoiced", methods=["POST"])
@require_sales_auth
def refresh_invoiced_api():
    """Refresh all invoiced data from Odoo and update Supabase cache."""
    try:
        sales_service = _get_sales_service()
        cache_service = _get_sales_cache_service()
        
        if not cache_service:
            return jsonify({
                "error": "Cache service not available",
                "message": "Supabase is not configured"
            }), 500
        
        # Get current year and month
        from datetime import datetime
        now = datetime.now()
        current_year = now.year
        current_month = now.month
        previous_year = current_year - 1

        # Force refresh totals + breakdowns for current year and previous year (up to current_month for both)
        from calendar import monthrange
        from datetime import date

        def refresh_year(year_to_refresh: int):
            months_to_refresh = current_month  # align previous-year overlay to current month count
            for month in range(1, months_to_refresh + 1):
                _, last_day = monthrange(year_to_refresh, month)
                month_start = date(year_to_refresh, month, 1)
                month_end = date(year_to_refresh, month, last_day)

                # Totals with component breakdown (so amount_aed matches invoices - credit_notes + reversed)
                invoices_total = sales_service._get_invoices_total(month_start, month_end)
                credit_notes_total = sales_service._get_credit_notes_total(month_start, month_end)
                reversed_total = sales_service._get_reversed_total(month_start, month_end)
                amount = invoices_total - credit_notes_total + reversed_total
                cache_service.save_month_data(
                    year_to_refresh, month, amount,
                    invoices_total=invoices_total,
                    credit_notes_total=credit_notes_total,
                    reversed_total=reversed_total,
                )

                # Breakdown (net of credit notes and reversed)
                breakdown = sales_service._build_invoice_breakdown_with_sign(month_start, month_end, year_to_refresh, month)
                if breakdown:
                    cache_service.upsert_month_breakdown(breakdown)

        refresh_year(previous_year)
        refresh_year(current_year)

        # Get the refreshed series and breakdowns (including previous year overlay)
        invoiced_series, invoiced_breakdown = sales_service.get_monthly_invoiced_series_with_breakdown(
            current_year,
            current_month,
            cache_service=cache_service,
            include_previous_year=True,
        )
        
        return jsonify({
            "success": True,
            "invoiced_series": invoiced_series,
            "invoiced_series_breakdown": invoiced_breakdown,
            "message": f"Refreshed invoiced totals and breakdowns for {previous_year} and {current_year}"
        })
        
    except OdooUnavailableError as exc:
        current_app.logger.warning("Odoo unavailable while refreshing invoiced data", exc_info=True)
        error_message = str(exc) if str(exc) else "Unable to connect to Odoo. Please try again later."
        return jsonify({
            "error": "odoo_unavailable",
            "message": error_message
        }), 503
    except Exception as exc:
        current_app.logger.error("Error refreshing invoiced data", exc_info=True)
        return jsonify({
            "error": "server_error",
            "message": str(exc)
        }), 500


@creatives_bp.route("/api/email-settings", methods=["GET"])
def get_email_settings_api():
    """Get current email settings."""
    try:
        email_settings_service = EmailSettingsService.from_env()
        settings = email_settings_service.get_settings()
        
        if settings:
            # Convert date/time strings to proper format
            # Ensure boolean values are properly converted
            internal_external_imbalance_enabled = settings.get("internal_external_imbalance_enabled", False)
            if isinstance(internal_external_imbalance_enabled, str):
                internal_external_imbalance_enabled = internal_external_imbalance_enabled.lower() in ("true", "t", "1")
            else:
                internal_external_imbalance_enabled = bool(internal_external_imbalance_enabled)
            
            enabled = settings.get("enabled", False)
            if isinstance(enabled, str):
                enabled = enabled.lower() in ("true", "t", "1")
            else:
                enabled = bool(enabled)
            
            overbooking_enabled = settings.get("overbooking_enabled", False)
            if isinstance(overbooking_enabled, str):
                overbooking_enabled = overbooking_enabled.lower() in ("true", "t", "1")
            else:
                overbooking_enabled = bool(overbooking_enabled)
            
            underbooking_enabled = settings.get("underbooking_enabled", False)
            if isinstance(underbooking_enabled, str):
                underbooking_enabled = underbooking_enabled.lower() in ("true", "t", "1")
            else:
                underbooking_enabled = bool(underbooking_enabled)
            
            subscription_hours_alert_enabled = settings.get("subscription_hours_alert_enabled", False)
            if isinstance(subscription_hours_alert_enabled, str):
                subscription_hours_alert_enabled = subscription_hours_alert_enabled.lower() in ("true", "t", "1")
            else:
                subscription_hours_alert_enabled = bool(subscription_hours_alert_enabled)
            
            result = {
                "recipients": settings.get("recipients", []),
                "cc_recipients": settings.get("cc_recipients", []),
                "send_date": settings.get("send_date"),
                "send_time": settings.get("send_time"),
                "enabled": enabled,
                "internal_external_imbalance_enabled": internal_external_imbalance_enabled,
                "overbooking_enabled": overbooking_enabled,
                "underbooking_enabled": underbooking_enabled,
                "subscription_hours_alert_enabled": subscription_hours_alert_enabled,
            }
            return jsonify({"success": True, "settings": result})
        else:
            return jsonify({
                "success": True,
                "settings": {
                    "recipients": [],
                    "cc_recipients": [],
                    "send_date": None,
                "send_time": None,
                "enabled": False,
                "internal_external_imbalance_enabled": False,
                "overbooking_enabled": False,
                "underbooking_enabled": False,
                "subscription_hours_alert_enabled": False,
                }
            })
    except RuntimeError as e:
        current_app.logger.error(f"Email settings service not configured: {e}")
        return jsonify({
            "success": False,
            "error": "Email settings service not configured",
            "settings": {
                "recipients": [],
                "cc_recipients": [],
                "send_date": None,
                "send_time": None,
                "enabled": False,
                "internal_external_imbalance_enabled": False,
                "overbooking_enabled": False,
                "underbooking_enabled": False,
                "subscription_hours_alert_enabled": False,
            }
        }), 503
    except Exception as exc:
        current_app.logger.error("Error fetching email settings", exc_info=True)
        return jsonify({"success": False, "error": "Failed to fetch email settings"}), 500


@creatives_bp.route("/api/email-settings", methods=["POST"])
def save_email_settings_api():
    """Save email settings."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "No data provided"}), 400
        
        recipients = data.get("recipients", [])
        cc_recipients = data.get("cc_recipients", [])
        send_date_str = data.get("send_date")
        send_time_str = data.get("send_time")
        enabled = data.get("enabled", True)
        internal_external_imbalance_enabled = data.get("internal_external_imbalance_enabled", False)
        overbooking_enabled = data.get("overbooking_enabled", False)
        underbooking_enabled = data.get("underbooking_enabled", False)
        subscription_hours_alert_enabled = data.get("subscription_hours_alert_enabled", False)
        
        # Validate recipients
        if not recipients or len(recipients) == 0:
            return jsonify({"success": False, "error": "At least one recipient is required"}), 400
        
        # Validate email addresses
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        all_emails = recipients + cc_recipients
        for email in all_emails:
            if not re.match(email_pattern, email):
                return jsonify({"success": False, "error": f"Invalid email address: {email}"}), 400
        
        # Parse date and time
        send_date = None
        if send_date_str:
            try:
                send_date = datetime.strptime(send_date_str, "%Y-%m-%d").date()
            except ValueError:
                return jsonify({"success": False, "error": "Invalid date format. Use YYYY-MM-DD"}), 400
        
        send_time = None
        if send_time_str:
            try:
                send_time = datetime.strptime(send_time_str, "%H:%M").time()
            except ValueError:
                return jsonify({"success": False, "error": "Invalid time format. Use HH:MM"}), 400
        
        # Save settings
        email_settings_service = EmailSettingsService.from_env()
        success = email_settings_service.save_settings(
            recipients=recipients,
            cc_recipients=cc_recipients,
            send_date=send_date,
            send_time=send_time,
            enabled=enabled,
            internal_external_imbalance_enabled=internal_external_imbalance_enabled,
            overbooking_enabled=overbooking_enabled,
            underbooking_enabled=underbooking_enabled,
            subscription_hours_alert_enabled=subscription_hours_alert_enabled,
        )
        
        if success:
            return jsonify({"success": True, "message": "Email settings saved successfully"})
        else:
            return jsonify({"success": False, "error": "Failed to save email settings"}), 500
            
    except RuntimeError as e:
        current_app.logger.error(f"Email settings service not configured: {e}")
        return jsonify({
            "success": False,
            "error": "Email settings service not configured"
        }), 503
    except Exception as exc:
        current_app.logger.error("Error saving email settings", exc_info=True)
        return jsonify({"success": False, "error": "Failed to save email settings"}), 500


@creatives_bp.route("/api/creative-hour-adjustments", methods=["GET"])
def get_creative_hour_adjustments_api():
    """List per-employee monthly hour overrides (dashboard availability)."""
    try:
        svc = CreativeHourAdjustmentsService.from_env()
        rows = svc.list_all()
        return jsonify({"success": True, "adjustments": rows})
    except RuntimeError as e:
        current_app.logger.warning("Creative hour adjustments unavailable: %s", e)
        return jsonify({"success": False, "error": "Supabase not configured", "adjustments": []}), 503
    except Exception as exc:
        current_app.logger.error("Error loading creative hour adjustments", exc_info=True)
        return jsonify({"success": False, "error": "Failed to load adjustments", "adjustments": []}), 500


@creatives_bp.route("/api/creative-hour-adjustments", methods=["PUT", "POST"])
def save_creative_hour_adjustments_api():
    """Replace all creative hour overrides."""
    try:
        payload = request.get_json()
        if not payload:
            return jsonify({"success": False, "error": "No data provided"}), 400
        raw = payload.get("adjustments")
        if not isinstance(raw, list):
            return jsonify({"success": False, "error": "adjustments must be a list"}), 400
        parsed: List[Tuple[int, float]] = []
        seen_ids: Set[int] = set()
        for item in raw:
            if not isinstance(item, dict):
                continue
            eid = item.get("employee_id")
            hrs = item.get("monthly_hours")
            if not isinstance(eid, int):
                try:
                    eid = int(eid)
                except (TypeError, ValueError):
                    continue
            try:
                h = float(hrs)
            except (TypeError, ValueError):
                continue
            if h < 0 or h > 400:
                return jsonify({"success": False, "error": "monthly_hours must be between 0 and 400"}), 400
            if eid in seen_ids:
                continue
            seen_ids.add(eid)
            parsed.append((eid, h))

        # Empty list = explicit "clear all". Non-empty but nothing parsed = invalid payload; do not wipe DB.
        if len(raw) > 0 and len(parsed) == 0:
            return jsonify(
                {
                    "success": False,
                    "error": "No valid adjustment rows. Existing settings were not changed.",
                }
            ), 400

        svc = CreativeHourAdjustmentsService.from_env()
        allow_clear = len(raw) == 0
        if not svc.replace_all(parsed, allow_empty_replace=allow_clear):
            return jsonify({"success": False, "error": "Failed to save adjustments"}), 500
        return jsonify({"success": True, "message": "Hour adjustments saved."})
    except RuntimeError as e:
        current_app.logger.error("Creative hour adjustments save: %s", e)
        return jsonify({"success": False, "error": "Supabase not configured"}), 503
    except Exception as exc:
        current_app.logger.error("Error saving creative hour adjustments", exc_info=True)
        return jsonify({"success": False, "error": "Failed to save adjustments"}), 500


@creatives_bp.route("/api/email-settings/test", methods=["POST"])
def test_email_settings_api():
    """Send an alert report email (test mode)."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "No data provided"}), 400
        
        recipients = data.get("recipients", [])
        cc_recipients = data.get("cc_recipients", [])
        internal_external_imbalance_enabled = data.get("internal_external_imbalance_enabled", False)
        overbooking_enabled = data.get("overbooking_enabled", False)
        underbooking_enabled = data.get("underbooking_enabled", False)
        subscription_hours_alert_enabled = data.get("subscription_hours_alert_enabled", False)
        test_month_str = data.get("test_month")  # Format: YYYY-MM or None
        
        # Validate recipients
        if not recipients or len(recipients) == 0:
            return jsonify({"success": False, "error": "At least one recipient is required"}), 400
        
        # Validate email addresses
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        all_emails = recipients + cc_recipients
        for email in all_emails:
            if not re.match(email_pattern, email):
                return jsonify({"success": False, "error": f"Invalid email address: {email}"}), 400
        
        # Parse test month or use current month
        if test_month_str:
            try:
                # Parse YYYY-MM format
                year, month = map(int, test_month_str.split('-'))
                selected_month = date(year, month, 1)
            except (ValueError, TypeError):
                return jsonify({"success": False, "error": "Invalid month format. Use YYYY-MM"}), 400
        else:
            # Use current month if not specified
            selected_month = _resolve_month()
        
        month_start, month_end = _month_bounds(selected_month)
        
        # Get alert data if enabled
        internal_external_imbalance = None
        overbooking = None
        underbooking = None
        declining_utilization_trend = None
        subscription_hours_alert = None
        
        # Initialize alert service with required services
        sales_service = _get_sales_service()
        employee_service = _get_employee_service()
        availability_service = _get_availability_service()
        planning_service = _get_planning_service()
        timesheet_service = _get_timesheet_service()
        comparison_service = _get_comparison_service()
        
        alert_service = AlertService(
            sales_service,
            employee_service=employee_service,
            availability_service=availability_service,
            planning_service=planning_service,
            timesheet_service=timesheet_service,
            comparison_service=comparison_service,
        )
        
        # Always check for declining utilization trend (no toggle needed - always enabled)
        declining_utilization_trend = alert_service.detect_declining_utilization_trend(
            month_start, month_end
        )
        
        if internal_external_imbalance_enabled:
            internal_external_imbalance = alert_service.detect_internal_external_imbalance(
                month_start, month_end
            )
        
        if overbooking_enabled:
            overbooking = alert_service.detect_overbooking(
                month_start, month_end
            )
        
        if underbooking_enabled:
            underbooking = alert_service.detect_underbooking(
                month_start, month_end
            )
        
        if subscription_hours_alert_enabled:
            subscription_hours_alert = alert_service.detect_subscription_hours_alert(
                month_start, month_end
            )
        
        # Send alert report
        email_service = EmailService.from_env()
        success = email_service.send_alert_report(
            to_recipients=recipients,
            month_start=month_start,
            month_end=month_end,
            internal_external_imbalance=internal_external_imbalance,
            overbooking=overbooking,
            underbooking=underbooking,
            declining_utilization_trend=declining_utilization_trend,
            subscription_hours_alert=subscription_hours_alert,
            cc_recipients=cc_recipients if cc_recipients else None,
        )
        
        if success:
            return jsonify({"success": True, "message": "Alert report sent successfully"})
        else:
            return jsonify({"success": False, "error": "Failed to send alert report"}), 500
            
    except RuntimeError as e:
        current_app.logger.error(f"Email service not configured: {e}")
        return jsonify({
            "success": False,
            "error": "Email service not configured. Please check Azure credentials."
        }), 503
    except Exception as exc:
        current_app.logger.error("Error sending alert report", exc_info=True)
        return jsonify({
            "success": False,
            "error": f"Failed to send alert report: {str(exc)}"
        }), 500


@creatives_bp.route("/api/email-settings/send-monthly-alert", methods=["POST"])
def send_monthly_alert_api():
    """Send monthly alert report based on saved settings (for cron jobs).
    
    This endpoint reads settings from the database and sends all enabled alerts in one email.
    Railway's cron scheduler should call this endpoint monthly.
    """
    try:
        # Get settings from database
        email_settings_service = EmailSettingsService.from_env()
        settings = email_settings_service.get_settings()
        
        if not settings:
            current_app.logger.warning("No email settings found in database")
            return jsonify({
                "success": False,
                "error": "No email settings configured"
            }), 404
        
        # Check if alerts are enabled
        if not settings.get("enabled", False):
            current_app.logger.info("Email alerts are disabled in settings")
            return jsonify({
                "success": True,
                "message": "Email alerts are disabled"
            })
        
        recipients = settings.get("recipients", [])
        if not recipients or len(recipients) == 0:
            current_app.logger.warning("No recipients configured for email alerts")
            return jsonify({
                "success": False,
                "error": "No recipients configured"
            }), 400
        
        cc_recipients = settings.get("cc_recipients", [])
        
        # Get enabled alert types
        internal_external_imbalance_enabled = settings.get("internal_external_imbalance_enabled", False)
        overbooking_enabled = settings.get("overbooking_enabled", False)
        underbooking_enabled = settings.get("underbooking_enabled", False)
        subscription_hours_alert_enabled = settings.get("subscription_hours_alert_enabled", False)
        
        # Use previous month for the alert report (typical use case)
        from datetime import datetime, timedelta
        today = datetime.now().date()
        # Get first day of previous month
        if today.month == 1:
            selected_month = date(today.year - 1, 12, 1)
        else:
            selected_month = date(today.year, today.month - 1, 1)
        
        month_start, month_end = _month_bounds(selected_month)
        
        # Get alert data if enabled
        internal_external_imbalance = None
        overbooking = None
        underbooking = None
        declining_utilization_trend = None
        subscription_hours_alert = None
        
        # Initialize alert service with required services
        sales_service = _get_sales_service()
        employee_service = _get_employee_service()
        availability_service = _get_availability_service()
        planning_service = _get_planning_service()
        timesheet_service = _get_timesheet_service()
        comparison_service = _get_comparison_service()
        
        alert_service = AlertService(
            sales_service,
            employee_service=employee_service,
            availability_service=availability_service,
            planning_service=planning_service,
            timesheet_service=timesheet_service,
            comparison_service=comparison_service,
        )
        
        # Always check for declining utilization trend (no toggle needed - always enabled)
        declining_utilization_trend = alert_service.detect_declining_utilization_trend(
            month_start, month_end
        )
        
        if internal_external_imbalance_enabled:
            internal_external_imbalance = alert_service.detect_internal_external_imbalance(
                month_start, month_end
            )
        
        if overbooking_enabled:
            overbooking = alert_service.detect_overbooking(
                month_start, month_end
            )
        
        if underbooking_enabled:
            underbooking = alert_service.detect_underbooking(
                month_start, month_end
            )
        
        if subscription_hours_alert_enabled:
            subscription_hours_alert = alert_service.detect_subscription_hours_alert(
                month_start, month_end
            )
        
        # Only send email if at least one alert has data
        has_any_alerts = (
            declining_utilization_trend is not None or
            (internal_external_imbalance and internal_external_imbalance.get("count", 0) > 0) or
            (overbooking and overbooking.get("count", 0) > 0) or
            (underbooking and underbooking.get("count", 0) > 0) or
            (subscription_hours_alert and subscription_hours_alert.get("count", 0) > 0)
        )
        
        if not has_any_alerts:
            current_app.logger.info(f"No alerts detected for {selected_month.strftime('%B %Y')}")
            return jsonify({
                "success": True,
                "message": "No alerts detected for this month"
            })
        
        # Send alert report with ALL enabled alerts in ONE email
        email_service = EmailService.from_env()
        success = email_service.send_alert_report(
            to_recipients=recipients,
            month_start=month_start,
            month_end=month_end,
            internal_external_imbalance=internal_external_imbalance,
            overbooking=overbooking,
            underbooking=underbooking,
            declining_utilization_trend=declining_utilization_trend,
            subscription_hours_alert=subscription_hours_alert,
            cc_recipients=cc_recipients if cc_recipients else None,
        )
        
        if success:
            current_app.logger.info(f"Monthly alert report sent successfully for {selected_month.strftime('%B %Y')}")
            return jsonify({
                "success": True,
                "message": f"Alert report sent successfully for {selected_month.strftime('%B %Y')}"
            })
        else:
            return jsonify({"success": False, "error": "Failed to send alert report"}), 500
            
    except RuntimeError as e:
        current_app.logger.error(f"Email service not configured: {e}")
        return jsonify({
            "success": False,
            "error": "Email service not configured. Please check Azure credentials."
        }), 503
    except Exception as exc:
        current_app.logger.error("Error sending monthly alert report", exc_info=True)
        return jsonify({
            "success": False,
            "error": f"Failed to send alert report: {str(exc)}"
        }), 500


@creatives_bp.route("/api/sales/refresh-sales-orders", methods=["POST"])
@require_sales_auth
def refresh_sales_orders_api():
    """Refresh all Sales Orders data from Odoo and update Supabase cache."""
    try:
        sales_service = _get_sales_service()
        cache_service = _get_sales_cache_service()
        
        if not cache_service:
            return jsonify({
                "error": "Cache service not available",
                "message": "Supabase is not configured"
            }), 500
        
        # Get current year and month
        from datetime import datetime
        now = datetime.now()
        current_year = now.year
        current_month = now.month
        
        # Force refresh for all months by fetching from Odoo and updating cache (totals + breakdowns)
        from calendar import monthrange
        from datetime import date
        previous_year = current_year - 1

        def refresh_so_year(year_to_refresh: int):
            months = current_month
            for month in range(1, months + 1):
                _, last_day = monthrange(year_to_refresh, month)
                month_start = date(year_to_refresh, month, 1)
                month_end = date(year_to_refresh, month, last_day)

                amount = sales_service._get_monthly_sales_orders_total_from_odoo(month_start, month_end)
                cache_service.save_sales_order_month_data(year_to_refresh, month, amount)

                breakdown = sales_service._build_sales_orders_breakdown(month_start, month_end, year_to_refresh, month)
                if breakdown:
                    cache_service.upsert_sales_order_breakdown(breakdown)

        refresh_so_year(previous_year)
        refresh_so_year(current_year)
        
        # Get the refreshed series from cache
        sales_orders_series, sales_orders_series_breakdown = sales_service.get_monthly_sales_orders_series_with_breakdown(
            current_year,
            current_month,
            cache_service=cache_service,
            include_previous_year=True
        )
        
        return jsonify({
            "success": True,
            "sales_orders_series": sales_orders_series,
            "sales_orders_series_breakdown": sales_orders_series_breakdown,
            "message": f"Refreshed Sales Orders totals and breakdowns for {previous_year} and {current_year}"
        })
        
    except OdooUnavailableError as exc:
        current_app.logger.warning("Odoo unavailable while refreshing Sales Orders data", exc_info=True)
        error_message = str(exc) if str(exc) else "Unable to connect to Odoo. Please try again later."
        return jsonify({
            "error": "odoo_unavailable",
            "message": error_message
        }), 503
    except Exception as exc:
        current_app.logger.error("Error refreshing Sales Orders data", exc_info=True)
        return jsonify({
            "error": "server_error",
            "message": str(exc)
        }), 500


@creatives_bp.route("/api/creative-groups", methods=["GET"])
def get_creative_groups_api():
    """Get all saved creative groups."""
    try:
        cache_service = None
        try:
            cache_service = SupabaseCacheService.from_env()
        except RuntimeError as e:
            # Supabase not configured, log the actual error
            current_app.logger.warning(f"Supabase not configured: {e}")
            return jsonify({"groups": []})
        
        groups = cache_service.get_creative_groups()
        return jsonify({"groups": groups})
    except Exception as exc:
        current_app.logger.error("Error fetching creative groups", exc_info=True)
        return jsonify({"error": "Failed to fetch groups", "groups": []}), 500


@creatives_bp.route("/api/creative-groups", methods=["POST"])
def create_creative_group_api():
    """Create a new creative group."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        name = data.get("name", "").strip()
        creative_ids = data.get("creative_ids", [])
        
        if not name:
            return jsonify({"error": "Group name is required"}), 400
        
        if not isinstance(creative_ids, list) or len(creative_ids) == 0:
            return jsonify({"error": "At least one creative ID is required"}), 400
        
        # Validate creative IDs are integers
        try:
            creative_ids = [int(id) for id in creative_ids]
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid creative IDs"}), 400
        
        cache_service = None
        try:
            cache_service = SupabaseCacheService.from_env()
        except RuntimeError as e:
            error_msg = str(e)
            current_app.logger.error(f"Failed to initialize Supabase service: {error_msg}")
            return jsonify({"error": "Supabase not configured", "details": error_msg}), 503
        
        group = cache_service.save_creative_group(name, creative_ids)
        if group:
            return jsonify({"success": True, "group": group}), 201
        else:
            return jsonify({"error": "Failed to save group"}), 500
    except Exception as exc:
        current_app.logger.error("Error creating creative group", exc_info=True)
        return jsonify({"error": "Failed to create group"}), 500


@creatives_bp.route("/api/creative-groups/<int:group_id>", methods=["PUT"])
def update_creative_group_api(group_id: int):
    """Update an existing creative group."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        name = data.get("name", "").strip()
        creative_ids = data.get("creative_ids", [])
        
        if not name:
            return jsonify({"error": "Group name is required"}), 400
        
        if not isinstance(creative_ids, list) or len(creative_ids) == 0:
            return jsonify({"error": "At least one creative ID is required"}), 400
        
        # Validate creative IDs are integers
        try:
            creative_ids = [int(id) for id in creative_ids]
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid creative IDs"}), 400
        
        cache_service = None
        try:
            cache_service = SupabaseCacheService.from_env()
        except RuntimeError as e:
            error_msg = str(e)
            current_app.logger.error(f"Failed to initialize Supabase service: {error_msg}")
            return jsonify({"error": "Supabase not configured", "details": error_msg}), 503
        
        group = cache_service.save_creative_group(name, creative_ids, group_id)
        if group:
            return jsonify({"success": True, "group": group})
        else:
            return jsonify({"error": "Failed to update group"}), 500
    except Exception as exc:
        current_app.logger.error("Error updating creative group", exc_info=True)
        return jsonify({"error": "Failed to update group"}), 500


@creatives_bp.route("/api/creative-groups/<int:group_id>", methods=["DELETE"])
def delete_creative_group_api(group_id: int):
    """Delete a creative group."""
    try:
        cache_service = None
        try:
            cache_service = SupabaseCacheService.from_env()
        except RuntimeError as e:
            error_msg = str(e)
            current_app.logger.error(f"Failed to initialize Supabase service: {error_msg}")
            return jsonify({"error": "Supabase not configured", "details": error_msg}), 503
        
        success = cache_service.delete_creative_group(group_id)
        if success:
            return jsonify({"success": True})
        else:
            return jsonify({"error": "Failed to delete group"}), 500
    except Exception as exc:
        current_app.logger.error("Error deleting creative group", exc_info=True)
        return jsonify({"error": "Failed to delete group"}), 500


def _month_bounds(month_start: date) -> Tuple[date, date]:
    last_day = monthrange(month_start.year, month_start.month)[1]
    month_end = month_start.replace(day=last_day)
    return month_start, month_end


MIN_MONTH = date(2025, 1, 1)

POOL_DEFINITIONS = [
    {"slug": "ksa", "label": "KSA", "tag": "ksa"},
    {"slug": "uae", "label": "UAE", "tag": "uae"},
]


@dataclass(frozen=True)
class DashboardViewPeriod:
    """View window for the creatives dashboard (one calendar month or one fiscal quarter)."""

    period_start: date
    period_end: date
    previous_period_start: date
    previous_period_end: date
    is_quarter: bool
    quarter: Optional[int]
    market_anchor_month: date
    series_anchor_month: date
    display_label: str
    has_previous_period: bool
    selected_month_key: str


def _quarter_bounds(year: int, quarter: int) -> Tuple[date, date]:
    """Return inclusive start/end dates for a calendar quarter."""
    if quarter == 1:
        start = date(year, 1, 1)
        end = date(year, 3, 31)
    elif quarter == 2:
        start = date(year, 4, 1)
        end = date(year, 6, 30)
    elif quarter == 3:
        start = date(year, 7, 1)
        end = date(year, 9, 30)
    else:
        start = date(year, 10, 1)
        end = date(year, 12, 31)
    return start, end


def _previous_quarter_bounds(year: int, quarter: int) -> Tuple[date, date]:
    if quarter == 1:
        return _quarter_bounds(year - 1, 4)
    return _quarter_bounds(year, quarter - 1)


def _month_period_from_anchor(anchor: date) -> DashboardViewPeriod:
    anchor = max(anchor.replace(day=1), MIN_MONTH)
    period_start, period_end = _month_bounds(anchor)
    has_previous_period = anchor > MIN_MONTH
    if has_previous_period:
        prev_first = _add_months(anchor, -1)
        previous_period_start, previous_period_end = _month_bounds(prev_first)
    else:
        previous_period_start = previous_period_end = period_start
    return DashboardViewPeriod(
        period_start=period_start,
        period_end=period_end,
        previous_period_start=previous_period_start,
        previous_period_end=previous_period_end,
        is_quarter=False,
        quarter=None,
        market_anchor_month=anchor,
        series_anchor_month=anchor,
        display_label=anchor.strftime("%B %Y"),
        has_previous_period=has_previous_period,
        selected_month_key=anchor.strftime("%Y-%m"),
    )


def _resolve_view_period() -> DashboardViewPeriod:
    """Parse dashboard period from query string (month, quarter, legacy YYYY-MM)."""
    today = date.today()
    default_anchor = today.replace(day=1)
    if default_anchor < MIN_MONTH:
        default_anchor = MIN_MONTH

    month_str = (request.args.get("month") or "").strip()
    year_str = (request.args.get("year") or "").strip()

    # Quarter: year + Q1..Q4
    if year_str and month_str and month_str.upper().startswith("Q") and len(month_str) <= 2:
        mu = month_str.upper()
        if len(mu) == 2 and mu[1] in "1234":
            try:
                year = int(year_str)
                q = int(mu[1])
                period_start, period_end = _quarter_bounds(year, q)
                prev_start, prev_end = _previous_quarter_bounds(year, q)
                has_previous_period = prev_start >= MIN_MONTH
                anchor = date(period_end.year, period_end.month, 1)
                return DashboardViewPeriod(
                    period_start=period_start,
                    period_end=period_end,
                    previous_period_start=prev_start,
                    previous_period_end=prev_end,
                    is_quarter=True,
                    quarter=q,
                    market_anchor_month=anchor,
                    series_anchor_month=anchor,
                    display_label=f"Q{q} {year}",
                    has_previous_period=has_previous_period,
                    selected_month_key=f"{year}-Q{q}",
                )
            except (ValueError, OverflowError):
                pass

    # Split month + year (1–12)
    if year_str and month_str and "-" not in month_str:
        try:
            year = int(year_str)
            month_num = int(month_str)
            if 1 <= month_num <= 12:
                anchor = date(year, month_num, 1)
                return _month_period_from_anchor(anchor)
        except (ValueError, OverflowError):
            pass

    # Legacy: month=YYYY-MM
    if month_str and "-" in month_str and "Q" not in month_str.upper():
        try:
            parsed = datetime.strptime(month_str, "%Y-%m")
            anchor = parsed.date().replace(day=1)
            return _month_period_from_anchor(max(anchor, MIN_MONTH))
        except ValueError:
            pass

    return _month_period_from_anchor(default_anchor)


def _resolve_month() -> date:
    """First day of the viewed calendar month (or first month of the viewed quarter)."""
    return _resolve_view_period().period_start


def _month_part_options() -> List[Dict[str, str]]:
    """Quarters plus January–December."""
    quarters = [{"value": f"Q{i}", "label": f"Q{i}"} for i in range(1, 5)]
    months = [{"value": f"{m:02d}", "label": month_name[m]} for m in range(1, 13)]
    return quarters + months


def _year_options(center_month: date) -> List[Dict[str, str]]:
    """Years from data start through a sensible upper bound (includes selected year)."""
    min_y = MIN_MONTH.year
    today = date.today()
    max_y = max(today.year, center_month.year, min_y) + 1
    return [{"value": str(y), "label": str(y)} for y in range(min_y, max_y + 1)]


def _add_months(anchor: date, offset: int) -> date:
    year = anchor.year + (anchor.month - 1 + offset) // 12
    month = (anchor.month - 1 + offset) % 12 + 1
    return date(year, month, 1)


def _calendar_months_spanned(period_start: date, period_end: date) -> int:
    """Inclusive count of calendar months overlapping [period_start, period_end]."""
    if period_start > period_end:
        return 0
    return (period_end.year - period_start.year) * 12 + (period_end.month - period_start.month) + 1


def _employed_months_in_view(
    period_start: date,
    period_end: date,
    joining: Optional[date],
) -> int:
    """Months in the view on or after the creative's join month (joining date from Odoo)."""
    if joining is None:
        return _calendar_months_spanned(period_start, period_end)
    join_month_start = date(joining.year, joining.month, 1)
    if period_end < join_month_start:
        return 0
    window_start = max(period_start, join_month_start)
    return _calendar_months_spanned(window_start, period_end)


def _creatives_with_availability(
    view: DashboardViewPeriod,
    creatives: Optional[List[Dict[str, object]]] = None,
) -> List[Dict[str, object]]:
    """Enrich creatives with availability for the viewed period (month or quarter)."""
    if creatives is None:
        employee_service = _get_employee_service()
        creatives = employee_service.get_creatives()

    month_start = view.period_start
    month_end = view.period_end
    has_previous_period = view.has_previous_period
    previous_period_start = view.previous_period_start
    previous_period_end = view.previous_period_end
    market_anchor_month = view.market_anchor_month
    previous_market_anchor = date(
        previous_period_end.year, previous_period_end.month, 1
    )

    summaries: Dict[int, AvailabilitySummary] = {}
    planned_hours: Dict[int, float] = {}
    logged_hours: Dict[int, float] = {}
    previous_summaries: Dict[int, AvailabilitySummary] = {}
    previous_planned_hours: Dict[int, float] = {}
    previous_logged_hours: Dict[int, float] = {}

    app = current_app._get_current_object()
    settings = current_app.config["ODOO_SETTINGS"]

    def _get_availability_with_new_client(start: date, end: date):
        with app.app_context():
            new_client = OdooClient(settings)
            service = AvailabilityService(new_client)
            return service.calculate_monthly_availability(creatives, start, end)

    def _get_planned_with_new_client(start: date, end: date):
        with app.app_context():
            new_client = OdooClient(settings)
            service = PlanningService(new_client)
            return service.planned_hours_for_month(creatives, start, end)

    def _get_logged_with_new_client(start: date, end: date):
        with app.app_context():
            new_client = OdooClient(settings)
            service = TimesheetService(new_client)
            return service.logged_hours_for_month(creatives, start, end)

    futures: Dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=6 if has_previous_period else 3) as executor:
        futures["summaries"] = executor.submit(_get_availability_with_new_client, month_start, month_end)
        futures["planned"] = executor.submit(_get_planned_with_new_client, month_start, month_end)
        futures["logged"] = executor.submit(_get_logged_with_new_client, month_start, month_end)

        if has_previous_period:
            futures["previous_summaries"] = executor.submit(
                _get_availability_with_new_client, previous_period_start, previous_period_end
            )
            futures["previous_planned"] = executor.submit(
                _get_planned_with_new_client, previous_period_start, previous_period_end
            )
            futures["previous_logged"] = executor.submit(
                _get_logged_with_new_client, previous_period_start, previous_period_end
            )

        for key, future in futures.items():
            futures[key] = future.result()

    summaries = futures["summaries"]
    planned_hours = futures["planned"]
    logged_hours = futures["logged"]
    if has_previous_period:
        previous_summaries = futures.get("previous_summaries", {}) or {}
        previous_planned_hours = futures.get("previous_planned", {}) or {}
        previous_logged_hours = futures.get("previous_logged", {}) or {}

    hour_adjustments: Dict[int, float] = {}
    try:
        hour_adjustments = CreativeHourAdjustmentsService.from_env().get_adjustments_map()
    except Exception:
        hour_adjustments = {}

    use_bu_model_current = use_business_unit_model(market_anchor_month)

    enriched: List[Dict[str, object]] = []
    for creative in creatives:
        # Pre-cutover months continue to use the legacy market/pool model;
        # April 2026 onward switches to Business Unit / SBU / Pod.
        if use_bu_model_current:
            bu_assignment = resolve_business_unit_for_month(creative, market_anchor_month)
            has_bu_labels = bool(
                bu_assignment
                and (
                    bu_assignment.business_unit
                    or bu_assignment.sub_business_unit
                    or bu_assignment.pod
                )
            )
            if not has_bu_labels:
                continue
            market_slug = None
            market_display = None
            pool_name = None
            current_business_unit = bu_assignment.business_unit
            current_sub_business_unit = bu_assignment.sub_business_unit
            current_pod = bu_assignment.pod
        else:
            market_result = _get_creative_market_for_month(creative, market_anchor_month)
            if market_result is None:
                continue

            market_slug, pool_name = market_result
            if not market_slug:
                continue

            market_display = market_slug.upper() if market_slug in {"ksa", "uae"} else market_slug.capitalize()
            current_business_unit = None
            current_sub_business_unit = None
            current_pod = None

        creative_id = creative.get("id")
        summary: AvailabilitySummary | None = summaries.get(creative_id) if isinstance(creative_id, int) else None
        base_hours = round(summary.base_hours, 2) if summary else 0.0
        time_off_hours = round(summary.time_off_hours, 2) if summary else 0.0
        public_holiday_hours = round(summary.public_holiday_hours, 2) if summary else 0.0
        public_holiday_details = summary.public_holiday_details if summary else []
        available_hours = (
            round(summary.available_hours, 2)
            if summary
            else round(max(base_hours - public_holiday_hours - time_off_hours, 0.0), 2)
        )
        planned = round(planned_hours.get(creative_id, 0.0), 2) if isinstance(creative_id, int) else 0.0
        logged = round(logged_hours.get(creative_id, 0.0), 2) if isinstance(creative_id, int) else 0.0

        joining = parse_joining_date(creative.get("x_studio_joining_date"))
        in_ramp_current = (
            joining is not None
            and period_overlaps_new_joiner_ramp(joining, month_start, month_end)
        )

        adj = hour_adjustments.get(creative_id) if isinstance(creative_id, int) else None
        hours_adjusted = False
        if adj is not None:
            hours_adjusted = True
            months_on = _employed_months_in_view(month_start, month_end, joining)
            if months_on <= 0:
                available_hours = 0.0
                base_hours = 0.0
                time_off_hours = 0.0
                public_holiday_hours = 0.0
                public_holiday_details = []
            else:
                h = float(adj) * float(months_on)
                base_hours = h
                time_off_hours = 0.0
                public_holiday_hours = 0.0
                public_holiday_details = []
                available_hours = h
        elif in_ramp_current:
            available_hours = 0.0
            planned = 0.0
            logged = 0.0

        previous_market_slug = None
        previous_market_display = None
        previous_pool_name = None
        previous_business_unit = None
        previous_sub_business_unit = None
        previous_pod = None
        previous_available = None
        previous_planned = None
        previous_logged = None
        if has_previous_period:
            # Each period resolves against its own model: a previous-period anchor
            # before 2026-04-01 still uses legacy market/pool even when the current
            # period has switched to BU.
            if use_business_unit_model(previous_market_anchor):
                prev_bu = resolve_business_unit_for_month(creative, previous_market_anchor)
                if prev_bu and prev_bu.business_unit:
                    previous_business_unit = prev_bu.business_unit
                    previous_sub_business_unit = prev_bu.sub_business_unit
                    previous_pod = prev_bu.pod
            else:
                previous_result = _get_creative_market_for_month(creative, previous_market_anchor)
                if previous_result:
                    previous_market_slug, previous_pool_name = previous_result
                    if previous_market_slug:
                        previous_market_display = (
                            previous_market_slug.upper()
                            if previous_market_slug in {"ksa", "uae"}
                            else previous_market_slug.capitalize()
                        )
            prev_summary: AvailabilitySummary | None = (
                previous_summaries.get(creative_id) if isinstance(creative_id, int) else None
            )
            previous_available = round(prev_summary.available_hours, 2) if prev_summary else 0.0
            previous_planned = (
                round(previous_planned_hours.get(creative_id, 0.0), 2) if isinstance(creative_id, int) else 0.0
            )
            previous_logged = (
                round(previous_logged_hours.get(creative_id, 0.0), 2) if isinstance(creative_id, int) else 0.0
            )

        in_ramp_previous = (
            joining is not None
            and has_previous_period
            and period_overlaps_new_joiner_ramp(joining, previous_period_start, previous_period_end)
        )
        # Previous-period metrics stay Odoo-derived. Hour adjustments apply only to the current view
        # so comparison data is not rewritten when settings change.
        if in_ramp_previous:
            previous_available = 0.0
            previous_planned = 0.0
            previous_logged = 0.0

        planned_utilization = _calculate_utilization(planned, available_hours)
        logged_utilization = _calculate_utilization(logged, available_hours)
        utilization_status = _utilization_status(planned_utilization, logged_utilization)

        enriched.append(
            {
                **creative,
                "is_new_joiner_ramp": bool(in_ramp_current and not hours_adjusted),
                "hours_adjusted": hours_adjusted,
                "market_slug": market_slug,
                "market_display": market_display,
                "pool_name": pool_name,
                "pool_display": pool_name if pool_name else "No Pool",
                "base_hours": base_hours,
                "base_hours_display": _format_hours_minutes(base_hours),
                "time_off_hours": time_off_hours,
                "time_off_hours_display": _format_hours_minutes(time_off_hours),
                "public_holiday_hours": public_holiday_hours,
                "public_holiday_hours_display": _format_hours_minutes(public_holiday_hours),
                "public_holiday_details": public_holiday_details,
                "available_hours": available_hours,
                "available_hours_display": _format_hours_minutes(available_hours),
                "planned_hours": planned,
                "planned_hours_display": _format_hours_minutes(planned),
                "logged_hours": logged,
                "logged_hours_display": _format_hours_minutes(logged),
                "planned_utilization": planned_utilization,
                "planned_utilization_display": _format_percentage(planned_utilization),
                "logged_utilization": logged_utilization,
                "logged_utilization_display": _format_percentage(logged_utilization),
                "utilization_status": utilization_status,
                "previous_market_slug": previous_market_slug,
                "previous_market_display": previous_market_display,
                "previous_pool_name": previous_pool_name,
                "previous_available_hours": previous_available if has_previous_period else None,
                "previous_planned_hours": previous_planned if has_previous_period else None,
                "previous_logged_hours": previous_logged if has_previous_period else None,
                # Business Unit / SBU / Pod (post-2026-04-01 model). These are
                # populated when the period anchor is on/after the cutover; the
                # legacy market_* / pool_* fields stay None in that case.
                "business_unit": current_business_unit,
                "sub_business_unit": current_sub_business_unit,
                "pod": current_pod,
                "previous_business_unit": previous_business_unit,
                "previous_sub_business_unit": previous_sub_business_unit,
                "previous_pod": previous_pod,
            }
        )

    return enriched


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


def _format_aed_value(value: float) -> str:
    return f"{value:,.2f} AED"


def _normalize_client_key(
    project_id: Any,
    name: Any,
    market: Any,
) -> Tuple[Tuple[Any, ...], Optional[int], str, str]:
    client_name = str(name).strip() if isinstance(name, str) else ""
    market_name = str(market).strip() if isinstance(market, str) else ""
    if not client_name:
        client_name = "Unassigned Client"
    if not market_name:
        market_name = "Unassigned Market"
    if isinstance(project_id, int):
        key: Tuple[Any, ...] = ("id", project_id)
        normalized_id: Optional[int] = project_id
    else:
        key = ("name", market_name.lower(), client_name.lower())
        normalized_id = None
    return key, normalized_id, client_name, market_name


def _extract_sales_top_clients(markets: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    clients: List[Dict[str, Any]] = []
    for market in markets or []:
        market_name = market.get("market")
        projects = market.get("projects") or []
        for project in projects:
            project_name = project.get("project_name")
            revenue_value = float(project.get("total_aed", 0.0) or 0.0)
            request_count = len(project.get("sales_orders") or [])
            project_id = project.get("project_id")
            clients.append(
                {
                    "project_id": project_id if isinstance(project_id, int) else None,
                    "client_name": project_name,
                    "market": market_name,
                    "total_revenue_aed": revenue_value,
                    "request_count": request_count,
                }
            )
    return clients



def _infer_pool_from_sources(
    tags: Iterable[str] | None = None,
    *candidates: object,
) -> str | None:
    tokens: list[str] = []
    if tags:
        tokens.extend(str(tag).lower() for tag in tags if isinstance(tag, str))
    for candidate in candidates:
        if not candidate:
            continue
        if isinstance(candidate, (list, tuple)):
            tokens.extend(str(item).lower() for item in candidate if isinstance(item, str))
        else:
            tokens.append(str(candidate).lower())
    for definition in POOL_DEFINITIONS:
        token = definition["tag"].lower()
        if any(token in value for value in tokens):
            return definition["slug"]
    return None


def _format_hours_display(value: float) -> str:
    if not value or abs(value) < 1e-6:
        return "0h"
    rounded = round(value, 1)
    if abs(rounded - round(rounded)) < 0.1:
        return f"{int(round(rounded)):,}h"
    return f"{rounded:,.1f}h"


def _format_currency_display(value: float) -> str:
    return f"{value:,.2f} AED"


def _extract_agreement_tokens(raw: Any) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        stripped = raw.strip()
        if not stripped:
            return []
        tokens = [part.strip() for part in re.split(r"[,/&|]+", stripped) if part.strip()]
        return tokens or [stripped]
    if isinstance(raw, (list, tuple, set)):
        tokens: List[str] = []
        for item in raw:
            tokens.extend(_extract_agreement_tokens(item))
        return tokens
    return []


def _normalize_agreements(values: Iterable[str]) -> List[str]:
    seen: set[str] = set()
    normalized: List[str] = []
    for value in values:
        stripped = value.strip()
        if not stripped:
            continue
        key = stripped.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(stripped)
    return normalized


def _infer_account_type(tags: Iterable[Any] | None) -> str:
    if not tags:
        return "non-key"
    normalized_tags: List[str] = []
    for tag in tags:
        if isinstance(tag, str):
            normalized_tags.append(tag.strip().lower())
    for value in normalized_tags:
        if "non-key" in value or "non key" in value:
            return "non-key"
    for value in normalized_tags:
        if "key account" in value:
            return "key"
    return "non-key"


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
