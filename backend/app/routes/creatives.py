"""Routes for creatives dashboard."""
from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from calendar import monthrange
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from flask import Blueprint, current_app, g, jsonify, render_template, request

from ..integrations.odoo_client import OdooClient, OdooUnavailableError
from ..services.availability_service import AvailabilityService, AvailabilitySummary
from ..services.employee_service import EmployeeService
from ..services.external_hours_service import ExternalHoursService
from ..services.planning_service import PlanningService
from ..services.timesheet_service import TimesheetService
from ..services.utilization_service import UtilizationService
from ..services.supabase_cache_service import SupabaseCacheService
from ..services.comparison_service import ComparisonService

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

from flask import Blueprint, current_app, g, jsonify, render_template, request

from ..integrations.odoo_client import OdooClient, OdooUnavailableError
from ..services.availability_service import AvailabilityService, AvailabilitySummary
from ..services.employee_service import EmployeeService
from ..services.planning_service import PlanningService
from ..services.timesheet_service import TimesheetService
from ..services.external_hours_service import ExternalHoursService
from ..services.utilization_service import UtilizationService
from ..services.supabase_cache_service import SupabaseCacheService
from ..services.headcount_service import HeadcountService

creatives_bp = Blueprint("creatives", __name__)

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


@creatives_bp.route("/")
def dashboard():
    selected_month = _resolve_month()
    has_previous_month = selected_month > MIN_MONTH
    try:
        month_start, month_end = _month_bounds(selected_month)
        
        # Get all creatives from Odoo FIRST (before any filtering) for total creatives count
        # Use get_all_creatives() to include inactive creatives in the total count
        employee_service = _get_employee_service()
        all_creatives_from_odoo = employee_service.get_all_creatives(include_inactive=True)
        
        # Now get creatives with availability (this filters to only those with market/pool)
        # Pass the same list to avoid double-fetching
        all_creatives = _creatives_with_availability(month_start, month_end, all_creatives_from_odoo)
        
        # Parse filter parameters
        selected_markets, selected_pools = _parse_filter_params(request.args)
        
        # Filter creatives
        creatives = _filter_creatives_by_market_and_pool(
            all_creatives,
            selected_markets if selected_markets else None,
            selected_pools if selected_pools else None,
        )
        
        # Get available markets and pools for filter options
        available_markets, available_pools = _get_available_markets_and_pools(all_creatives)
        
        # Parallelize independent operations to reduce load time
        # Capture app context and settings before threading
        app = current_app._get_current_object()
        settings = current_app.config["ODOO_SETTINGS"]
        agreement_type = request.args.get("agreement_type")
        account_type = request.args.get("account_type")
        
        def _compute_stats_with_context():
            with app.app_context():
                return _creatives_stats(creatives, all_creatives_from_odoo, selected_month)
        
        def _compute_aggregates_with_context():
            with app.app_context():
                return _creatives_aggregates(
                    all_creatives,
                    selected_month,
                    include_comparison=True,
                    selected_markets=selected_markets if selected_markets else None,
                    selected_pools=selected_pools if selected_pools else None,
                )
        
        def _compute_pool_stats_with_context():
            with app.app_context():
                return _pool_stats(creatives, selected_month)
        
        def _compute_headcount_with_context():
            with app.app_context():
                headcount_service = HeadcountService(_get_employee_service())
                return headcount_service.calculate_headcount(
                    selected_month, 
                    all_creatives_from_odoo, 
                    all_creatives,
                    selected_markets=selected_markets if selected_markets else None,
                    selected_pools=selected_pools if selected_pools else None,
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
        
        def _build_client_payload_with_context():
            with app.app_context():
                return _build_client_dashboard_payload(
                    selected_month,
                    agreement_type,
                    account_type,
                    settings=settings,
                    app=app,
                )
        
        # Execute independent computations in parallel (except tasks which needs headcount)
        with ThreadPoolExecutor(max_workers=6) as executor:
            future_stats = executor.submit(_compute_stats_with_context)
            future_aggregates = executor.submit(_compute_aggregates_with_context)
            future_pool_stats = executor.submit(_compute_pool_stats_with_context)
            future_headcount = executor.submit(_compute_headcount_with_context)
            future_overtime_stats = executor.submit(_compute_overtime_stats_with_context)
            future_client_payload = executor.submit(_build_client_payload_with_context)
            
            # Wait for all results except tasks (which depends on headcount)
            stats = future_stats.result()
            aggregates = future_aggregates.result()
            pool_stats = future_pool_stats.result()
            headcount = future_headcount.result()
            overtime_stats = future_overtime_stats.result()
            client_payload, filter_options, agreement_filter, account_filter = future_client_payload.result()
        
        # Now calculate tasks with the correct headcount
        tasks_service = _get_tasks_service()
        tasks_stats = tasks_service.calculate_tasks_statistics(
            all_creatives,
            month_start,
            month_end,
            headcount.get("available", 0),
        )
        
        month_options = _month_options(selected_month)


        context = {
            "creatives": creatives,
            "month_options": month_options,
            "selected_month": selected_month.strftime("%Y-%m"),
            "readable_month": selected_month.strftime("%B %Y"),
            "stats": stats,
            "aggregates": aggregates,
            "pool_stats": pool_stats,
            "headcount": headcount,
            "tasks_stats": tasks_stats,
            "overtime_stats": overtime_stats,
            "client_filter_options": filter_options,
            "selected_agreement_type": agreement_filter or "",
            "selected_account_type": account_filter or "",
            "available_markets": available_markets,
            "available_pools": available_pools,
            "selected_markets": selected_markets,
            "selected_pools": selected_pools,
            "has_previous_month": has_previous_month,
            "odoo_unavailable": False,
            "odoo_error_message": None,
        }
        context.update(client_payload)
        return render_template("creatives/dashboard.html", **context)
    except OdooUnavailableError as exc:
        current_app.logger.warning("Odoo unavailable while rendering dashboard", exc_info=True)
        context = _empty_dashboard_context(
            selected_month,
            error_message=str(exc) if str(exc) else "Unable to connect to Odoo. Please try again shortly.",
        )
        context["available_markets"] = []
        context["available_pools"] = []
        context["selected_markets"] = []
        context["selected_pools"] = []
        return render_template("creatives/dashboard.html", **context), 503


@creatives_bp.route("/api/creatives")
def creatives_api():
    selected_month = _resolve_month()
    has_previous_month = selected_month > MIN_MONTH
    try:
        month_start, month_end = _month_bounds(selected_month)
        
        # Get all creatives from Odoo FIRST (before any filtering) for total creatives count
        # Use get_all_creatives() to include inactive creatives in the total count
        employee_service = _get_employee_service()
        all_creatives_from_odoo = employee_service.get_all_creatives(include_inactive=True)
        
        # Now get creatives with availability (this filters to only those with market/pool)
        # Pass the same list to avoid double-fetching
        all_creatives = _creatives_with_availability(month_start, month_end, all_creatives_from_odoo)
        
        # Parse filter parameters
        selected_markets, selected_pools = _parse_filter_params(request.args)
        
        # Filter creatives
        creatives = _filter_creatives_by_market_and_pool(
            all_creatives,
            selected_markets if selected_markets else None,
            selected_pools if selected_pools else None,
        )
        
        # Get available markets and pools for filter options
        available_markets, available_pools = _get_available_markets_and_pools(all_creatives)
        
        stats = _creatives_stats(creatives, all_creatives_from_odoo, selected_month)
        # Use all_creatives (unfiltered) for aggregates, applying filters if present
        aggregates = _creatives_aggregates(
            all_creatives,
            selected_month,
            include_comparison=True,
            selected_markets=selected_markets if selected_markets else None,
            selected_pools=selected_pools if selected_pools else None,
        )
        pool_stats = _pool_stats(creatives, selected_month)
        
        # Calculate headcount metrics
        # Use all_creatives (with availability data) for accurate available count
        headcount_service = _get_headcount_service()
        headcount = headcount_service.calculate_headcount(
            selected_month, 
            all_creatives_from_odoo, 
            all_creatives,
            selected_markets=selected_markets if selected_markets else None,
            selected_pools=selected_pools if selected_pools else None,
        )
        
        client_payload, filter_options, agreement_filter, account_filter = _build_client_dashboard_payload(
            selected_month,
            request.args.get("agreement_type"),
            request.args.get("account_type"),
        )
        
        # Calculate tasks statistics
        # IMPORTANT: Always use all_creatives (unfiltered) for tasks_stats so client-side filtering works correctly
        # Tasks are inferred from creatives, so we need all tasks to filter client-side based on filtered creatives
        tasks_service = _get_tasks_service()
        tasks_stats = tasks_service.calculate_tasks_statistics(
            all_creatives,  # Use all_creatives instead of filtered creatives
            month_start,
            month_end,
            headcount.get("available", 0),
        )
        
        # Calculate overtime statistics
        # Filter overtime to only include requests from creatives retrieved from Odoo
        overtime_service = _get_overtime_service()
        overtime_stats = overtime_service.calculate_overtime_statistics(
            month_start, 
            month_end,
            creatives=all_creatives,  # Use all_creatives to include all creatives, not just filtered ones
        )
        
        response_payload: Dict[str, Any] = {
            "creatives": creatives,
            "selected_month": selected_month.strftime("%Y-%m"),
            "readable_month": selected_month.strftime("%B %Y"),
            "stats": stats,
            "aggregates": aggregates,
            "pool_stats": pool_stats,
            "headcount": headcount,
            "tasks_stats": tasks_stats,
            "overtime_stats": overtime_stats,
            "client_filter_options": filter_options,
            "selected_filters": {
                "agreement_type": agreement_filter or "",
                "account_type": account_filter or "",
            },
            "available_markets": available_markets,
            "available_pools": available_pools,
            "selected_markets": selected_markets,
            "selected_pools": selected_pools,
            "has_previous_month": has_previous_month,
            "odoo_unavailable": False,
        }
        response_payload.update(client_payload)
        return jsonify(response_payload)
    except OdooUnavailableError as exc:
        current_app.logger.warning("Odoo unavailable while serving creatives API", exc_info=True)
        error_message = str(exc) if str(exc) else "Unable to connect to Odoo. Please try again later."
        fallback_state = _base_dashboard_state(selected_month)
        response_payload = {
            **fallback_state,
            "selected_month": selected_month.strftime("%Y-%m"),
            "readable_month": selected_month.strftime("%B %Y"),
            "client_filter_options": fallback_state.get("client_filter_options", {"agreement_types": [], "account_types": []}),
            "selected_filters": {"agreement_type": "", "account_type": ""},
            "available_markets": [],
            "available_pools": [],
            "selected_markets": [],
            "selected_pools": [],
            "has_previous_month": has_previous_month,
            "error": "odoo_unavailable",
            "message": error_message,
            "odoo_unavailable": True,
        }
        return jsonify(response_payload), 503


@creatives_bp.route("/api/client-dashboard")
def client_dashboard_api():
    selected_month = _resolve_month()
    try:
        client_payload, filter_options, agreement_filter, account_filter = _build_client_dashboard_payload(
            selected_month,
            request.args.get("agreement_type"),
            request.args.get("account_type"),
        )
        response_payload = {
            **client_payload,
            "client_filter_options": filter_options,
            "selected_filters": {
                "agreement_type": agreement_filter or "",
                "account_type": account_filter or "",
            },
            "selected_month": selected_month.strftime("%Y-%m"),
            "readable_month": selected_month.strftime("%B %Y"),
            "odoo_unavailable": False,
        }
        return jsonify(response_payload)
    except OdooUnavailableError as exc:
        current_app.logger.warning("Odoo unavailable while serving client dashboard API", exc_info=True)
        error_message = str(exc) if str(exc) else "Unable to connect to Odoo. Please try again later."
        fallback_payload, filter_options, _, _ = _empty_client_dashboard_payload(selected_month)
        response_payload = {
            **fallback_payload,
            "client_filter_options": filter_options,
            "selected_filters": {"agreement_type": "", "account_type": ""},
            "selected_month": selected_month.strftime("%Y-%m"),
            "readable_month": selected_month.strftime("%B %Y"),
            "error": "odoo_unavailable",
            "message": error_message,
            "odoo_unavailable": True,
        }
        return jsonify(response_payload), 503


@creatives_bp.route("/api/client-dashboard/refresh-hours-series", methods=["POST"])
def refresh_hours_series_api():
    """Refresh the external used hours series data from Odoo for all months.
    
    This endpoint forces a refresh of all cached months by fetching fresh data from Odoo.
    """
    selected_month = _resolve_month()
    try:
        external_hours_service = _get_external_hours_service()
        series_window = _series_window(selected_month)
        
        # Force refresh all months from Odoo
        subscription_used_hours_series = external_hours_service.external_used_hours_series(
            selected_month.year,
            upto_month=selected_month.month,
            max_months=series_window,
            force_refresh=True,
        )
        
        response_payload = {
            "client_subscription_used_hours_series": subscription_used_hours_series,
            "client_subscription_used_hours_year": selected_month.year,
            "client_subscription_used_hours_window": series_window,
            "selected_month": selected_month.strftime("%Y-%m"),
            "readable_month": selected_month.strftime("%B %Y"),
            "odoo_unavailable": False,
            "refreshed": True,
        }
        return jsonify(response_payload)
    except OdooUnavailableError as exc:
        current_app.logger.warning("Odoo unavailable while refreshing hours series", exc_info=True)
        error_message = str(exc) if str(exc) else "Unable to connect to Odoo. Please try again later."
        response_payload = {
            "error": "odoo_unavailable",
            "message": error_message,
            "odoo_unavailable": True,
            "selected_month": selected_month.strftime("%Y-%m"),
            "readable_month": selected_month.strftime("%B %Y"),
        }
        return jsonify(response_payload), 503
    except Exception as exc:
        current_app.logger.error("Error refreshing hours series", exc_info=True)
        error_message = str(exc) if str(exc) else "An error occurred while refreshing the data."
        response_payload = {
            "error": "refresh_failed",
            "message": error_message,
            "selected_month": selected_month.strftime("%Y-%m"),
            "readable_month": selected_month.strftime("%B %Y"),
        }
        return jsonify(response_payload), 500


@creatives_bp.route("/api/utilization")
def utilization_api():
    selected_month = _resolve_month()
    try:
        month_start, month_end = _month_bounds(selected_month)
        utilization_service = _get_utilization_service()
        summary = utilization_service.get_utilization_summary(month_start, month_end)
        summary["odoo_unavailable"] = False
        summary["selected_month"] = selected_month.strftime("%Y-%m")
        summary["readable_month"] = selected_month.strftime("%B %Y")
        return jsonify(summary)
    except OdooUnavailableError as exc:
        current_app.logger.warning("Odoo unavailable while serving utilization API", exc_info=True)
        error_message = str(exc) if str(exc) else "Unable to connect to Odoo. Please try again later."
        summary = _empty_utilization_summary()
        summary.update(
            {
                "selected_month": selected_month.strftime("%Y-%m"),
                "readable_month": selected_month.strftime("%B %Y"),
                "error": "odoo_unavailable",
                "message": error_message,
                "odoo_unavailable": True,
            }
        )
        return jsonify(summary), 503


@creatives_bp.route("/api/creative-groups", methods=["GET"])
def get_creative_groups_api():
    """Get all saved creative groups."""
    try:
        cache_service = None
        try:
            cache_service = SupabaseCacheService.from_env()
        except RuntimeError:
            # Supabase not configured, return empty list
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
        except RuntimeError:
            return jsonify({"error": "Supabase not configured"}), 503
        
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
        except RuntimeError:
            return jsonify({"error": "Supabase not configured"}), 503
        
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
        except RuntimeError:
            return jsonify({"error": "Supabase not configured"}), 503
        
        success = cache_service.delete_creative_group(group_id)
        if success:
            return jsonify({"success": True})
        else:
            return jsonify({"error": "Failed to delete group"}), 500
    except Exception as exc:
        current_app.logger.error("Error deleting creative group", exc_info=True)
        return jsonify({"error": "Failed to delete group"}), 500


def _resolve_month() -> date:
    month_str = request.args.get("month")
    today = date.today()
    default_month = today.replace(day=1)
    if default_month < MIN_MONTH:
        default_month = MIN_MONTH

    if not month_str:
        return default_month

    try:
        parsed = datetime.strptime(month_str, "%Y-%m")
        resolved = parsed.date().replace(day=1)
        return resolved if resolved >= MIN_MONTH else MIN_MONTH
    except ValueError:
        return default_month


def _month_bounds(month_start: date) -> Tuple[date, date]:
    last_day = monthrange(month_start.year, month_start.month)[1]
    month_end = month_start.replace(day=last_day)
    return month_start, month_end


MIN_MONTH = date(2025, 1, 1)

POOL_DEFINITIONS = [
    {"slug": "ksa", "label": "KSA", "tag": "ksa"},
    {"slug": "uae", "label": "UAE", "tag": "uae"},
]



def _month_options(center_month: date, window: int = 6) -> List[Dict[str, str]]:
    options: List[Dict[str, str]] = []
    start_month = MIN_MONTH
    end_month = _add_months(center_month, window)
    if end_month < start_month:
        end_month = start_month

    option_month = start_month
    while option_month <= end_month:
        options.append(
            {
                "value": option_month.strftime("%Y-%m"),
                "label": option_month.strftime("%B %Y"),
                "current": option_month == center_month,
            }
        )
        option_month = _add_months(option_month, 1)
    return options


def _add_months(anchor: date, offset: int) -> date:
    year = anchor.year + (anchor.month - 1 + offset) // 12
    month = (anchor.month - 1 + offset) % 12 + 1
    return date(year, month, 1)


def _creatives_with_availability(
    month_start: date,
    month_end: date,
    creatives: Optional[List[Dict[str, object]]] = None,
) -> List[Dict[str, object]]:
    """Enrich creatives with availability data, filtering to those with market/pool for the month."""
    # Use provided creatives list or fetch from Odoo
    if creatives is None:
        employee_service = _get_employee_service()
        creatives = employee_service.get_creatives()
    
    # Determine if we have a previous month to compare against
    has_previous_month = month_start > MIN_MONTH
    previous_month_start: Optional[date] = None
    previous_month_end: Optional[date] = None
    if has_previous_month:
        previous_month_start = _add_months(month_start, -1)
        previous_month_end = _month_bounds(previous_month_start)[1]
    
    summaries: Dict[int, AvailabilitySummary] = {}
    planned_hours: Dict[int, float] = {}
    logged_hours: Dict[int, float] = {}
    previous_summaries: Dict[int, AvailabilitySummary] = {}
    previous_planned_hours: Dict[int, float] = {}
    previous_logged_hours: Dict[int, float] = {}
    
    # Create separate OdooClient instances for parallel execution
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
    with ThreadPoolExecutor(max_workers=6 if has_previous_month else 3) as executor:
        futures["summaries"] = executor.submit(_get_availability_with_new_client, month_start, month_end)
        futures["planned"] = executor.submit(_get_planned_with_new_client, month_start, month_end)
        futures["logged"] = executor.submit(_get_logged_with_new_client, month_start, month_end)
        
        if has_previous_month and previous_month_start and previous_month_end:
            futures["previous_summaries"] = executor.submit(
                _get_availability_with_new_client, previous_month_start, previous_month_end
            )
            futures["previous_planned"] = executor.submit(
                _get_planned_with_new_client, previous_month_start, previous_month_end
            )
            futures["previous_logged"] = executor.submit(
                _get_logged_with_new_client, previous_month_start, previous_month_end
            )
        
        for key, future in futures.items():
            futures[key] = future.result()
    
    summaries = futures["summaries"]
    planned_hours = futures["planned"]
    logged_hours = futures["logged"]
    if has_previous_month:
        previous_summaries = futures.get("previous_summaries", {}) or {}
        previous_planned_hours = futures.get("previous_planned", {}) or {}
        previous_logged_hours = futures.get("previous_logged", {}) or {}

    selected_month = month_start  # Use month_start as the selected month for market determination

    enriched: List[Dict[str, object]] = []
    for creative in creatives:
        # Determine market and pool for this creative for the selected month
        market_result = _get_creative_market_for_month(creative, selected_month)
        if market_result is None:
            continue
        
        market_slug, pool_name = market_result
        if not market_slug:
            continue
        
        # Get market display name (capitalize slug)
        market_display = market_slug.upper() if market_slug in {"ksa", "uae"} else market_slug.capitalize()
        
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

        previous_market_slug = None
        previous_market_display = None
        previous_pool_name = None
        previous_available = None
        previous_planned = None
        previous_logged = None
        if has_previous_month and previous_month_start:
            previous_result = _get_creative_market_for_month(creative, previous_month_start)
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

        planned_utilization = _calculate_utilization(planned, available_hours)
        logged_utilization = _calculate_utilization(logged, available_hours)
        utilization_status = _utilization_status(planned_utilization, logged_utilization)

        enriched.append(
            {
                **creative,
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
                "previous_available_hours": previous_available if has_previous_month else None,
                "previous_planned_hours": previous_planned if has_previous_month else None,
                "previous_logged_hours": previous_logged if has_previous_month else None,
            }
        )

    return enriched


def _creatives_stats(
    creatives: List[Dict[str, object]],
    all_creatives_from_odoo: List[Dict[str, object]],
    selected_month: date
) -> Dict[str, int]:
    """Calculate creative statistics.

    Args:
        creatives: Filtered list of creatives (with market/pool for selected month)
        all_creatives_from_odoo: All creatives from Odoo (Department == creative)
        selected_month: The month being viewed

    Returns:
        Dictionary with total, available, and active counts
    """
    # Total Creatives: All creatives from Odoo with Department == creative
    # Ensure we're using the full unfiltered list
    total = len(all_creatives_from_odoo) if all_creatives_from_odoo else 0
    
    # Available Creatives: Creatives with market and pool for the selected month
    # Count from the full list, not the filtered list
    available = 0
    if all_creatives_from_odoo:
        for creative in all_creatives_from_odoo:
            market_result = _get_creative_market_for_month(creative, selected_month)
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
    selected_month: Optional[date] = None,
    include_comparison: bool = True,
    selected_markets: Optional[List[str]] = None,
    selected_pools: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Calculate aggregates for creatives with optional month-over-month comparison."""

    market_filter = {m.lower() for m in selected_markets or []} or None
    pool_filter = set(selected_pools or []) or None

    def _matches_filters(market_slug: Optional[str], pool_name: Optional[str]) -> bool:
        normalized_market = market_slug.lower() if isinstance(market_slug, str) else None
        if market_filter and (not normalized_market or normalized_market not in market_filter):
            return False
        if pool_filter:
            if not pool_name:
                return False
            if pool_name not in pool_filter:
                return False
        return True

    filtered_creatives = [c for c in creatives if _matches_filters(c.get("market_slug"), c.get("pool_name"))]

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
            if not _matches_filters(creative.get("previous_market_slug"), creative.get("previous_pool_name")):
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

    if include_comparison and selected_month:
        comparison: Optional[Dict[str, Any]] = None
        has_previous_month = selected_month > MIN_MONTH
        if has_previous_month:
            previous_totals = _aggregate_previous_totals()
            if previous_totals is not None:
                comparison = _calculate_comparison_from_totals(totals, previous_totals)
            else:
                try:
                    comparison_service = _get_comparison_service()
                    previous_aggregates = comparison_service.calculate_previous_month_aggregates(
                        selected_month, filtered_creatives
                    )
                    comparison = comparison_service.calculate_comparison(totals, previous_aggregates)
                except Exception as exc:
                    current_app.logger.warning(
                        f"Failed to calculate comparison via service: {exc}", exc_info=True
                    )
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
    - Returns (market_slug, pool_name) or None if no market matches
    
    Args:
        creative: Creative employee record with market fields
        target_month: The month to check (should be first day of month)
        
    Returns:
        Tuple of (market_slug, pool_name) or None if no market matches
    """
    if not creative:
        return None
    
    month_start = target_month
    _, last_day = monthrange(month_start.year, month_start.month)
    month_end = month_start.replace(day=last_day)
    
    # Check current market first
    current_market = creative.get("current_market")
    current_start = creative.get("current_market_start")
    current_end = creative.get("current_market_end")
    current_pool = creative.get("current_pool")
    
    if current_market:
        # If current market has no end date, they're still in it
        if current_start and not current_end:
            # Check if target month is on or after start date
            if target_month >= current_start.replace(day=1):
                market_slug = _normalize_market_name(current_market)
                if market_slug:
                    return (market_slug, current_pool)
        # If current market has both dates, check if target month falls within range
        elif current_start and current_end:
            # Check if target month overlaps with current market period
            if current_start <= month_end and current_end >= month_start:
                market_slug = _normalize_market_name(current_market)
                if market_slug:
                    return (market_slug, current_pool)
        # If current market has only start date (no end), they're still in it
        elif current_start and not current_end:
            if target_month >= current_start.replace(day=1):
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
            if target_month >= previous_start_1.replace(day=1):
                market_slug = _normalize_market_name(previous_market_1)
                if market_slug:
                    return (market_slug, previous_pool_1)
        # If previous market 1 has both dates, check if target month falls within range
        elif previous_start_1 and previous_end_1:
            # Check if target month overlaps with previous market 1 period
            if previous_start_1 <= month_end and previous_end_1 >= month_start:
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
            if target_month >= previous_start_2.replace(day=1):
                market_slug = _normalize_market_name(previous_market_2)
                if market_slug:
                    return (market_slug, previous_pool_2)
        # If previous market 2 has both dates, check if target month falls within range
        elif previous_start_2 and previous_end_2:
            # Check if target month overlaps with previous market 2 period
            if previous_start_2 <= month_end and previous_end_2 >= month_start:
                market_slug = _normalize_market_name(previous_market_2)
                if market_slug:
                    return (market_slug, previous_pool_2)
    
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
        "uae": "uae",
    }
    
    # Check for exact match first
    if normalized in market_mapping:
        return market_mapping[normalized]
    
    # Check for partial matches
    for key, value in market_mapping.items():
        if key in normalized or normalized in key:
            return value
    
    return normalized


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


