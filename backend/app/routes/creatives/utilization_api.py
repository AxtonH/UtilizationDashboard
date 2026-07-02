"""Utilization endpoints: /api/utilization, refresh-monthly, warm-monthly-cache."""
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
from .deps import _get_utilization_service
from .stats import _empty_utilization_summary
from .view_period import MIN_MONTH, _resolve_month, _resolve_view_period


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


@creatives_bp.route("/api/utilization/refresh-monthly", methods=["POST"])
def refresh_monthly_utilization_api():
    """Refresh monthly utilization from Odoo and upsert Supabase cache.

    Recomputes every month from the dashboard minimum month (or optional ``since`` /
    ``cache_from`` query/body as ``YYYY-MM``) through the currently viewed month so a
    cleared cache regains full history, not only the viewing calendar year.
    """
    try:
        selected_month = _resolve_month()
        utilization_service = _get_utilization_service()
        utilization_cache_service = None
        
        try:
            from ...services.utilization_cache_service import UtilizationCacheService
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
        
        # Force refresh by recalculating from Odoo and updating cache (multi-year through anchor)
        monthly_series = utilization_service.calculate_monthly_utilization_series(
            selected_month,
            cache_service=utilization_cache_service,
            force_refresh=True,
            cache_period_start=_parse_optional_utilization_cache_since(),
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


def _parse_warm_monthly_cache_anchor() -> date:
    """First day of month to warm through (Jan..anchor), for scheduled cache jobs."""
    raw = request.args.get("anchor") or request.args.get("through")
    if not raw:
        payload = request.get_json(silent=True)
        if isinstance(payload, dict):
            raw = payload.get("anchor") or payload.get("through")
    if raw:
        try:
            text = str(raw).strip()[:10]
            parts = text.split("-")
            if len(parts) >= 2:
                y, m = int(parts[0]), int(parts[1])
                return date(y, m, 1)
        except (ValueError, TypeError):
            pass
    return date.today().replace(day=1)


def _parse_optional_utilization_cache_since() -> Optional[date]:
    """Optional lower bound (first month) for utilization cache refresh (query or JSON body)."""
    raw = request.args.get("since") or request.args.get("cache_from")
    if not raw:
        payload = request.get_json(silent=True)
        if isinstance(payload, dict):
            raw = payload.get("since") or payload.get("cache_from")
    if not raw:
        return None
    try:
        text = str(raw).strip()[:10]
        parts = text.split("-")
        if len(parts) >= 2:
            y, m = int(parts[0]), int(parts[1])
            return max(date(y, m, 1), MIN_MONTH)
    except (ValueError, TypeError):
        pass
    return None


@creatives_bp.route("/api/utilization/warm-monthly-cache", methods=["POST"])
def warm_monthly_utilization_cache_api():
    """Precompute monthly utilization cache from dashboard min month through anchor.

    Run off-peak via cron (Railway, GitHub Actions, etc.) so historic rows stay current
    without users clicking Refresh. Uses the same Odoo + Supabase path as
    ``/api/utilization/refresh-monthly`` with ``force_refresh=True``.

    Authentication: set env ``UTILIZATION_MONTHLY_CACHE_CRON_SECRET`` and send header
    ``X-Cron-Secret`` with that value. If the secret is unset, returns 503 so the route is opt-in.

    Query/body (optional): ``anchor`` or ``through`` as ``YYYY-MM`` or ``YYYY-MM-DD``
    (defaults to first day of current calendar month); ``since`` or ``cache_from`` as
    ``YYYY-MM`` for the earliest month to repopulate (defaults to dashboard minimum month).
    """
    configured = os.getenv("UTILIZATION_MONTHLY_CACHE_CRON_SECRET", "").strip()
    if not configured:
        return jsonify(
            {
                "error": "not_configured",
                "message": "Set UTILIZATION_MONTHLY_CACHE_CRON_SECRET to enable this endpoint.",
            }
        ), 503
    submitted = (request.headers.get("X-Cron-Secret") or "").strip()
    if submitted != configured:
        return jsonify({"error": "unauthorized"}), 401

    try:
        anchor = _parse_warm_monthly_cache_anchor()
        cache_since = _parse_optional_utilization_cache_since()
        utilization_service = _get_utilization_service()
        try:
            from ...services.utilization_cache_service import UtilizationCacheService

            utilization_cache_service = UtilizationCacheService.from_env()
        except Exception as e:
            current_app.logger.debug("Utilization cache not available: %s", e)
            return jsonify(
                {
                    "error": "cache_unavailable",
                    "message": "Supabase is not configured for utilization cache.",
                }
            ), 500

        monthly_series = utilization_service.calculate_monthly_utilization_series(
            anchor,
            cache_service=utilization_cache_service,
            force_refresh=True,
            cache_period_start=cache_since,
        )
        lo = (cache_since or MONTHLY_UTILIZATION_CACHE_MIN).replace(day=1)
        if lo < MONTHLY_UTILIZATION_CACHE_MIN:
            lo = MONTHLY_UTILIZATION_CACHE_MIN
        cache_months_processed = len(_inclusive_month_tuple_sequence(lo, anchor))
        payload: Dict[str, Any] = {
            "success": True,
            "anchor_month": anchor.isoformat(),
            "months_updated": len(monthly_series),
            "cache_months_processed": cache_months_processed,
            "message": f"Warmed monthly utilization cache through {anchor.strftime('%B %Y')}",
        }
        if request.args.get("verbose") == "1":
            payload["monthly_utilization_series"] = monthly_series
        return jsonify(payload)
    except OdooUnavailableError as exc:
        current_app.logger.warning(
            "Odoo unavailable while warming monthly utilization cache", exc_info=True
        )
        error_message = str(exc) if str(exc) else "Unable to connect to Odoo."
        return jsonify({"error": "odoo_unavailable", "message": error_message}), 503
    except Exception as exc:
        current_app.logger.error("Error warming monthly utilization cache", exc_info=True)
        return jsonify({"error": "server_error", "message": str(exc)}), 500
