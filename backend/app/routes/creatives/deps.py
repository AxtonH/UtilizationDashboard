"""Per-request service accessors (g-cached), lifecycle hooks, request prefetch."""
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
        # The two fetches are independent Odoo call chains; run them side by
        # side. The subscription call gets its own service + client because an
        # XML-RPC connection must not be shared across threads.
        subscription_service = ExternalHoursService(
            OdooClient(current_app.config["ODOO_SETTINGS"]),
            cache_service=service._cache_service,
        )
        with ThreadPoolExecutor(max_workers=2) as executor:
            ext_future = executor.submit(service.external_hours_for_month, month_start, month_end)
            sub_future = executor.submit(
                subscription_service.subscription_hours_for_month, month_start, month_end
            )
            ext = ext_future.result()
            sub = sub_future.result()
        markets_ext = ext.get("markets") if isinstance(ext.get("markets"), list) else []
        markets_sub = sub.get("markets") if isinstance(sub.get("markets"), list) else []
        return markets_ext, markets_sub
    except Exception:
        current_app.logger.warning(
            "Could not load client external hours markets for period",
            exc_info=True,
        )
        return [], []


def _start_request_prefetch(
    month_start: date,
    month_end: date,
) -> Tuple[threading.Thread, threading.Thread, Dict[str, Any]]:
    """Kick off the two fetches that do not depend on creatives data.

    The Supabase hour overrides and the client external/subscription hours are
    independent of the employee list, so they start at request time and their
    latency overlaps the employee fetch + availability enrichment. Join a
    thread before reading its key from the returned dict.
    """
    app = current_app._get_current_object()
    results: Dict[str, Any] = {}

    def _prefetch_adjustments() -> None:
        try:
            results["adjustments"] = CreativeHourAdjustmentsService.from_env().get_adjustments_map()
        except Exception:
            results["adjustments"] = {}

    def _prefetch_client_external() -> None:
        # _client_external_hours_markets_for_period handles its own errors and
        # returns ([], []) on failure, so this thread cannot die uncaught.
        with app.app_context():
            results["client_external"] = _client_external_hours_markets_for_period(
                month_start, month_end
            )

    adjustments_thread = threading.Thread(target=_prefetch_adjustments, daemon=True)
    external_thread = threading.Thread(target=_prefetch_client_external, daemon=True)
    adjustments_thread.start()
    external_thread.start()
    return adjustments_thread, external_thread, results


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
        from ...services.tasks_service import TasksService
        g.tasks_service = TasksService.from_comparison_service(_get_comparison_service())
    return g.tasks_service


def _get_overtime_service() -> "OvertimeService":
    if "overtime_service" not in g:
        from ...services.overtime_service import OvertimeService
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
        from ...services.sales_service import SalesService
        g.sales_service = SalesService(_get_odoo_client())
    return g.sales_service


def _new_sales_service(settings: Optional[OdooSettings] = None) -> "SalesService":
    """Create a fresh SalesService with its own OdooClient (for safe parallel calls).
    
    Args:
        settings: Optional pre-fetched OdooSettings to avoid relying on flask context inside threads.
    """
    from ...services.sales_service import SalesService
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
        from ...config import Config

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