def _annotate_client_markets(
    markets: Iterable[Mapping[str, Any]] | None,
    entry_key: str,
) -> List[Dict[str, Any]]:
    annotated: List[Dict[str, Any]] = []
    for market in markets or []:
        market_label = str(market.get("market") or "Unassigned Market").strip() or "Unassigned Market"
        entries: List[Dict[str, Any]] = []
        for entry in market.get(entry_key, []) or []:
            entry_copy: Dict[str, Any] = deepcopy(entry)
            agreements = _normalize_agreements(_extract_agreement_tokens(entry_copy.get("agreement_type")))
            if not agreements:
                agreements = ["Unknown"]
            entry_copy["_agreement_tokens"] = agreements
            entry_copy["_account_type"] = _infer_account_type(entry_copy.get("tags"))
            entries.append(entry_copy)
        annotated.append({"market": market_label, entry_key: entries})
    return annotated


def _collect_client_filter_options(
    sales_markets: Iterable[Mapping[str, Any]] | None,
    subscription_markets: Iterable[Mapping[str, Any]] | None,
) -> Dict[str, List[str]]:
    agreement_candidates: List[str] = []
    account_candidates: set[str] = set()

    for market in sales_markets or []:
        for project in market.get("projects", []) or []:
            agreement_candidates.extend(project.get("_agreement_tokens", []))
            account = project.get("_account_type")
            if isinstance(account, str) and account:
                account_candidates.add(account)

    for market in subscription_markets or []:
        for subscription in market.get("subscriptions", []) or []:
            agreement_candidates.extend(subscription.get("_agreement_tokens", []))
            account = subscription.get("_account_type")
            if isinstance(account, str) and account:
                account_candidates.add(account)

    agreements = sorted(_normalize_agreements(agreement_candidates), key=str.casefold)
    account_candidates.update({"key", "non-key"})
    account_order = {"key": 0, "non-key": 1}
    accounts = sorted(
        {value.strip().lower() for value in account_candidates if isinstance(value, str) and value.strip()},
        key=lambda value: (account_order.get(value, 99), value)
    )
    return {
        "agreement_types": agreements,
        "account_types": accounts,
    }


