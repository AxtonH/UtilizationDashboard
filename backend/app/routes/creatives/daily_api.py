"""Per-creative daily hours endpoint for the card calendar view."""
from __future__ import annotations

import threading
import time
from typing import Any, Dict, Optional, Tuple

from flask import current_app, jsonify

from ...integrations.odoo_client import OdooClient, OdooUnavailableError
from ...services.daily_hours_service import DailyHoursService, run_pooled
from ...services.employee_service import EmployeeService
from .blueprint import creatives_bp
from .deps import _get_employee_service
from .view_period import _resolve_view_period

# Target department ids depend only on config + Odoo schema; cache them so the
# per-card endpoint doesn't re-resolve departments on every expand.
_DEPT_CACHE: Dict[str, Any] = {"at": 0.0, "ids": None}
_DEPT_CACHE_LOCK = threading.Lock()
_DEPT_TTL_SECONDS = 600.0

# Short-lived memo of computed payloads: a creative's day breakdown only needs
# to be fresh-ish while users browse cards, and repeat expands (or several
# viewers) shouldn't re-run the Odoo queries.
_PAYLOAD_CACHE: Dict[Tuple[int, str], Tuple[float, Dict[str, Any]]] = {}
_PAYLOAD_CACHE_LOCK = threading.Lock()
_PAYLOAD_TTL_SECONDS = 120.0
_PAYLOAD_MAX_ENTRIES = 256

_EMPLOYEE_FIELDS = [
    "name",
    "department_id",
    "resource_calendar_id",
    "company_id",
    "user_id",
    "resource_id",
]


def _m2o_id(value: Any) -> Optional[int]:
    if isinstance(value, (list, tuple)) and value and isinstance(value[0], int):
        return value[0]
    if isinstance(value, int):
        return value
    return None


def _m2o_name(value: Any) -> Optional[str]:
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return str(value[1])
    return None


def _get_target_department_ids(client: OdooClient) -> set[int]:
    now = time.monotonic()
    with _DEPT_CACHE_LOCK:
        if _DEPT_CACHE["ids"] is not None and (now - _DEPT_CACHE["at"]) < _DEPT_TTL_SECONDS:
            return _DEPT_CACHE["ids"]
    ids = set(EmployeeService(client)._get_target_department_ids())
    with _DEPT_CACHE_LOCK:
        _DEPT_CACHE["ids"] = ids
        _DEPT_CACHE["at"] = time.monotonic()
    return ids


def _fetch_employee_light(client: OdooClient, employee_id: int) -> Optional[Dict[str, Any]]:
    """Fetch just the fields daily_breakdown needs for one employee.

    Avoids the full get_all_creatives download (~2.5s when its memo is cold).
    """
    rows = client.execute_kw(
        "hr.employee",
        "search_read",
        [[("id", "=", employee_id)]],
        {
            "fields": _EMPLOYEE_FIELDS,
            "limit": 1,
            "context": {"active_test": False},
        },
    )
    if not rows:
        return None
    record = rows[0]
    return {
        "id": employee_id,
        "name": record.get("name"),
        "department_id": _m2o_id(record.get("department_id")),
        "resource_calendar_name": _m2o_name(record.get("resource_calendar_id")),
        "company_id": _m2o_id(record.get("company_id")),
        "user_id": _m2o_id(record.get("user_id")),
        "resource_id": _m2o_id(record.get("resource_id")),
    }


@creatives_bp.route("/api/creatives/daily-hours")
def creative_daily_hours_bulk():
    """Daily hours + worked projects for ALL creatives in one response.

    Fired by the frontend in the background after the dashboard payload
    renders, so expanding any card is instant. Costs ~5 batched Odoo queries
    regardless of headcount (vs ~5 per creative on the single endpoint).
    """
    view = _resolve_view_period()
    cache_key = (-1, view.selected_month_key)  # -1 = bulk sentinel, no id overlap
    now = time.monotonic()
    with _PAYLOAD_CACHE_LOCK:
        entry = _PAYLOAD_CACHE.get(cache_key)
        if entry is not None and (now - entry[0]) < _PAYLOAD_TTL_SECONDS:
            return jsonify(entry[1])

    try:
        settings = current_app.config["ODOO_SETTINGS"]
        employees = _get_employee_service().get_all_creatives(include_inactive=True)
        service = DailyHoursService(OdooClient(settings))
        per_creative = service.daily_breakdown_bulk(employees, view.period_start, view.period_end)

        payload = {
            "selected_month": view.selected_month_key,
            "creatives": {str(emp_id): data for emp_id, data in per_creative.items()},
        }
        with _PAYLOAD_CACHE_LOCK:
            _PAYLOAD_CACHE[cache_key] = (time.monotonic(), payload)
            while len(_PAYLOAD_CACHE) > _PAYLOAD_MAX_ENTRIES:
                _PAYLOAD_CACHE.pop(next(iter(_PAYLOAD_CACHE)))
        return jsonify(payload)
    except OdooUnavailableError as exc:
        current_app.logger.warning(
            "Odoo unavailable while serving bulk daily hours API", exc_info=True
        )
        message = str(exc) or "Unable to connect to Odoo. Please try again later."
        return (
            jsonify({"error": "odoo_unavailable", "message": message, "creatives": {}}),
            503,
        )


@creatives_bp.route("/api/creatives/<int:creative_id>/daily-hours")
def creative_daily_hours(creative_id: int):
    """Logged / booked / overtime hours per day for one creative.

    Accepts the same year/month query params as the other dashboard
    endpoints (quarter keys included); the response covers every day of the
    resolved period.
    """
    view = _resolve_view_period()
    cache_key = (creative_id, view.selected_month_key)
    now = time.monotonic()
    with _PAYLOAD_CACHE_LOCK:
        entry = _PAYLOAD_CACHE.get(cache_key)
        if entry is not None and (now - entry[0]) < _PAYLOAD_TTL_SECONDS:
            return jsonify(entry[1])

    try:
        settings = current_app.config["ODOO_SETTINGS"]

        # Both lookups run on the shared worker pool so they reuse persistent
        # Odoo connections instead of paying a TLS handshake per request.
        creative = run_pooled(settings, lambda c: _fetch_employee_light(c, creative_id)).result()
        if creative is None or creative["department_id"] not in run_pooled(
            settings, _get_target_department_ids
        ).result():
            return jsonify({"error": "not_found", "message": "Creative not found"}), 404

        # This client only serves the rare absence top-up path; constructing
        # it is free (no connection until first call).
        service = DailyHoursService(OdooClient(settings))
        payload = service.daily_breakdown(creative, view.period_start, view.period_end)
        payload["selected_month"] = view.selected_month_key

        with _PAYLOAD_CACHE_LOCK:
            _PAYLOAD_CACHE[cache_key] = (time.monotonic(), payload)
            while len(_PAYLOAD_CACHE) > _PAYLOAD_MAX_ENTRIES:
                _PAYLOAD_CACHE.pop(next(iter(_PAYLOAD_CACHE)))
        return jsonify(payload)
    except OdooUnavailableError as exc:
        current_app.logger.warning(
            "Odoo unavailable while serving daily hours API", exc_info=True
        )
        message = str(exc) or "Unable to connect to Odoo. Please try again later."
        return (
            jsonify({"error": "odoo_unavailable", "message": message, "days": []}),
            503,
        )
