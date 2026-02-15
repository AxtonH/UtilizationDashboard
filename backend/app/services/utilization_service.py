"""Utilization dashboard service for company-wide metrics."""
from __future__ import annotations

from calendar import monthrange
from datetime import date
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .availability_service import AvailabilityService
from .employee_service import EmployeeService
from .external_hours_service import ExternalHoursService
from .planning_service import PlanningService
from .timesheet_service import TimesheetService


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

    def get_utilization_summary(self, month_start: date, month_end: date) -> Dict[str, Any]:
        """Get company-wide utilization summary for the specified month."""
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

        # Calculate totals
        total_available_hours = sum(
            summary.available_hours for summary in summaries.values()
        )
        total_planned_hours = sum(planned_hours.values())
        total_logged_hours = sum(logged_hours.values())

        # External hours breakdown
        total_external_hours = external_data.get("summary", {}).get("total_external_hours", 0.0)
        total_subscription_used_hours = subscription_data.get("summary", {}).get(
            "total_subscription_used_hours", 0.0
        )
        total_external_used_hours = total_external_hours + total_subscription_used_hours

        # Available creatives count
        available_creatives_count = sum(
            1 for summary in summaries.values() if summary.available_hours > 0
        )

        # Calculate pool statistics
        pool_stats = self._calculate_pool_stats(
            creatives, summaries, planned_hours, logged_hours, month_start
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
    ) -> List[Dict[str, Any]]:
        """Calculate monthly utilization data from January to current viewing month.
        
        Args:
            current_month: The current month being viewed
            cache_service: Optional UtilizationCacheService for caching
            force_refresh: If True, force refresh from Odoo and update cache for
                          current year and previous year (e.g. 2024 and 2025)
            
        Returns:
            List of monthly data points with per-creative breakdowns
        """
        # Get ALL creatives (same as company-wide utilization calculation)
        creatives = self.employee_service.get_creatives()
        year = current_month.year
        current_month_num = current_month.month
        # When force_refresh, process current year + previous year, all 12 months each
        if force_refresh:
            years_to_refresh = [year - 1, year]
            months_to_process = range(1, 13)
        else:
            years_to_refresh = [year]
            months_to_process = range(1, current_month_num + 1)
        
        monthly_data = []
        
        for year_num in years_to_refresh:
            for month_num in months_to_process:
                month_start = date(year_num, month_num, 1)
                _, last_day = monthrange(year_num, month_num)
                month_end = date(year_num, month_num, last_day)
                
                # Check cache for historical months (not current month) unless force_refresh
                is_current = year_num == year and month_num == current_month_num
                cached_data = []
                
                if cache_service and not is_current and not force_refresh:
                    try:
                        cached_data = cache_service.get_month_data(year_num, month_num)
                    except Exception as e:
                        print(f"Cache retrieval error for {year_num}-{month_num}: {e}")
                        cached_data = []
                
                # Use cached data only if it exists and we're not forcing refresh
                # Note: Cached data should include ALL creatives with available hours > 0
                if cached_data and not force_refresh:
                    # Use cached data
                    creative_breakdown = [
                        {
                            "id": item["creative_id"],
                            "available_hours": float(item["available_hours"]),
                            "logged_hours": float(item["logged_hours"]),
                            "planned_hours": float(item.get("planned_hours") or 0.0),
                            "utilization_percent": float(item["utilization_percent"]) if item.get("utilization_percent") is not None else None,
                            "market_slug": item.get("market_slug"),
                            "pool_name": item.get("pool_name"),
                        }
                        for item in cached_data
                    ]
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
                    for creative in creatives:
                        creative_id = creative.get("id")
                        if not isinstance(creative_id, int):
                            continue
                        
                        summary = summaries.get(creative_id)
                        available = summary.available_hours if summary else 0.0
                        logged = logged_hours.get(creative_id, 0.0)
                        planned = planned_hours.get(creative_id, 0.0)
                        
                        # Calculate utilization percentage
                        utilization_percent = None
                        if available > 0:
                            utilization_percent = round((logged / available) * 100.0, 2)
                        
                        # Only include creatives with available hours
                        if available > 0:
                            # Derive market_slug and pool_name for this month (uses correct historical pool)
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
                                    normalized_tags = [str(tag).strip().lower() for tag in tags if isinstance(tag, str)]
                                    for pool_def in POOL_DEFINITIONS:
                                        pool_tag = pool_def.get("tag")
                                        if pool_tag and any(pool_tag in tag for tag in normalized_tags):
                                            pool_name = pool_def.get("label")
                                            break
                            
                            creative_breakdown.append({
                                "id": creative_id,
                                "available_hours": round(available, 2),
                                "logged_hours": round(logged, 2),
                                "planned_hours": round(planned, 2),
                                "utilization_percent": utilization_percent,
                                "market_slug": market_slug,
                                "pool_name": pool_name,
                            })
                    
                    # Cache (always save when force_refresh, or for historical months when not)
                    if cache_service and creative_breakdown and (force_refresh or not is_current):
                        try:
                            cache_data = [
                                {
                                    "creative_id": item["id"],
                                    "available_hours": item["available_hours"],
                                    "logged_hours": item["logged_hours"],
                                    "planned_hours": item.get("planned_hours", 0.0),
                                    "utilization_percent": item.get("utilization_percent"),
                                    "market_slug": item.get("market_slug"),
                                    "pool_name": item.get("pool_name"),
                                }
                                for item in creative_breakdown
                            ]
                            cache_service.save_month_data(year_num, month_num, cache_data)
                        except Exception as e:
                            print(f"Cache save error for {year_num}-{month_num}: {e}")
                
                # Only include in monthly_data for selected year, up to selected month (for chart display)
                if year_num == year and month_num <= current_month_num:
                    monthly_data.append({
                        "month": month_num,
                        "label": month_start.strftime("%b"),
                        "creatives": creative_breakdown,
                    })
        
        return monthly_data