def _normalize_agreement_filter(
    raw_value: Optional[str],
    available: Iterable[str],
) -> Optional[str]:
    if not raw_value:
        return None
    candidate = raw_value.strip()
    if not candidate:
        return None
    lookup = {value.lower(): value for value in available}
    return lookup.get(candidate.lower())


def _normalize_account_filter(
    raw_value: Optional[str],
    available: Iterable[str],
) -> Optional[str]:
    if not raw_value:
        return None
    candidate = raw_value.strip().lower()
    if not candidate:
        return None
    mapping = {
        "key": "key",
        "key account": "key",
        "key-account": "key",
        "key_account": "key",
        "non-key": "non-key",
        "non key": "non-key",
        "nonkey": "non-key",
        "non-key account": "non-key",
        "non key account": "non-key",
        "non_key": "non-key",
    }
    canonical = mapping.get(candidate)
    if canonical is None:
        return None
    available_lookup = {value.lower(): value for value in available}
    return available_lookup.get(canonical, available_lookup.get(canonical.lower()))


def _extract_subscription_top_clients_from_markets(
    markets: Iterable[Mapping[str, Any]] | None,
) -> List[Dict[str, Any]]:
    aggregated: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
    for market in markets or []:
        market_name = market.get("market")
        for subscription in market.get("subscriptions", []) or []:
            key, normalized_id, client_name, normalized_market = _normalize_client_key(
                subscription.get("project_id"),
                subscription.get("project_name"),
                market_name,
            )
            bucket = aggregated.setdefault(
                key,
                {
                    "project_id": normalized_id,
                    "client_name": client_name,
                    "market": normalized_market,
                    "total_revenue_aed": 0.0,
                    "request_count": 0,
                },
            )
            revenue_delta = float(subscription.get("aed_total", 0.0) or 0.0)
            bucket["total_revenue_aed"] += revenue_delta
            parent_tasks = subscription.get("subscription_parent_tasks")
            requests = len(parent_tasks) if isinstance(parent_tasks, list) else 0
            if requests > bucket["request_count"]:
                bucket["request_count"] = requests

    top_clients: List[Dict[str, Any]] = []
    for record in aggregated.values():
        total_revenue = float(record.get("total_revenue_aed", 0.0) or 0.0)
        record["total_revenue_aed"] = total_revenue
        record["total_revenue_aed_display"] = _format_aed_value(total_revenue)
        top_clients.append(record)

    top_clients.sort(
        key=lambda item: (
            -item["total_revenue_aed"],
            item["client_name"].lower(),
        )
    )
    return top_clients


