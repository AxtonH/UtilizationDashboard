"""Resolve a creative's assignment (Business Unit / Sub Business Unit / Pod) for a target month.

The dashboard transitioned from a market+pool taxonomy to a business-unit taxonomy
on 2026-04-01. For target months before the cutover the legacy resolver in
``routes.creatives._get_creative_market_for_month`` continues to apply. From the
cutover onward, callers should use ``resolve_business_unit_for_month`` (defined
here) which walks the new ``x_studio_business_unit`` / ``x_studio_sub_business_unit``
/ ``x_studio_pod`` slots with their dedicated start/end-date pairs.

Slot layout on ``hr.employee`` (per Operations, Apr 2026):

    Slot        BU                              SBU                                  Pod                  Start                       End
    Current     x_studio_business_unit          x_studio_sub_business_unit           x_studio_pod         x_studio_start_date_4       x_studio_end_date_4
    Previous 1  x_studio_business_unit_1        x_studio_sub_business_unit_1         x_studio_pod_1       x_studio_start_date_5       x_studio_end_date_5
    Previous 2  x_studio_business_unit_2        x_studio_sub_business_unit_2         x_studio_pod_2       x_studio_start_date_6       x_studio_end_date_6
    Previous 3  x_studio_business_unit_3        x_studio_sub_business_unit_3         x_studio_pod_3       x_studio_start_date_7       x_studio_end_date_7

Slot ordering and overlap rules mirror the legacy resolver: try current first,
then previous 1/2/3; a slot with both dates set must overlap the target month;
a slot with only a start date matches when the target month is on/after it; a
slot with no start date is skipped.
"""
from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable, Mapping, Optional, Set


CUTOVER_DATE = date(2026, 4, 1)


@dataclass(frozen=True)
class BusinessUnitAssignment:
    """Resolved BU/SBU/Pod for a single target month."""

    business_unit: Optional[str]
    sub_business_unit: Optional[str]
    pod: Optional[str]


def use_business_unit_model(target_month: date) -> bool:
    """True when the target month is on/after the BU-model cutover (2026-04-01)."""
    return target_month >= CUTOVER_DATE


def split_assignment_field_tokens(value: Any) -> Set[str]:
    """Split a comma-separated BU / SBU / Pod display string into trimmed tokens."""
    if not value or not isinstance(value, str):
        return set()
    return {part.strip() for part in value.split(",") if part.strip()}


def creative_matches_bu_assignment_filters(
    creative: Mapping[str, Any],
    selected_business_units: Optional[Iterable[str]] = None,
    selected_sub_business_units: Optional[Iterable[str]] = None,
    selected_pods: Optional[Iterable[str]] = None,
) -> bool:
    """AND across BU, SBU, and pod dimensions; within each dimension, OR of selected tokens.

    Selected values match if they appear as comma-separated tokens on the corresponding
    field (same storage shape as enriched ``business_unit`` / ``sub_business_unit`` / ``pod``).
    """
    bu_sel = [str(x).strip() for x in (selected_business_units or ()) if x is not None and str(x).strip()]
    sbu_sel = [str(x).strip() for x in (selected_sub_business_units or ()) if x is not None and str(x).strip()]
    pod_sel = [str(x).strip() for x in (selected_pods or ()) if x is not None and str(x).strip()]
    if not bu_sel and not sbu_sel and not pod_sel:
        return True

    bu_tokens = split_assignment_field_tokens(creative.get("business_unit"))
    sbu_tokens = split_assignment_field_tokens(creative.get("sub_business_unit"))
    pod_tokens = split_assignment_field_tokens(creative.get("pod"))

    if bu_sel and not bu_tokens.intersection(bu_sel):
        return False
    if sbu_sel and not sbu_tokens.intersection(sbu_sel):
        return False
    if pod_sel and not pod_tokens.intersection(pod_sel):
        return False
    return True


