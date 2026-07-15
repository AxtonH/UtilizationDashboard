"""Shared finality invariant for monthly Supabase caches.

A closed month's cached rows are only authoritative when they were last
written AFTER the month ended, plus a per-domain grace window. Rows written
mid-month (via manual refresh, a warm cron, or viewing a different month)
would otherwise freeze with the tail of the month missing once the calendar
flips — the "nobody opened the dashboard for the last 10 days of the month"
bug. Provisional rows are dropped by the caller so the month recomputes and
re-caches with a post-close timestamp: self-healing, no manual refresh.

Months closed longer than ``LEGACY_TRUST_AFTER_DAYS`` ago are trusted as-is,
so legacy rows written before this invariant existed cannot trigger a mass
recompute of deep history; the manual refresh endpoints remain the tool for
rewriting old months.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Mapping, Optional, Sequence, Tuple

# Timesheets are commonly back-filled in the first days of the next month.
UTILIZATION_CACHE_FINALIZE_GRACE_DAYS = 5

# Invoices / sales orders keep landing during month-end closing.
SALES_CACHE_FINALIZE_GRACE_DAYS = 7

LEGACY_TRUST_AFTER_DAYS = 180


def parse_cache_timestamp(value: Any) -> Optional[datetime]:
    """Parse a Supabase timestamptz value into an aware UTC datetime."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def cached_month_rows_are_final(
    rows: Sequence[Mapping[str, Any]],
    month_end: date,
    grace_days: int,
    timestamp_keys: Tuple[str, ...] = ("updated_at", "cached_at"),
) -> bool:
    """True when the newest row timestamp is past the month's finalize threshold.

    Rows without parseable timestamps are treated as trusted (previous
    behavior) — every cache table involved stamps writes, so that only
    happens for genuinely legacy data.
    """
    if (date.today() - month_end).days > LEGACY_TRUST_AFTER_DAYS:
        return True

    finalize_after = datetime.combine(
        month_end + timedelta(days=1 + grace_days),
        time.min,
        tzinfo=timezone.utc,
    )
    latest: Optional[datetime] = None
    for row in rows:
        for key in timestamp_keys:
            parsed = parse_cache_timestamp(row.get(key))
            if parsed is not None and (latest is None or parsed > latest):
                latest = parsed
    if latest is None:
        return True
    return latest >= finalize_after