def _apply_client_filters(
    sales_markets: Iterable[Mapping[str, Any]] | None,
    subscription_markets: Iterable[Mapping[str, Any]] | None,
    agreement_filter: Optional[str],
    account_filter: Optional[str],
) -> Dict[str, Any]:
    def _matches(entry: Mapping[str, Any]) -> bool:
        agreements = entry.get("_agreement_tokens", []) or []
        if agreement_filter:
            agreement_values = {token.lower() for token in agreements if isinstance(token, str)}
            if agreement_filter.lower() not in agreement_values:
                return False
        account = entry.get("_account_type")
        if account_filter:
            if not isinstance(account, str):
                return False
            if account.lower() != account_filter.lower():
                return False
        return True

    filtered_sales: List[Dict[str, Any]] = []
    total_projects = 0
    total_external_hours = 0.0
    total_revenue = 0.0
    total_invoices = 0

    for market in sales_markets or []:
        matching_projects = [
            deepcopy(project)
            for project in market.get("projects", []) or []
            if _matches(project)
        ]
        if not matching_projects:
            continue
        market_hours = sum(float(project.get("total_external_hours", 0.0) or 0.0) for project in matching_projects)
        market_revenue = sum(float(project.get("total_aed", 0.0) or 0.0) for project in matching_projects)
        market_invoices = sum(len(project.get("sales_orders") or []) for project in matching_projects)
        market_label = market.get("market") or "Unassigned Market"
        filtered_sales.append(
            {
                "market": market_label,
                "projects": matching_projects,
                "total_external_hours": market_hours,
                "total_external_hours_display": _format_hours_display(market_hours),
                "total_aed": market_revenue,
                "total_aed_display": _format_currency_display(market_revenue),
                "total_invoices": market_invoices,
            }
        )
        total_projects += len(matching_projects)
        total_external_hours += market_hours
        total_revenue += market_revenue
        total_invoices += market_invoices

    sales_summary = {
        "total_projects": total_projects,
        "total_external_hours": total_external_hours,
        "total_external_hours_display": _format_hours_display(total_external_hours),
        "total_revenue_aed": total_revenue,
        "total_revenue_aed_display": _format_currency_display(total_revenue),
        "total_invoices": total_invoices,
    }

    filtered_subscriptions: List[Dict[str, Any]] = []
    total_monthly_hours = 0.0
    total_subscription_used_hours = 0.0
    total_subscription_revenue = 0.0
    subscription_total_count: int = 0
    total_parent_tasks = 0

    for market in subscription_markets or []:
        matching_subscriptions = [
            deepcopy(subscription)
            for subscription in market.get("subscriptions", []) or []
            if _matches(subscription)
        ]
        if not matching_subscriptions:
            continue
        market_label = market.get("market") or "Unassigned Market"
        # Deduplicate by order reference within a market to avoid duplicate cards
        order_map: Dict[str, Dict[str, Any]] = {}
        for subscription in matching_subscriptions:
            reference = str(subscription.get("order_reference") or "").strip()
            if not reference:
                reference = str(subscription.get("project_name") or "").strip()
            if not reference:
                continue
            order_map.setdefault(reference, subscription)

        deduped_subscriptions = list(order_map.values())
        market_monthly_hours = sum(
            float(subscription.get("monthly_billable_hours", 0.0) or 0.0)
            for subscription in deduped_subscriptions
        )
        market_revenue = sum(float(subscription.get("aed_total", 0.0) or 0.0) for subscription in deduped_subscriptions)
        market_used_hours = sum(
            float(subscription.get("subscription_used_hours", 0.0) or 0.0)
            for subscription in deduped_subscriptions
        )
        # Count parent tasks for this market
        market_parent_tasks = sum(
            len(subscription.get("subscription_parent_tasks", [])) if isinstance(subscription.get("subscription_parent_tasks"), list) else 0
            for subscription in deduped_subscriptions
        )
        filtered_subscriptions.append(
            {
                "market": market_label,
                "subscriptions": deduped_subscriptions,
                "total_monthly_hours": market_monthly_hours,
                "total_monthly_hours_display": _format_hours_display(market_monthly_hours),
                "total_aed": market_revenue,
                "total_aed_display": _format_currency_display(market_revenue),
                "total_subscription_used_hours": market_used_hours,
                "total_subscription_used_hours_display": _format_hours_display(market_used_hours),
            }
        )
        total_monthly_hours += market_monthly_hours
        total_subscription_revenue += market_revenue
        total_subscription_used_hours += market_used_hours
        total_parent_tasks += market_parent_tasks
        # Count one card per unique order reference
        subscription_total_count += len(deduped_subscriptions)

    subscription_summary = {
        "total_subscriptions": subscription_total_count,
        "total_monthly_hours": total_monthly_hours,
        "total_monthly_hours_display": _format_hours_display(total_monthly_hours),
        "total_revenue_aed": total_subscription_revenue,
        "total_revenue_aed_display": _format_currency_display(total_subscription_revenue),
        "total_subscription_used_hours": total_subscription_used_hours,
        "total_subscription_used_hours_display": _format_hours_display(total_subscription_used_hours),
        "total_parent_tasks": total_parent_tasks,
    }

    sales_top_clients = _extract_sales_top_clients(filtered_sales)
    subscription_top_clients = _extract_subscription_top_clients_from_markets(filtered_subscriptions)

    return {
        "sales_markets": filtered_sales,
        "sales_summary": sales_summary,
        "subscription_markets": filtered_subscriptions,
        "subscription_summary": subscription_summary,
        "sales_top_clients": sales_top_clients,
        "subscription_top_clients": subscription_top_clients,
    }


