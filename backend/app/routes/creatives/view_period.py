"""Dashboard view-period resolution, date math, and shared constants."""
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
