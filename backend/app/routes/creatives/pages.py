"""The dashboard page (/) and /api/creatives endpoints."""
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
from .blueprint import creatives_bp
from .deps import (
    _get_employee_service,
    _get_tasks_service,
    _get_utilization_service,
    _start_request_prefetch,
)
from .enrichment import _creatives_with_availability
from .filters import (
    _filter_creatives_by_bu_assignment,
    _filter_creatives_by_market_and_pool,
    _get_available_bu_assignment_options,
    _get_available_markets_and_pools,
    _parse_bu_assignment_filter_params,
    _parse_filter_params,
)
from .stats import (
    _base_dashboard_state,
    _creatives_aggregates,
    _creatives_stats,
    _empty_dashboard_context,
    _pool_stats,
)
from .view_period import _month_part_options, _resolve_view_period, _year_options


@creatives_bp.route("/")
def dashboard():
    view = _resolve_view_period()
    month_start, month_end = view.period_start, view.period_end
    has_previous_period = view.has_previous_period
    try:
        # Start the creatives-independent fetches immediately so they overlap
        # the employee fetch and availability enrichment below.
        adjustments_thread, external_thread, prefetch = _start_request_prefetch(
            month_start, month_end
        )

        # Get all creatives from Odoo FIRST (before any filtering) for total creatives count
        # Use get_all_creatives() to include inactive creatives in the total count
        employee_service = _get_employee_service()
        all_creatives_from_odoo = employee_service.get_all_creatives(include_inactive=True)

        # Supabase hour overrides, fetched once for the whole request; both the
        # availability enrichment and the utilization series consume this map.
        adjustments_thread.join()
        hour_adjustments = prefetch.get("adjustments", {})
        nj_included = prefetch.get("nj_included", set())

        # Now get creatives with availability (this filters to only those with market/pool)
        # Pass the same list to avoid double-fetching
        all_creatives = _creatives_with_availability(
            view,
            all_creatives_from_odoo,
            hour_adjustments=hour_adjustments,
            new_joiner_included_ids=nj_included,
        )

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
                from ...services.overtime_service import OvertimeService
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
                    from ...services.utilization_cache_service import UtilizationCacheService
                    utilization_cache_service = UtilizationCacheService.from_env()
                except Exception as e:
                    current_app.logger.debug(f"Utilization cache not available: {e}")
                
                return utilization_service.calculate_monthly_utilization_series(
                    view.series_anchor_month,
                    cache_service=utilization_cache_service,
                    hour_adjustments=hour_adjustments,
                )
        
        # Execute all computations in parallel with smart dependency handling
        # (client external hours already run on the prefetch thread).
        with ThreadPoolExecutor(max_workers=8) as executor:
            future_stats = executor.submit(_compute_stats_with_context)
            future_aggregates = executor.submit(_compute_aggregates_with_context)
            future_pool_stats = executor.submit(_compute_pool_stats_with_context)
            future_headcount = executor.submit(_compute_headcount_with_context)
            future_overtime_stats = executor.submit(_compute_overtime_stats_with_context)
            future_utilization_series = executor.submit(_compute_utilization_series_with_context)
            
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

        from ...services.overtime_service import attach_overtime_to_creatives
        attach_overtime_to_creatives(all_creatives, overtime_stats)

        external_thread.join()
        client_external_hours_all, client_subscription_hours_all = prefetch.get(
            "client_external", ([], [])
        )

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
            # Server-render the logout button's initial visibility so it does
            # not pop in when the client-side auth check resolves.
            "dashboard_authenticated": bool(session.get("dashboard_authenticated")),
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
        # Start the creatives-independent fetches immediately so they overlap
        # the employee fetch and availability enrichment below.
        adjustments_thread, external_thread, prefetch = _start_request_prefetch(
            month_start, month_end
        )

        # Get all creatives from Odoo FIRST (before any filtering) for total creatives count
        # Use get_all_creatives() to include inactive creatives in the total count
        employee_service = _get_employee_service()
        all_creatives_from_odoo = employee_service.get_all_creatives(include_inactive=True)

        # Supabase hour overrides, fetched once for the whole request.
        adjustments_thread.join()
        hour_adjustments = prefetch.get("adjustments", {})
        nj_included = prefetch.get("nj_included", set())

        # Now get creatives with availability (this filters to only those with market/pool)
        # Pass the same list to avoid double-fetching
        all_creatives = _creatives_with_availability(
            view,
            all_creatives_from_odoo,
            hour_adjustments=hour_adjustments,
            new_joiner_included_ids=nj_included,
        )

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
                from ...services.overtime_service import OvertimeService
                overtime_service = OvertimeService.from_settings(settings)
                # Return overtime for all creatives - filtering happens client-side
                return overtime_service.calculate_overtime_statistics(
                    month_start, 
                    month_end,
                    creatives=all_creatives,
                )

        # (client external hours already run on the prefetch thread)
        with ThreadPoolExecutor(max_workers=7) as executor:
            future_stats = executor.submit(_compute_stats_api)
            future_aggregates = executor.submit(_compute_aggregates_api)
            future_pool_stats = executor.submit(_compute_pool_stats_api)
            future_headcount = executor.submit(_compute_headcount_api)
            future_overtime = executor.submit(_compute_overtime_api)
            
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

        from ...services.overtime_service import attach_overtime_to_creatives
        attach_overtime_to_creatives(all_creatives, overtime_stats)

        external_thread.join()
        client_external_hours_all, client_subscription_hours_all = prefetch.get(
            "client_external", ([], [])
        )

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