def _build_client_dashboard_payload(
    selected_month: date,
    agreement_value: Optional[str],
    account_value: Optional[str],
    settings: Optional[Any] = None,
    app: Optional[Any] = None,
) -> Tuple[Dict[str, Any], Dict[str, List[str]], Optional[str], Optional[str]]:
    month_start, month_end = _month_bounds(selected_month)
    # Get settings from current_app if not provided (for backward compatibility)
    if settings is None:
        settings = current_app.config["ODOO_SETTINGS"]
    
    # Get app object for threads (use provided app or get from current_app)
    if app is None:
        app = current_app._get_current_object()
    
    # Get cache service if available (do this before threading since it might need app context)
    cache_service = None
    try:
        cache_service = SupabaseCacheService.from_env()
    except Exception:
        pass  # Continue without cache if not available

    # Parallelize external hours calls with separate clients
    external_data = None
    subscription_data = None
    subscription_used_hours_series = None
    
    def _get_external_hours():
        with app.app_context():
            new_client = OdooClient(settings)
            service = ExternalHoursService(new_client, cache_service=cache_service)
            return service.external_hours_for_month(month_start, month_end)
    
    def _get_subscription_hours():
        with app.app_context():
            new_client = OdooClient(settings)
            service = ExternalHoursService(new_client, cache_service=cache_service)
            return service.subscription_hours_for_month(month_start, month_end)
    
    def _get_used_hours_series():
        with app.app_context():
            new_client = OdooClient(settings)
            service = ExternalHoursService(new_client, cache_service=cache_service)
            series_window = _series_window(selected_month)
            return service.external_used_hours_series(
                selected_month.year,
                upto_month=selected_month.month,
                max_months=series_window,
            )
    
    with ThreadPoolExecutor(max_workers=3) as executor:
        future_external = executor.submit(_get_external_hours)
        future_subscription = executor.submit(_get_subscription_hours)
        future_series = executor.submit(_get_used_hours_series)
        
        external_data = future_external.result()
        subscription_data = future_subscription.result()
        subscription_used_hours_series = future_series.result()

    sales_markets = _annotate_client_markets(external_data.get("markets", []), "projects")
    subscription_markets = _annotate_client_markets(subscription_data.get("markets", []), "subscriptions")

    filter_options = _collect_client_filter_options(sales_markets, subscription_markets)
    agreement_filter = _normalize_agreement_filter(agreement_value, filter_options["agreement_types"])
    account_filter = _normalize_account_filter(account_value, filter_options["account_types"])

    filtered = _apply_client_filters(sales_markets, subscription_markets, agreement_filter, account_filter)
    series_window = _series_window(selected_month)

    payload = {
        "client_external_hours": filtered["sales_markets"],
        "client_external_hours_all": sales_markets,
        "client_sales_summary": filtered["sales_summary"],
        "client_subscription_hours": filtered["subscription_markets"],
        "client_subscription_hours_all": subscription_markets,
        "client_subscription_summary": filtered["subscription_summary"],
        "client_subscription_top_clients": _merge_top_clients(
            filtered["subscription_top_clients"],
            filtered["sales_top_clients"],
        ),
        "client_subscription_used_hours_series": subscription_used_hours_series,
        "client_subscription_used_hours_year": selected_month.year,
        "client_subscription_used_hours_window": series_window,
        "client_pool_external_summary": _compute_pool_external_summary(
            filtered["sales_markets"],
            filtered["subscription_markets"],
        ),
    }

    return payload, filter_options, agreement_filter, account_filter


