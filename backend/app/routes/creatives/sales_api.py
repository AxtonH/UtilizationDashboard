"""Sales endpoints: /api/sales, refresh-invoiced, refresh-sales-orders."""
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
from .deps import _get_sales_cache_service, _get_sales_service, _new_sales_service
from .view_period import DashboardViewPeriod, _resolve_view_period


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

        # Manual Strategy& hours (Supabase) fetched up front so the external-hours
        # bundle below can run inside the worker pool without request context.
        strat_sold, strat_used, strat_prev_sold, strat_prev_used = _strategy_and_manual_hours_for_view(view)

        with ThreadPoolExecutor(max_workers=10) as executor:
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
                # External-hours inputs that depend on nothing else: fetch them
                # from request start instead of inside get_external_hours_totals,
                # which previously re-fetched the whole previous-period chain
                # sequentially after the pool.
                "ext_sales_orders": executor.submit(
                    svc_call, "_get_sales_order_details_for_external_hours", period_start, period_end
                ),
            }
            if previous_period:
                futures["prev_subscriptions"] = executor.submit(
                    svc_call, "get_subscriptions_for_month", previous_period[0], previous_period[1]
                )
                futures["prev_ext_sales_orders"] = executor.submit(
                    svc_call, "_get_sales_order_details_for_external_hours",
                    previous_period[0], previous_period[1],
                )

            def run_external_bundle():
                # Chained off earlier futures so it overlaps the other workers
                # instead of running sequentially after the pool. (All futures it
                # waits on are submitted before this bundle, so FIFO dispatch
                # guarantees they are running or done when we wait on them.)
                subs = futures["subscriptions"].result()
                ext_orders = futures["ext_sales_orders"].result()
                prev_subs = futures["prev_subscriptions"].result() if previous_period else None
                prev_ext_orders = futures["prev_ext_sales_orders"].result() if previous_period else None
                svc = _new_sales_service(odoo_settings)
                stats = svc.get_subscription_statistics(period_start, period_end, subscriptions=subs)
                totals = svc.get_external_hours_totals(
                    period_start,
                    period_end,
                    subscriptions=subs,
                    sales_orders=ext_orders,
                    previous_period=previous_period,
                    previous_subscriptions=prev_subs,
                    previous_sales_orders=prev_ext_orders,
                    manual_strategy_sold=strat_sold,
                    manual_strategy_used=strat_used,
                    previous_manual_strategy_sold=strat_prev_sold,
                    previous_manual_strategy_used=strat_prev_used,
                )
                by_agreement = svc.get_external_hours_by_agreement_type(
                    period_start,
                    period_end,
                    subscriptions=subs,
                    sales_orders=ext_orders,
                    manual_strategy_sold=strat_sold,
                    manual_strategy_used=strat_used,
                )
                return stats, totals, by_agreement

            futures["external_bundle"] = executor.submit(run_external_bundle)

            sales_stats = futures["sales_stats"].result()
            invoiced_series, invoiced_series_breakdown = futures["invoiced"].result()
            sales_orders_series, sales_orders_series_breakdown = futures["sales_orders_series"].result()
            agreement_totals = futures["agreement_totals"].result()
            sales_orders_agreement_totals = futures["sales_orders_agreement_totals"].result()
            sales_orders_project_totals = futures["sales_orders_project_totals"].result()
            subscriptions = futures["subscriptions"].result()
            subscription_stats, external_hours_totals, external_hours_by_agreement = (
                futures["external_bundle"].result()
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
                "strategy_and_external_hours_sold": 0.0,
                "strategy_and_external_hours_used": 0.0,
                "comparison_sold": None,
                "comparison_used": None,
            },
            "external_hours_by_agreement": {
                "sold": {
                    "Retainer": 0.0,
                    "Framework": 0.0,
                    "Ad Hoc": 0.0,
                    "Unknown": 0.0,
                    "Strategy&": 0.0,
                },
                "used": {
                    "Retainer": 0.0,
                    "Framework": 0.0,
                    "Ad Hoc": 0.0,
                    "Unknown": 0.0,
                    "Strategy&": 0.0,
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


def _strategy_and_manual_hours_for_view(view: DashboardViewPeriod) -> Tuple[float, float, float, float]:
    """Manual Strategy& sold/used from Supabase for current and comparison date ranges."""
    try:
        svc = StrategyAndExternalHoursService.from_env()
    except RuntimeError:
        return (0.0, 0.0, 0.0, 0.0)
    cur_sold, cur_used = svc.sum_for_date_range(view.period_start, view.period_end)
    if not view.has_previous_period:
        return (cur_sold, cur_used, 0.0, 0.0)
    prev_sold, prev_used = svc.sum_for_date_range(view.previous_period_start, view.previous_period_end)
    return (cur_sold, cur_used, prev_sold, prev_used)
