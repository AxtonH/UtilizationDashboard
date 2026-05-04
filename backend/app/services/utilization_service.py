"""Utilization dashboard service for company-wide metrics."""
from __future__ import annotations

from calendar import monthrange
from datetime import date
from typing import Any, Dict, List, Mapping, Optional, Tuple

# Earliest month we store in Supabase for utilization (matches creatives.MIN_MONTH).
MONTHLY_UTILIZATION_CACHE_MIN = date(2025, 1, 1)


def _inclusive_month_tuple_sequence(month_lo: date, month_hi: date) -> List[Tuple[int, int]]:
    """Calendar months from month_lo through month_hi inclusive (both day=1; month_hi >= month_lo)."""
    out: List[Tuple[int, int]] = []
    y, m = month_lo.year, month_lo.month
    ey, em = month_hi.year, month_hi.month
    while (y, m) <= (ey, em):
        out.append((y, m))
        if m == 12:
            y += 1
            m = 1
        else:
            m += 1
    return out

from .assignment_service import resolve_business_unit_for_month, use_business_unit_model
from .availability_service import AvailabilityService
from .employee_service import EmployeeService
from .external_hours_service import ExternalHoursService
from .planning_service import PlanningService
from .timesheet_service import TimesheetService
from .new_joiner_period import parse_joining_date, period_overlaps_new_joiner_ramp


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
    """Months in the view on or after the creative's join month (matches creatives dashboard)."""
    if joining is None:
        return _calendar_months_spanned(period_start, period_end)
    join_month_start = date(joining.year, joining.month, 1)
    if period_end < join_month_start:
        return 0
    window_start = max(period_start, join_month_start)
    return _calendar_months_spanned(window_start, period_end)


def _apply_creatives_dashboard_hour_rules(
    raw_available: float,
    raw_logged: float,
    raw_planned: float,
    creative_id: int,
    joining: Optional[date],
    month_start: date,
    month_end: date,
    hour_adjustments: Mapping[int, float],
) -> Tuple[float, float, float]:
    """Match `_creatives_with_availability` ordering: contract override first, else joiner ramp."""
    adj = hour_adjustments.get(creative_id) if isinstance(creative_id, int) else None
    in_ramp = (
        joining is not None
        and period_overlaps_new_joiner_ramp(joining, month_start, month_end)
    )
    if adj is not None:
        months_on = _employed_months_in_view(month_start, month_end, joining)
        if months_on <= 0:
            available = 0.0
        else:
            available = float(adj) * float(months_on)
        return (available, float(raw_logged), float(raw_planned))
    if in_ramp:
        return (0.0, 0.0, 0.0)
    return (float(raw_available), float(raw_logged), float(raw_planned))


def _monthly_util_cache_payload_hours(
    raw_available: float,
    raw_logged: float,
    raw_planned: float,
    creative_id: int,
    joining: Optional[date],
    month_start: date,
    month_end: date,
    hour_adjustments: Mapping[int, float],
) -> Tuple[float, float, float]:
    """Rows stored without adjustments applied; joiners in ramp zeroed when no override."""
    adj = hour_adjustments.get(creative_id) if isinstance(creative_id, int) else None
    in_ramp = (
        joining is not None
        and period_overlaps_new_joiner_ramp(joining, month_start, month_end)
    )
    if adj is not None:
        return (float(raw_available), float(raw_logged), float(raw_planned))
    if in_ramp:
        return (0.0, 0.0, 0.0)
    return (float(raw_available), float(raw_logged), float(raw_planned))


def _apply_adjustments_to_cached_monthly_row(
    cached_available: float,
    cached_logged: float,
    cached_planned: float,
    creative_id: int,
    joining: Optional[date],
    month_start: date,
    month_end: date,
    hour_adjustments: Mapping[int, float],
) -> Tuple[float, float, float]:
    """Re-apply contract hours on read (cache stores pre-override availability)."""
    adj = hour_adjustments.get(creative_id) if isinstance(creative_id, int) else None
    if adj is None:
        return (
            float(cached_available),
            float(cached_logged),
            float(cached_planned),
        )
    months_on = _employed_months_in_view(month_start, month_end, joining)
    if months_on <= 0:
        available = 0.0
    else:
        available = float(adj) * float(months_on)
    return (available, float(cached_logged), float(cached_planned))