def _empty_client_dashboard_payload(
    selected_month: date,
) -> Tuple[Dict[str, Any], Dict[str, List[str]], Optional[str], Optional[str]]:
    """Return an empty client dashboard payload for error states."""
    zero_hours = _format_hours_display(0.0)
    zero_currency = _format_currency_display(0.0)
    payload = {
        "client_external_hours": [],
        "client_external_hours_all": [],
        "client_sales_summary": {
            "total_projects": 0,
            "total_external_hours": 0.0,
            "total_external_hours_display": zero_hours,
            "total_revenue_aed": 0.0,
            "total_revenue_aed_display": zero_currency,
            "total_invoices": 0,
        },
        "client_subscription_hours": [],
        "client_subscription_hours_all": [],
        "client_subscription_summary": {
            "total_subscriptions": 0,
            "total_monthly_hours": 0.0,
            "total_monthly_hours_display": zero_hours,
            "total_revenue_aed": 0.0,
            "total_revenue_aed_display": zero_currency,
            "total_subscription_used_hours": 0.0,
            "total_subscription_used_hours_display": zero_hours,
        },
        "client_subscription_top_clients": [],
        "client_subscription_used_hours_series": [],
        "client_subscription_used_hours_year": selected_month.year,
        "client_subscription_used_hours_window": max(1, min(12, selected_month.month)),
        "client_pool_external_summary": {
            "pools": [],
            "totals": {
                "projects": 0,
                "projects_display": "0",
                "used_hours": 0.0,
                "used_hours_display": zero_hours,
                "revenue": 0.0,
                "revenue_display": zero_currency,
            },
        },
    }
    filter_options = {"agreement_types": [], "account_types": []}
    return payload, filter_options, None, None