def resolve_business_unit_for_month(
    creative: Mapping[str, Any],
    target_month: date,
) -> Optional[BusinessUnitAssignment]:
    """Walk the BU slots in order (current → prev 1 → prev 2 → prev 3) and return
    the first one whose date window contains ``target_month``.

    Returns ``None`` if no slot matches or if the matched slot has no business unit.
    """
    if not creative:
        return None

    month_start = target_month.replace(day=1)
    _, last_day = monthrange(month_start.year, month_start.month)
    month_end = month_start.replace(day=last_day)

    for slot_index, slot in enumerate(_SLOTS):
        bu_raw = creative.get(slot.bu_key)
        sbu_raw = creative.get(slot.sbu_key)
        pod_raw = creative.get(slot.pod_key)
        if not (bu_raw or sbu_raw or pod_raw):
            continue
        start = creative.get(slot.start_key)
        end = creative.get(slot.end_key)
        # Current slot (index 0) may be filled without dates while Ops rolls out the
        # new fields; treat that as an open assignment. Historical slots still need
        # a date window so we do not resurrect stale rows.
        allow_undated_current = slot_index == 0
        if not _slot_matches(
            start,
            end,
            month_start,
            month_end,
            target_month,
            allow_undated_open_assignment=allow_undated_current,
        ):
            continue
        assignment = BusinessUnitAssignment(
            business_unit=_clean_assignment_label(bu_raw),
            sub_business_unit=_clean_assignment_label(sbu_raw),
            pod=_clean_assignment_label(pod_raw),
        )
        if assignment.business_unit or assignment.sub_business_unit or assignment.pod:
            return assignment

    return None


@dataclass(frozen=True)
class _Slot:
    bu_key: str
    sbu_key: str
    pod_key: str
    start_key: str
    end_key: str


_SLOTS: tuple[_Slot, ...] = (
    _Slot(
        bu_key="current_business_unit",
        sbu_key="current_sub_business_unit",
        pod_key="current_pod",
        start_key="current_business_unit_start",
        end_key="current_business_unit_end",
    ),
    _Slot(
        bu_key="previous_business_unit_1",
        sbu_key="previous_sub_business_unit_1",
        pod_key="previous_pod_1",
        start_key="previous_business_unit_1_start",
        end_key="previous_business_unit_1_end",
    ),
    _Slot(
        bu_key="previous_business_unit_2",
        sbu_key="previous_sub_business_unit_2",
        pod_key="previous_pod_2",
        start_key="previous_business_unit_2_start",
        end_key="previous_business_unit_2_end",
    ),
    _Slot(
        bu_key="previous_business_unit_3",
        sbu_key="previous_sub_business_unit_3",
        pod_key="previous_pod_3",
        start_key="previous_business_unit_3_start",
        end_key="previous_business_unit_3_end",
    ),
)


def _slot_matches(
    start: Optional[date],
    end: Optional[date],
    month_start: date,
    month_end: date,
    target_month: date,
    *,
    allow_undated_open_assignment: bool = False,
) -> bool:
    """Overlap rules aligned with the legacy market resolver, plus optional undated current slot."""
    if start and end:
        return start <= month_end and end >= month_start
    if start and not end:
        return target_month >= start.replace(day=1)
    if not start and not end and allow_undated_open_assignment:
        return True
    return False


def _clean(value: Any) -> Optional[str]:
    """Trim a value to a non-empty string, or return None."""
    if not value:
        return None
    text = str(value).strip()
    return text or None


def _clean_assignment_label(value: Any) -> Optional[str]:
    """Normalize Odoo many2one / many2many / char values for BU/SBU/Pod display."""
    if value in (None, False):
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, (list, tuple)):
        if not value:
            return None
        if all(isinstance(item, (list, tuple)) and len(item) >= 2 for item in value):
            names: list[str] = []
            for item in value:
                label = item[1]
                if label is None or label is False:
                    continue
                t = str(label).strip()
                if t and t not in names:
                    names.append(t)
            return ", ".join(names) if names else None
        if len(value) == 2 and isinstance(value[0], int) and isinstance(value[1], str):
            t = value[1].strip()
            return t or None
        if all(isinstance(x, int) for x in value):
            return None
    text = str(value).strip()
    return text or None
