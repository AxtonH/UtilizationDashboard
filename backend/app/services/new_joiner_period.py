"""New joiner ramp: exclude hours from utilization totals for the first 3 calendar months after join."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional


def add_months(anchor: date, offset: int) -> date:
    """Return the first day of the month `offset` months after `anchor` (anchor must be day 1)."""
    year = anchor.year + (anchor.month - 1 + offset) // 12
    month = (anchor.month - 1 + offset) % 12 + 1
    return date(year, month, 1)


def parse_joining_date(value: Any) -> Optional[date]:
    """Parse Odoo joining date (string, date, or datetime)."""
    if value is None:
        return None
    # datetime must be checked before date: datetime is a subclass of date in Python.
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        date_part = stripped.split("T")[0].split(" ")[0][:10]
        try:
            return datetime.strptime(date_part, "%Y-%m-%d").date()
        except (ValueError, AttributeError):
            try:
                return datetime.fromisoformat(stripped.replace("Z", "+00:00")).date()
            except (ValueError, AttributeError):
                return None
    return None


def period_overlaps_new_joiner_ramp(
    joining_date: date,
    period_start: date,
    period_end: date,
) -> bool:
    """True if [period_start, period_end] overlaps the 3 calendar months starting the join month.

    Example: join Jan 2026 → ramp is Jan–Mar 2026 inclusive; hours count from April 2026.
    """
    ramp_start = date(joining_date.year, joining_date.month, 1)
    ramp_end_exclusive = add_months(ramp_start, 3)
    return period_start < ramp_end_exclusive and period_end >= ramp_start