def _compute_pool_external_summary(
    sales_markets: Iterable[Mapping[str, Any]] | None,
    subscription_markets: Iterable[Mapping[str, Any]] | None,
) -> Dict[str, Any]:
    pool_lookup = {definition["slug"]: definition for definition in POOL_DEFINITIONS}
    pools: Dict[str, Dict[str, Any]] = {
        slug: {
            "slug": slug,
            "label": definition["label"],
            "projects": set(),
            "used_hours": 0.0,
            "sold_hours": 0.0,
            "revenue": 0.0,
            "order_keys": set(),
            "sold_order_keys": set(),
            "invoice_keys": set(),
        }
        for slug, definition in pool_lookup.items()
    }
    totals: Dict[str, Any] = {
        "projects": set(),
        "used_hours": 0.0,
        "sold_hours": 0.0,
        "revenue": 0.0,
        "order_keys": set(),
        "sold_order_keys": set(),
        "invoice_keys": set(),
    }

    for market in sales_markets or []:
        for project in market.get("projects", []) or []:
            slug = _infer_pool_from_sources(project.get("tags"), project.get("project_name"), market.get("market"))
            if not slug or slug not in pools:
                continue
            pool_state = pools[slug]

            project_id = project.get("project_id")
            if not isinstance(project_id, (int, str)):
                project_id = project.get("project_name") or project.get("name")
            identifier = f"sales::{project_id}" if project_id is not None else None
            if identifier is not None:
                pool_state["projects"].add(identifier)
                totals["projects"].add(identifier)

            external_hours = float(project.get("total_external_hours", 0.0) or 0.0)
            revenue_value = float(project.get("total_aed", 0.0) or 0.0)

            pool_state["used_hours"] += external_hours
            pool_state["sold_hours"] += external_hours
            pool_state["revenue"] += revenue_value

            totals["used_hours"] += external_hours
            totals["sold_hours"] += external_hours
            totals["revenue"] += revenue_value

    for market in subscription_markets or []:
        for subscription in market.get("subscriptions", []) or []:
            slug = _infer_pool_from_sources(subscription.get("tags"), subscription.get("project_name"), market.get("market"))
            if not slug or slug not in pools:
                continue
            pool_state = pools[slug]

            # Treat each subscription order as a distinct project for pool counts
            order_reference = subscription.get("order_reference") or subscription.get("project_name")
            identifier = f"subscription::{order_reference}" if order_reference else None
            if identifier is not None:
                pool_state["projects"].add(identifier)
                totals["projects"].add(identifier)

            order_reference = subscription.get("order_reference")
            order_key = (slug, order_reference or identifier)
            if order_key not in pool_state["order_keys"]:
                used_hours = float(subscription.get("subscription_used_hours", 0.0) or 0.0)
                pool_state["used_hours"] += used_hours
                totals["used_hours"] += used_hours
                pool_state["order_keys"].add(order_key)
                totals["order_keys"].add(order_key)

            sold_key = (slug, order_reference or identifier)
            if sold_key not in pool_state["sold_order_keys"]:
                monthly_hours = float(subscription.get("monthly_billable_hours", 0.0) or 0.0)
                pool_state["sold_hours"] += monthly_hours
                totals["sold_hours"] += monthly_hours
                pool_state["sold_order_keys"].add(sold_key)
                totals["sold_order_keys"].add(sold_key)

            invoice_reference = subscription.get("invoice_reference")
            invoice_key = (slug, order_reference, invoice_reference)
            if invoice_key not in pool_state["invoice_keys"]:
                revenue_value = float(subscription.get("aed_total", 0.0) or 0.0)
                pool_state["revenue"] += revenue_value
                totals["revenue"] += revenue_value
                pool_state["invoice_keys"].add(invoice_key)
                totals["invoice_keys"].add(invoice_key)

    total_project_count = len(totals["projects"])
    total_used_hours = totals["used_hours"]
    total_revenue = totals["revenue"]

    pool_cards = []
    for slug, state in pools.items():
        project_count = len(state["projects"])
        used_hours = state["used_hours"]
        revenue_value = state["revenue"]

        pool_cards.append(
            {
                "slug": slug,
                "label": pool_lookup[slug]["label"],
                "metrics": {
                    "projects": {
                        "value": project_count,
                        "display": f"{project_count:,}",
                        "total_display": f"{total_project_count:,}",
                        "ratio": (project_count / total_project_count) if total_project_count else 0.0,
                    },
                    "used_hours": {
                        "value": used_hours,
                        "display": _format_hours_display(used_hours),
                        "total_display": _format_hours_display(total_used_hours),
                        "ratio": (used_hours / total_used_hours) if total_used_hours else 0.0,
                    },
                    "revenue": {
                        "value": revenue_value,
                        "display": _format_currency_display(revenue_value),
                        "total_display": _format_currency_display(total_revenue),
                        "ratio": (revenue_value / total_revenue) if total_revenue else 0.0,
                    },
                },
            }
        )

    return {
        "pools": pool_cards,
        "totals": {
            "projects": total_project_count,
            "projects_display": f"{total_project_count:,}",
            "used_hours": total_used_hours,
            "used_hours_display": _format_hours_display(total_used_hours),
            "revenue": total_revenue,
            "revenue_display": _format_currency_display(total_revenue),
        },
    }

