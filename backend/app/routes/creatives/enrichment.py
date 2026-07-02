"""Creative enrichment with availability/planned/logged for the viewed period."""
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
from .deps import _get_employee_service
from .stats import (
    _calculate_utilization,
    _format_hours_minutes,
    _format_percentage,
    _utilization_status,
)
from .view_period import DashboardViewPeriod, _employed_months_in_view


def _creatives_with_availability(
    view: DashboardViewPeriod,
    creatives: Optional[List[Dict[str, object]]] = None,
    hour_adjustments: Optional[Dict[int, float]] = None,
) -> List[Dict[str, object]]:
    """Enrich creatives with availability for the viewed period (month or quarter).

    ``hour_adjustments`` may be passed pre-fetched so one request reads the
    Supabase overrides a single time; when None it is fetched here (previous
    behavior).
    """
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

    if hour_adjustments is None:
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