POOL_DEFINITIONS = [
    {"slug": "animator", "label": "Animator", "tag": "animator"},
    {"slug": "adeo", "label": "ADEO", "tag": "adeo"},
    {"slug": "growjo", "label": "GrowJo", "tag": "growjo"},
    {"slug": "ksa", "label": "KSA"},
    {"slug": "uae", "label": "UAE"},
]


class UtilizationService:
    """Aggregate company-wide utilization metrics."""

    def __init__(
        self,
        employee_service: EmployeeService,
        availability_service: AvailabilityService,
        planning_service: PlanningService,
        timesheet_service: TimesheetService,
        external_hours_service: ExternalHoursService,
    ):
        self.employee_service = employee_service
        self.availability_service = availability_service
        self.planning_service = planning_service
        self.timesheet_service = timesheet_service
        self.external_hours_service = external_hours_service

    def get_utilization_summary(
        self,
        month_start: date,
        month_end: date,
        *,
        pool_assignment_month: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Get company-wide utilization summary for the specified date range (month or quarter)."""
        creatives = self.employee_service.get_creatives()

        # Get availability data
        summaries = self.availability_service.calculate_monthly_availability(
            creatives, month_start, month_end
        )

        # Get planned and logged hours
        planned_hours = self.planning_service.planned_hours_for_month(
            creatives, month_start, month_end
        )
        logged_hours = self.timesheet_service.logged_hours_for_month(
            creatives, month_start, month_end
        )

        # Get external hours
        external_data = self.external_hours_service.external_hours_for_month(
            month_start, month_end
        )
        subscription_data = self.external_hours_service.subscription_hours_for_month(
            month_start, month_end
        )

        # Calculate totals (exclude new joiners in their first 3 calendar months)
        total_available_hours = 0.0
        total_planned_hours = 0.0
        total_logged_hours = 0.0
        available_creatives_count = 0
        for creative in creatives:
            creative_id = creative.get("id")
            if not isinstance(creative_id, int):
                continue
            joining = parse_joining_date(creative.get("x_studio_joining_date"))
            if joining and period_overlaps_new_joiner_ramp(joining, month_start, month_end):
                continue
            summary = summaries.get(creative_id)
            avail = float(summary.available_hours) if summary else 0.0
            total_available_hours += avail
            total_planned_hours += float(planned_hours.get(creative_id, 0.0) or 0.0)
            total_logged_hours += float(logged_hours.get(creative_id, 0.0) or 0.0)
            if avail > 0:
                available_creatives_count += 1

        # External hours breakdown
        total_external_hours = external_data.get("summary", {}).get("total_external_hours", 0.0)
        total_subscription_used_hours = subscription_data.get("summary", {}).get(
            "total_subscription_used_hours", 0.0
        )
        total_external_used_hours = total_external_hours + total_subscription_used_hours

        pool_month = pool_assignment_month or month_start
        # Calculate pool statistics
        pool_stats = self._calculate_pool_stats(
            creatives, summaries, planned_hours, logged_hours, pool_month, month_start, month_end
        )

        return {
            "available_creatives": available_creatives_count,
            "total_available_hours": round(total_available_hours, 2),
            "total_planned_hours": round(total_planned_hours, 2),
            "total_logged_hours": round(total_logged_hours, 2),
            "total_external_used_hours": round(total_external_used_hours, 2),
            "available_hours_display": self._format_hours(total_available_hours),
            "planned_hours_display": self._format_hours(total_planned_hours),
            "logged_hours_display": self._format_hours(total_logged_hours),
            "external_used_hours_display": self._format_hours(total_external_used_hours),
            "pool_stats": pool_stats,
        }

    def _calculate_pool_stats(
        self,
        creatives: List[Dict[str, Any]],
        summaries: Dict[int, Any],
        planned_hours: Dict[int, float],
        logged_hours: Dict[int, float],
        selected_month: date,
        period_start: date,
        period_end: date,
    ) -> List[Dict[str, Any]]:
        """Calculate utilization statistics for each pool based on market assignments for the selected month."""
        pool_totals: Dict[str, Dict[str, Any]] = {
            pool["slug"]: {
                "creative_ids": set(),
                "available_hours": 0.0,
                "planned_hours": 0.0,
                "logged_hours": 0.0,
            }
            for pool in POOL_DEFINITIONS
        }

        for creative in creatives:
            creative_id = creative.get("id")
            if not isinstance(creative_id, int):
                continue

            joining = parse_joining_date(creative.get("x_studio_joining_date"))
            if joining and period_overlaps_new_joiner_ramp(joining, period_start, period_end):
                continue

            # Use market-based logic for KSA, UAE
            primary_slug = self._resolve_primary_pool_slug(creative, selected_month)
            if not primary_slug:
                continue

            bucket = pool_totals.get(primary_slug)
            if bucket is None:
                continue

            if creative_id in bucket["creative_ids"]:
                continue

            bucket["creative_ids"].add(creative_id)

            summary = summaries.get(creative_id)
            if summary:
                bucket["available_hours"] += float(summary.available_hours)
            bucket["planned_hours"] += float(planned_hours.get(creative_id, 0.0) or 0.0)
            bucket["logged_hours"] += float(logged_hours.get(creative_id, 0.0) or 0.0)

        pool_stats: List[Dict[str, Any]] = []
        for pool in POOL_DEFINITIONS:
            slug = pool["slug"]
            bucket = pool_totals[slug]
            available_hours = round(bucket["available_hours"], 2)
            planned_hours_total = round(bucket["planned_hours"], 2)
            logged_hours_total = round(bucket["logged_hours"], 2)

            utilization_percent = 0.0
            if available_hours > 0:
                utilization_percent = round((logged_hours_total / available_hours) * 100, 1)

            pool_stats.append(
                {
                    "slug": slug,
                    "label": pool["label"],
                    "total_creatives": len(bucket["creative_ids"]),
                    "available_hours": available_hours,
                    "available_hours_display": self._format_hours(available_hours),
                    "planned_hours": planned_hours_total,
                    "planned_hours_display": self._format_hours(planned_hours_total),
                    "logged_hours": logged_hours_total,
                    "logged_hours_display": self._format_hours(logged_hours_total),
                    "utilization_percent": utilization_percent,
                }
            )

        return pool_stats

    def _get_creative_market_for_month(
        self,
        creative: Mapping[str, Any],
        target_month: date,
    ) -> Optional[Tuple[str, Optional[str]]]:
        """Determine which market and pool a creative was in for a given month.
        
        Returns (market_slug, pool_name) or None. Uses the pool from the matching
        period (current, previous_1, etc.) so historical months get correct pool.
        """
        if not creative:
            return None
        
        month_start = target_month.replace(day=1)
        _, last_day = monthrange(month_start.year, month_start.month)
        month_end = month_start.replace(day=last_day)
        
        # Check current market first
        current_market = creative.get("current_market")
        current_start = creative.get("current_market_start")
        current_end = creative.get("current_market_end")
        current_pool = creative.get("current_pool")
        
        if current_market:
            if current_start and not current_end:
                if target_month >= current_start.replace(day=1):
                    slug = self._normalize_market_name(current_market)
                    return (slug, current_pool) if slug else None
            elif current_start and current_end:
                if current_start <= month_end and current_end >= month_start:
                    slug = self._normalize_market_name(current_market)
                    return (slug, current_pool) if slug else None
        
        # Check previous market 1
        previous_market_1 = creative.get("previous_market_1")
        previous_start_1 = creative.get("previous_market_1_start")
        previous_end_1 = creative.get("previous_market_1_end")
        previous_pool_1 = creative.get("previous_pool_1")
        
        if previous_market_1:
            if previous_start_1 and not previous_end_1:
                if target_month >= previous_start_1.replace(day=1):
                    slug = self._normalize_market_name(previous_market_1)
                    return (slug, previous_pool_1) if slug else None
            elif previous_start_1 and previous_end_1:
                if previous_start_1 <= month_end and previous_end_1 >= month_start:
                    slug = self._normalize_market_name(previous_market_1)
                    return (slug, previous_pool_1) if slug else None
        
        # Check previous market 2
        previous_market_2 = creative.get("previous_market_2")
        previous_start_2 = creative.get("previous_market_2_start")
        previous_end_2 = creative.get("previous_market_2_end")
        previous_pool_2 = creative.get("previous_pool_2")
        
        if previous_market_2:
            if previous_start_2 and not previous_end_2:
                if target_month >= previous_start_2.replace(day=1):
                    slug = self._normalize_market_name(previous_market_2)
                    return (slug, previous_pool_2) if slug else None
            elif previous_start_2 and previous_end_2:
                if previous_start_2 <= month_end and previous_end_2 >= month_start:
                    slug = self._normalize_market_name(previous_market_2)
                    return (slug, previous_pool_2) if slug else None
        
        # Check previous market 3
        previous_market_3 = creative.get("previous_market_3")
        previous_start_3 = creative.get("previous_market_3_start")
        previous_end_3 = creative.get("previous_market_3_end")
        previous_pool_3 = creative.get("previous_pool_3")
        
        if previous_market_3:
            if previous_start_3 and not previous_end_3:
                if target_month >= previous_start_3.replace(day=1):
                    slug = self._normalize_market_name(previous_market_3)
                    return (slug, previous_pool_3) if slug else None
            elif previous_start_3 and previous_end_3:
                if previous_start_3 <= month_end and previous_end_3 >= month_start:
                    slug = self._normalize_market_name(previous_market_3)
                    return (slug, previous_pool_3) if slug else None
        
        return None

    def _normalize_market_name(self, market_name: Optional[str]) -> Optional[str]:
        """Normalize market name to match pool slugs."""
        if not market_name:
            return None
        
        normalized = str(market_name).strip().lower()
        
        market_mapping = {
            "ksa": "ksa",
            "uae": "uae",
            "shared": "shared",  # Add shared as a valid market,
        }
        
        if normalized in market_mapping:
            return market_mapping[normalized]
        
        for key, value in market_mapping.items():
            if key in normalized or normalized in key:
                return value
        
        # If no match found, return None (don't return unrecognized market names)
        return None

    def _resolve_primary_pool_slug(
        self, creative: Mapping[str, Any], selected_month: date
    ) -> Optional[str]:
        """Resolve the pool slug for a creative based on market or tags."""
        # Try market-based logic first (for KSA, UAE)
        result = self._get_creative_market_for_month(creative, selected_month)
        if result:
            market_slug, _ = result
            return market_slug
        
        # Fallback to tag-based logic for legacy pools
        tags = creative.get("tags")
        if not tags:
            return None
        
        normalized = [
            str(tag).strip().lower()
            for tag in tags
            if isinstance(tag, str) and tag.strip()
        ]
        if not normalized:
            return None
        
        for pool in POOL_DEFINITIONS:
            tag = pool.get("tag")
            if tag and self._match_pool(normalized, tag):
                return pool["slug"]
        
        return None

    def _match_pool(self, tags: List[str] | None, target: str) -> bool:
        """Check if creative tags match the target pool tag."""
        if not tags:
            return False
        normalized = [str(tag).lower() for tag in tags if isinstance(tag, str)]
        return any(target in tag for tag in normalized)

    def _format_hours(self, value: float) -> str:
        """Format hours as 'XXXh' or 'XXXh YYm'."""
        total_minutes = int(round(value * 60))
        hours, minutes = divmod(total_minutes, 60)
        if minutes == 0:
            return f"{hours}h"
        return f"{hours}h {minutes:02d}m"

    def calculate_monthly_utilization_series(
        self,
        current_month: date,
        cache_service: Optional[Any] = None,
        force_refresh: bool = False,
        cache_period_start: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        """Calculate monthly utilization data from January to current viewing month.

        Normal loads read/write cache only for the viewing calendar year (Jan through
        the selected month). When ``force_refresh`` is True (manual refresh or cron),
        Supabase is repopulated from ``cache_period_start`` (default
        ``MONTHLY_UTILIZATION_CACHE_MIN``) through ``current_month`` so historic rows
        return after a full cache wipe. The returned list is still only chart months:
        viewing year Jan through selected month.

        Args:
            current_month: Anchor month (first of month) for chart + refresh end.
            cache_service: Optional UtilizationCacheService for caching.
            force_refresh: If True, recompute and upsert cache for every month in the
                          configured cache window through ``current_month``.
            cache_period_start: First month to include when ``force_refresh`` is True.
                               Defaults to ``MONTHLY_UTILIZATION_CACHE_MIN``.

        Returns:
            List of monthly data points with per-creative breakdowns (viewing year only).
        """
        # Get ALL creatives (same as company-wide utilization calculation)
        creatives = self.employee_service.get_creatives()
        year_view = current_month.year
        month_view = current_month.month

        if force_refresh:
            lo = (cache_period_start or MONTHLY_UTILIZATION_CACHE_MIN).replace(day=1)
            if lo < MONTHLY_UTILIZATION_CACHE_MIN:
                lo = MONTHLY_UTILIZATION_CACHE_MIN
            months_pairs = _inclusive_month_tuple_sequence(lo, current_month)
        else:
            months_pairs = _inclusive_month_tuple_sequence(
                date(year_view, 1, 1), current_month
            )

        monthly_data = []
        creative_by_id = {c["id"]: c for c in creatives if isinstance(c.get("id"), int)}

        hour_adjustments: Dict[int, float] = {}
        try:
            from .creative_hour_adjustments_service import CreativeHourAdjustmentsService

            hour_adjustments = CreativeHourAdjustmentsService.from_env().get_adjustments_map()
        except Exception:
            pass

        for year_num, month_num in months_pairs:
            month_start = date(year_num, month_num, 1)
            _, last_day = monthrange(year_num, month_num)
            month_end = date(year_num, month_num, last_day)
            
            # Check cache for historical months (not current month) unless force_refresh
            is_current = year_num == year_view and month_num == month_view
            cached_data = []
            
            if cache_service and not is_current and not force_refresh:
                try:
                    cached_data = cache_service.get_month_data(year_num, month_num)
                except Exception as e:
                    print(f"Cache retrieval error for {year_num}-{month_num}: {e}")
                    cached_data = []
            
            use_bu_for_month = use_business_unit_model(month_start)
            cache_stale_for_bu = (
                use_bu_for_month
                and cached_data
                and isinstance(cached_data[0], dict)
                and "business_unit" not in cached_data[0]
            )

            # Use cached data only if it exists and we're not forcing refresh
            # Note: Cached data should include ALL creatives with available hours > 0.
            # BU months need business_unit/sub/pod columns; legacy-only cache rows must refresh.
            if cached_data and not force_refresh and not cache_stale_for_bu:
                # Apply Supabase hour overrides on read so monthly chart matches company-wide cards.
                creative_breakdown = []
                for item in cached_data:
                    cid = item.get("creative_id")
                    if not isinstance(cid, int):
                        continue
                    cr = creative_by_id.get(cid)
                    joining = (
                        parse_joining_date(cr.get("x_studio_joining_date"))
                        if cr is not None
                        else None
                    )
                    if (
                        joining
                        and period_overlaps_new_joiner_ramp(joining, month_start, month_end)
                        and cid not in hour_adjustments
                    ):
                        continue
                    available = float(item["available_hours"])
                    logged = float(item["logged_hours"])
                    planned = float(item.get("planned_hours") or 0.0)
                    available, logged, planned = _apply_adjustments_to_cached_monthly_row(
                        available,
                        logged,
                        planned,
                        cid,
                        joining,
                        month_start,
                        month_end,
                        hour_adjustments,
                    )
                    if available <= 0:
                        continue
                    utilization_percent = round((logged / available) * 100.0, 2)
                    creative_breakdown.append(
                        {
                            "id": cid,
                            "available_hours": available,
                            "logged_hours": logged,
                            "planned_hours": planned,
                            "utilization_percent": utilization_percent,
                            "market_slug": item.get("market_slug"),
                            "pool_name": item.get("pool_name"),
                            "business_unit": item.get("business_unit"),
                            "sub_business_unit": item.get("sub_business_unit"),
                            "pod": item.get("pod"),
                        }
                    )
            else:
                # Calculate from scratch
                summaries = self.availability_service.calculate_monthly_availability(
                    creatives, month_start, month_end
                )
                planned_hours = self.planning_service.planned_hours_for_month(
                    creatives, month_start, month_end
                )
                logged_hours = self.timesheet_service.logged_hours_for_month(
                    creatives, month_start, month_end
                )
                
                creative_breakdown = []
                cache_payload_rows: List[Dict[str, Any]] = []
                for creative in creatives:
                    creative_id = creative.get("id")
                    if not isinstance(creative_id, int):
                        continue

                    summary = summaries.get(creative_id)
                    raw_available = float(summary.available_hours) if summary else 0.0
                    raw_logged = float(logged_hours.get(creative_id, 0.0) or 0.0)
                    raw_planned = float(planned_hours.get(creative_id, 0.0) or 0.0)

                    joining = parse_joining_date(creative.get("x_studio_joining_date"))
                    available, logged, planned = _apply_creatives_dashboard_hour_rules(
                        raw_available,
                        raw_logged,
                        raw_planned,
                        creative_id,
                        joining,
                        month_start,
                        month_end,
                        hour_adjustments,
                    )

                    if available <= 0:
                        continue

                    market_slug = None
                    pool_name = None
                    business_unit = None
                    sub_business_unit = None
                    pod_name = None

                    if use_bu_for_month:
                        bu_assign = resolve_business_unit_for_month(creative, month_start)
                        if not bu_assign or not (
                            bu_assign.business_unit
                            or bu_assign.sub_business_unit
                            or bu_assign.pod
                        ):
                            continue
                        business_unit = bu_assign.business_unit
                        sub_business_unit = bu_assign.sub_business_unit
                        pod_name = bu_assign.pod
                    else:
                        # Derive market_slug and pool_name for this month (legacy model)
                        result = self._get_creative_market_for_month(creative, month_start)
                        if not result:
                            continue
                        market_slug, pool_name = result
                        if not market_slug:
                            continue

                        # Fallback to tags for legacy pools if pool_name not from market
                        if not pool_name:
                            tags = creative.get("tags", [])
                            if tags:
                                normalized_tags = [
                                    str(tag).strip().lower()
                                    for tag in tags
                                    if isinstance(tag, str)
                                ]
                                for pool_def in POOL_DEFINITIONS:
                                    pool_tag = pool_def.get("tag")
                                    if pool_tag and any(pool_tag in tag for tag in normalized_tags):
                                        pool_name = pool_def.get("label")
                                        break

                    utilization_percent = round((logged / available) * 100.0, 2)

                    c_avail, c_log, c_pl = _monthly_util_cache_payload_hours(
                        raw_available,
                        raw_logged,
                        raw_planned,
                        creative_id,
                        joining,
                        month_start,
                        month_end,
                        hour_adjustments,
                    )
                    cache_payload_rows.append(
                        {
                            "creative_id": creative_id,
                            "available_hours": round(c_avail, 2),
                            "logged_hours": round(c_log, 2),
                            "planned_hours": round(c_pl, 2),
                            "utilization_percent": None,
                            "market_slug": market_slug,
                            "pool_name": pool_name,
                            "business_unit": business_unit,
                            "sub_business_unit": sub_business_unit,
                            "pod": pod_name,
                        }
                    )

                    creative_breakdown.append(
                        {
                            "id": creative_id,
                            "available_hours": round(available, 2),
                            "logged_hours": round(logged, 2),
                            "planned_hours": round(planned, 2),
                            "utilization_percent": utilization_percent,
                            "market_slug": market_slug,
                            "pool_name": pool_name,
                            "business_unit": business_unit,
                            "sub_business_unit": sub_business_unit,
                            "pod": pod_name,
                        }
                    )
                
                # Cache (always save when force_refresh, or for historical months when not)
                if cache_service and cache_payload_rows and (force_refresh or not is_current):
                    try:
                        cache_service.save_month_data(year_num, month_num, cache_payload_rows)
                    except Exception as e:
                        print(f"Cache save error for {year_num}-{month_num}: {e}")
            
            # Chart series: viewing calendar year Jan through selected month only.
            if year_num == year_view and month_num <= month_view:
                monthly_data.append({
                    "month": month_num,
                    "label": month_start.strftime("%b"),
                    "creatives": creative_breakdown,
                })
        
        return monthly_data