def _merge_top_clients(
    subscription_clients: Iterable[Mapping[str, Any]] | None,
    sales_clients: Iterable[Mapping[str, Any]] | None,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    combined: Dict[Tuple[Any, ...], Dict[str, Any]] = {}

    def _ingest(entry: Mapping[str, Any]) -> None:
        key, normalized_id, client_name, market_name = _normalize_client_key(
            entry.get("project_id"),
            entry.get("client_name"),
            entry.get("market"),
        )
        record = combined.setdefault(
            key,
            {
                "project_id": normalized_id,
                "client_name": client_name,
                "market": market_name,
                "total_revenue_aed": 0.0,
                "request_count": 0,
            },
        )
        revenue_delta = entry.get("total_revenue_aed", 0.0)
        if isinstance(revenue_delta, (int, float)):
            record["total_revenue_aed"] += float(revenue_delta)
        request_delta = entry.get("request_count", 0)
        if isinstance(request_delta, (int, float)):
            record["request_count"] += int(request_delta)

    for entry in subscription_clients or []:
        _ingest(entry)
    for entry in sales_clients or []:
        _ingest(entry)

    top_clients: List[Dict[str, Any]] = []
    for record in combined.values():
        total_value = float(record.get("total_revenue_aed", 0.0) or 0.0)
        record["total_revenue_aed"] = total_value
        record["total_revenue_aed_display"] = _format_aed_value(total_value)
        top_clients.append(record)

    top_clients.sort(
        key=lambda item: (
            -item["total_revenue_aed"],
            item["client_name"].lower(),
        )
    )
    return top_clients[:limit]


def _base_dashboard_state(selected_month: date) -> Dict[str, Any]:
    """Provide a minimal dashboard state when downstream services are unavailable."""
    client_payload, filter_options, _, _ = _empty_client_dashboard_payload(selected_month)
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
        "client_filter_options": filter_options,
        "selected_agreement_type": "",
        "selected_account_type": "",
        "odoo_unavailable": True,
    }
    state.update(client_payload)
    return state


def _empty_dashboard_context(selected_month: date, error_message: str) -> Dict[str, Any]:
    """Compose the context for rendering the dashboard when Odoo is unreachable."""
    context = _base_dashboard_state(selected_month)
    context.update(
        {
            "month_options": _month_options(selected_month),
            "selected_month": selected_month.strftime("%Y-%m"),
            "readable_month": selected_month.strftime("%B %Y"),
            "has_previous_month": selected_month > MIN_MONTH,
            "odoo_error_message": error_message,
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
