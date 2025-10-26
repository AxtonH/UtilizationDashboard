"""Routes for creatives dashboard."""
from __future__ import annotations

import re
from copy import deepcopy
from calendar import monthrange
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from flask import Blueprint, current_app, g, jsonify, render_template, request

from ..integrations.odoo_client import OdooClient, OdooUnavailableError
from ..services.availability_service import AvailabilityService, AvailabilitySummary
from ..services.employee_service import EmployeeService
from ..services.planning_service import PlanningService
from ..services.timesheet_service import TimesheetService
from ..services.external_hours_service import ExternalHoursService
from ..services.utilization_service import UtilizationService

creatives_bp = Blueprint("creatives", __name__)


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
        g.external_hours_service = ExternalHoursService(_get_odoo_client())
    return g.external_hours_service


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

@creatives_bp.before_app_request
def _inject_service_into_app_context() -> None:
    """Ensure Odoo settings dataclass is available via config for reuse."""
    if "ODOO_SETTINGS" not in current_app.config:
        from ..config import Config

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


@creatives_bp.route("/")
def dashboard():
    selected_month = _resolve_month()
    try:
        month_start, month_end = _month_bounds(selected_month)
        creatives = _creatives_with_availability(month_start, month_end)
        stats = _creatives_stats(creatives)
        aggregates = _creatives_aggregates(creatives)
        month_options = _month_options(selected_month)
        pool_stats = _pool_stats(creatives)
        client_payload, filter_options, agreement_filter, account_filter = _build_client_dashboard_payload(
            selected_month,
            request.args.get("agreement_type"),
            request.args.get("account_type"),
        )

        context = {
            "creatives": creatives,
            "month_options": month_options,
            "selected_month": selected_month.strftime("%Y-%m"),
            "readable_month": selected_month.strftime("%B %Y"),
            "stats": stats,
            "aggregates": aggregates,
            "pool_stats": pool_stats,
            "client_filter_options": filter_options,
            "selected_agreement_type": agreement_filter or "",
            "selected_account_type": account_filter or "",
            "odoo_unavailable": False,
            "odoo_error_message": None,
        }
        context.update(client_payload)
        return render_template("creatives/dashboard.html", **context)
    except OdooUnavailableError as exc:
        current_app.logger.warning("Odoo unavailable while rendering dashboard", exc_info=True)
        context = _empty_dashboard_context(
            selected_month,
            error_message=str(exc) if str(exc) else "Unable to connect to Odoo. Please try again shortly.",
        )
        return render_template("creatives/dashboard.html", **context), 503


@creatives_bp.route("/api/creatives")
def creatives_api():
    selected_month = _resolve_month()
    try:
        month_start, month_end = _month_bounds(selected_month)
        creatives = _creatives_with_availability(month_start, month_end)
        stats = _creatives_stats(creatives)
        aggregates = _creatives_aggregates(creatives)
        pool_stats = _pool_stats(creatives)
        client_payload, filter_options, agreement_filter, account_filter = _build_client_dashboard_payload(
            selected_month,
            request.args.get("agreement_type"),
            request.args.get("account_type"),
        )
        response_payload: Dict[str, Any] = {
            "creatives": creatives,
            "selected_month": selected_month.strftime("%Y-%m"),
            "readable_month": selected_month.strftime("%B %Y"),
            "stats": stats,
            "aggregates": aggregates,
            "pool_stats": pool_stats,
            "client_filter_options": filter_options,
            "selected_filters": {
                "agreement_type": agreement_filter or "",
                "account_type": account_filter or "",
            },
            "odoo_unavailable": False,
        }
        response_payload.update(client_payload)
        return jsonify(response_payload)
    except OdooUnavailableError as exc:
        current_app.logger.warning("Odoo unavailable while serving creatives API", exc_info=True)
        error_message = str(exc) if str(exc) else "Unable to connect to Odoo. Please try again later."
        fallback_state = _base_dashboard_state(selected_month)
        response_payload = {
            **fallback_state,
            "selected_month": selected_month.strftime("%Y-%m"),
            "readable_month": selected_month.strftime("%B %Y"),
            "client_filter_options": fallback_state.get("client_filter_options", {"agreement_types": [], "account_types": []}),
            "selected_filters": {"agreement_type": "", "account_type": ""},
            "error": "odoo_unavailable",
            "message": error_message,
            "odoo_unavailable": True,
        }
        return jsonify(response_payload), 503


@creatives_bp.route("/api/client-dashboard")
def client_dashboard_api():
    selected_month = _resolve_month()
    try:
        client_payload, filter_options, agreement_filter, account_filter = _build_client_dashboard_payload(
            selected_month,
            request.args.get("agreement_type"),
            request.args.get("account_type"),
        )
        response_payload = {
            **client_payload,
            "client_filter_options": filter_options,
            "selected_filters": {
                "agreement_type": agreement_filter or "",
                "account_type": account_filter or "",
            },
            "selected_month": selected_month.strftime("%Y-%m"),
            "readable_month": selected_month.strftime("%B %Y"),
            "odoo_unavailable": False,
        }
        return jsonify(response_payload)
    except OdooUnavailableError as exc:
        current_app.logger.warning("Odoo unavailable while serving client dashboard API", exc_info=True)
        error_message = str(exc) if str(exc) else "Unable to connect to Odoo. Please try again later."
        fallback_payload, filter_options, _, _ = _empty_client_dashboard_payload(selected_month)
        response_payload = {
            **fallback_payload,
            "client_filter_options": filter_options,
            "selected_filters": {"agreement_type": "", "account_type": ""},
            "selected_month": selected_month.strftime("%Y-%m"),
            "readable_month": selected_month.strftime("%B %Y"),
            "error": "odoo_unavailable",
            "message": error_message,
            "odoo_unavailable": True,
        }
        return jsonify(response_payload), 503


@creatives_bp.route("/api/utilization")
def utilization_api():
    selected_month = _resolve_month()
    try:
        month_start, month_end = _month_bounds(selected_month)
        utilization_service = _get_utilization_service()
        summary = utilization_service.get_utilization_summary(month_start, month_end)
        summary["odoo_unavailable"] = False
        summary["selected_month"] = selected_month.strftime("%Y-%m")
        summary["readable_month"] = selected_month.strftime("%B %Y")
        return jsonify(summary)
    except OdooUnavailableError as exc:
        current_app.logger.warning("Odoo unavailable while serving utilization API", exc_info=True)
        error_message = str(exc) if str(exc) else "Unable to connect to Odoo. Please try again later."
        summary = _empty_utilization_summary()
        summary.update(
            {
                "selected_month": selected_month.strftime("%Y-%m"),
                "readable_month": selected_month.strftime("%B %Y"),
                "error": "odoo_unavailable",
                "message": error_message,
                "odoo_unavailable": True,
            }
        )
        return jsonify(summary), 503


def _resolve_month() -> date:
    month_str = request.args.get("month")
    today = date.today()
    default_month = today.replace(day=1)
    if default_month < MIN_MONTH:
        default_month = MIN_MONTH

    if not month_str:
        return default_month

    try:
        parsed = datetime.strptime(month_str, "%Y-%m")
        resolved = parsed.date().replace(day=1)
        return resolved if resolved >= MIN_MONTH else MIN_MONTH
    except ValueError:
        return default_month


def _month_bounds(month_start: date) -> Tuple[date, date]:
    last_day = monthrange(month_start.year, month_start.month)[1]
    month_end = month_start.replace(day=last_day)
    return month_start, month_end


MIN_MONTH = date(2025, 1, 1)

POOL_DEFINITIONS = [
    {"slug": "ksa", "label": "KSA", "tag": "ksa"},
    {"slug": "nightshift", "label": "Nightshift", "tag": "nightshift"},
    {"slug": "uae", "label": "UAE", "tag": "uae"},
]



def _month_options(center_month: date, window: int = 6) -> List[Dict[str, str]]:
    options: List[Dict[str, str]] = []
    start_month = MIN_MONTH
    end_month = _add_months(center_month, window)
    if end_month < start_month:
        end_month = start_month

    option_month = start_month
    while option_month <= end_month:
        options.append(
            {
                "value": option_month.strftime("%Y-%m"),
                "label": option_month.strftime("%B %Y"),
                "current": option_month == center_month,
            }
        )
        option_month = _add_months(option_month, 1)
    return options


def _add_months(anchor: date, offset: int) -> date:
    year = anchor.year + (anchor.month - 1 + offset) // 12
    month = (anchor.month - 1 + offset) % 12 + 1
    return date(year, month, 1)


def _creatives_with_availability(month_start: date, month_end: date) -> List[Dict[str, object]]:
    employee_service = _get_employee_service()
    availability_service = _get_availability_service()
    planning_service = _get_planning_service()
    timesheet_service = _get_timesheet_service()

    creatives = employee_service.get_creatives()
    summaries = availability_service.calculate_monthly_availability(creatives, month_start, month_end)
    planned_hours = planning_service.planned_hours_for_month(creatives, month_start, month_end)
    logged_hours = timesheet_service.logged_hours_for_month(creatives, month_start, month_end)

    enriched: List[Dict[str, object]] = []
    for creative in creatives:
        creative_id = creative.get("id")
        summary: AvailabilitySummary | None = summaries.get(creative_id) if isinstance(creative_id, int) else None
        base_hours = round(summary.base_hours, 2) if summary else 0.0
        time_off_hours = round(summary.time_off_hours, 2) if summary else 0.0
        public_holiday_hours = round(summary.public_holiday_hours, 2) if summary else 0.0
        available_hours = (
            round(summary.available_hours, 2)
            if summary
            else round(max(base_hours - public_holiday_hours - time_off_hours, 0.0), 2)
        )
        planned = round(planned_hours.get(creative_id, 0.0), 2) if isinstance(creative_id, int) else 0.0
        logged = round(logged_hours.get(creative_id, 0.0), 2) if isinstance(creative_id, int) else 0.0

        planned_utilization = _calculate_utilization(planned, available_hours)
        logged_utilization = _calculate_utilization(logged, available_hours)
        utilization_status = _utilization_status(planned_utilization, logged_utilization)

        enriched.append(
            {
                **creative,
                "base_hours": base_hours,
                "base_hours_display": _format_hours_minutes(base_hours),
                "time_off_hours": time_off_hours,
                "time_off_hours_display": _format_hours_minutes(time_off_hours),
                "public_holiday_hours": public_holiday_hours,
                "public_holiday_hours_display": _format_hours_minutes(public_holiday_hours),
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
            }
        )

    return enriched


def _creatives_stats(creatives: List[Dict[str, object]]) -> Dict[str, int]:
    total = len(creatives)
    available = 0
    active = 0
    for creative in creatives:
        available_hours = float(creative.get("available_hours", 0) or 0)
        if available_hours > 0:
            available += 1
        logged_hours = float(creative.get("logged_hours", 0) or 0)
        if logged_hours > 0:
            active += 1
    return {"total": total, "available": available, "active": active}


def _creatives_aggregates(creatives: List[Dict[str, object]]) -> Dict[str, Any]:
    totals = {"planned": 0.0, "logged": 0.0, "available": 0.0}
    for creative in creatives:
        totals["planned"] += float(creative.get("planned_hours", 0) or 0.0)
        totals["logged"] += float(creative.get("logged_hours", 0) or 0.0)
        totals["available"] += float(creative.get("available_hours", 0) or 0.0)
    max_value = max(totals.values()) if totals else 0.0
    display = {key: _format_hours_minutes(value) for key, value in totals.items()}
    return {**totals, "max": max_value, "display": display}


def _pool_stats(creatives: List[Dict[str, object]]) -> List[Dict[str, Any]]:
    pools = [
        {"name": "KSA", "tag": "ksa", "slug": "ksa"},
        {"name": "Nightshift", "tag": "nightshift", "slug": "nightshift"},
        {"name": "UAE", "tag": "uae", "slug": "uae"},
    ]

    def match_pool(tags: List[str] | None, target: str) -> bool:
        if not tags:
            return False
        normalized = [str(tag).lower() for tag in tags if isinstance(tag, str)]
        return any(target in tag for tag in normalized)

    results: List[Dict[str, Any]] = []
    for pool in pools:
        members = [creative for creative in creatives if match_pool(creative.get("tags"), pool["tag"])]
        total = len(members)
        available = sum(1 for creative in members if float(creative.get("available_hours", 0) or 0) > 0)
        active = sum(1 for creative in members if float(creative.get("logged_hours", 0) or 0) > 0)
        total_available_hours = sum(float(creative.get("available_hours", 0) or 0) for creative in members)
        total_planned_hours = sum(float(creative.get("planned_hours", 0) or 0) for creative in members)
        total_logged_hours = sum(float(creative.get("logged_hours", 0) or 0) for creative in members)
        results.append(
            {
                "name": pool["name"],
                "slug": pool["slug"],
                "total_creatives": total,
                "available_creatives": available,
                "active_creatives": active,
                "available_hours": total_available_hours,
                "available_hours_display": _format_hours_minutes(total_available_hours),
                "planned_hours": total_planned_hours,
                "planned_hours_display": _format_hours_minutes(total_planned_hours),
                "logged_hours": total_logged_hours,
                "logged_hours_display": _format_hours_minutes(total_logged_hours),
            }
        )
    return results


def _format_hours_minutes(value: float) -> str:
    total_minutes = int(round(value * 60))
    hours, minutes = divmod(total_minutes, 60)
    if minutes == 0:
        return f"{hours}h"
    return f"{hours}h {minutes:02d}m"


def _calculate_utilization(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return round((numerator / denominator) * 100, 1)


def _format_percentage(value: float) -> str:
    rounded = round(value, 1)
    if float(rounded).is_integer():
        return f"{int(rounded)}%"
    return f"{rounded:.1f}%"


def _utilization_status(planned_percent: float, logged_percent: float) -> str:
    if planned_percent < 50 or logged_percent < 50:
        return "critical"
    if planned_percent < 75 or logged_percent < 75:
        return "warning"
    return "healthy"


def _format_aed_value(value: float) -> str:
    return f"{value:,.2f} AED"


def _normalize_client_key(
    project_id: Any,
    name: Any,
    market: Any,
) -> Tuple[Tuple[Any, ...], Optional[int], str, str]:
    client_name = str(name).strip() if isinstance(name, str) else ""
    market_name = str(market).strip() if isinstance(market, str) else ""
    if not client_name:
        client_name = "Unassigned Client"
    if not market_name:
        market_name = "Unassigned Market"
    if isinstance(project_id, int):
        key: Tuple[Any, ...] = ("id", project_id)
        normalized_id: Optional[int] = project_id
    else:
        key = ("name", market_name.lower(), client_name.lower())
        normalized_id = None
    return key, normalized_id, client_name, market_name


def _extract_sales_top_clients(markets: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    clients: List[Dict[str, Any]] = []
    for market in markets or []:
        market_name = market.get("market")
        projects = market.get("projects") or []
        for project in projects:
            project_name = project.get("project_name")
            revenue_value = float(project.get("total_aed", 0.0) or 0.0)
            request_count = len(project.get("sales_orders") or [])
            project_id = project.get("project_id")
            clients.append(
                {
                    "project_id": project_id if isinstance(project_id, int) else None,
                    "client_name": project_name,
                    "market": market_name,
                    "total_revenue_aed": revenue_value,
                    "request_count": request_count,
                }
            )
    return clients



def _infer_pool_from_sources(
    tags: Iterable[str] | None = None,
    *candidates: object,
) -> str | None:
    tokens: list[str] = []
    if tags:
        tokens.extend(str(tag).lower() for tag in tags if isinstance(tag, str))
    for candidate in candidates:
        if not candidate:
            continue
        if isinstance(candidate, (list, tuple)):
            tokens.extend(str(item).lower() for item in candidate if isinstance(item, str))
        else:
            tokens.append(str(candidate).lower())
    for definition in POOL_DEFINITIONS:
        token = definition["tag"].lower()
        if any(token in value for value in tokens):
            return definition["slug"]
    return None


def _format_hours_display(value: float) -> str:
    if not value or abs(value) < 1e-6:
        return "0h"
    rounded = round(value, 1)
    if abs(rounded - round(rounded)) < 0.1:
        return f"{int(round(rounded)):,}h"
    return f"{rounded:,.1f}h"


def _format_currency_display(value: float) -> str:
    return f"{value:,.2f} AED"


def _extract_agreement_tokens(raw: Any) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        stripped = raw.strip()
        if not stripped:
            return []
        tokens = [part.strip() for part in re.split(r"[,/&|]+", stripped) if part.strip()]
        return tokens or [stripped]
    if isinstance(raw, (list, tuple, set)):
        tokens: List[str] = []
        for item in raw:
            tokens.extend(_extract_agreement_tokens(item))
        return tokens
    return []


def _normalize_agreements(values: Iterable[str]) -> List[str]:
    seen: set[str] = set()
    normalized: List[str] = []
    for value in values:
        stripped = value.strip()
        if not stripped:
            continue
        key = stripped.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(stripped)
    return normalized


def _infer_account_type(tags: Iterable[Any] | None) -> str:
    if not tags:
        return "non-key"
    normalized_tags: List[str] = []
    for tag in tags:
        if isinstance(tag, str):
            normalized_tags.append(tag.strip().lower())
    for value in normalized_tags:
        if "non-key" in value or "non key" in value:
            return "non-key"
    for value in normalized_tags:
        if "key account" in value:
            return "key"
    return "non-key"


def _annotate_client_markets(
    markets: Iterable[Mapping[str, Any]] | None,
    entry_key: str,
) -> List[Dict[str, Any]]:
    annotated: List[Dict[str, Any]] = []
    for market in markets or []:
        market_label = str(market.get("market") or "Unassigned Market").strip() or "Unassigned Market"
        entries: List[Dict[str, Any]] = []
        for entry in market.get(entry_key, []) or []:
            entry_copy: Dict[str, Any] = deepcopy(entry)
            agreements = _normalize_agreements(_extract_agreement_tokens(entry_copy.get("agreement_type")))
            if not agreements:
                agreements = ["Unknown"]
            entry_copy["_agreement_tokens"] = agreements
            entry_copy["_account_type"] = _infer_account_type(entry_copy.get("tags"))
            entries.append(entry_copy)
        annotated.append({"market": market_label, entry_key: entries})
    return annotated


def _collect_client_filter_options(
    sales_markets: Iterable[Mapping[str, Any]] | None,
    subscription_markets: Iterable[Mapping[str, Any]] | None,
) -> Dict[str, List[str]]:
    agreement_candidates: List[str] = []
    account_candidates: set[str] = set()

    for market in sales_markets or []:
        for project in market.get("projects", []) or []:
            agreement_candidates.extend(project.get("_agreement_tokens", []))
            account = project.get("_account_type")
            if isinstance(account, str) and account:
                account_candidates.add(account)

    for market in subscription_markets or []:
        for subscription in market.get("subscriptions", []) or []:
            agreement_candidates.extend(subscription.get("_agreement_tokens", []))
            account = subscription.get("_account_type")
            if isinstance(account, str) and account:
                account_candidates.add(account)

    agreements = sorted(_normalize_agreements(agreement_candidates), key=str.casefold)
    account_candidates.update({"key", "non-key"})
    account_order = {"key": 0, "non-key": 1}
    accounts = sorted(
        {value.strip().lower() for value in account_candidates if isinstance(value, str) and value.strip()},
        key=lambda value: (account_order.get(value, 99), value)
    )
    return {
        "agreement_types": agreements,
        "account_types": accounts,
    }


def _normalize_agreement_filter(
    raw_value: Optional[str],
    available: Iterable[str],
) -> Optional[str]:
    if not raw_value:
        return None
    candidate = raw_value.strip()
    if not candidate:
        return None
    lookup = {value.lower(): value for value in available}
    return lookup.get(candidate.lower())


def _normalize_account_filter(
    raw_value: Optional[str],
    available: Iterable[str],
) -> Optional[str]:
    if not raw_value:
        return None
    candidate = raw_value.strip().lower()
    if not candidate:
        return None
    mapping = {
        "key": "key",
        "key account": "key",
        "key-account": "key",
        "key_account": "key",
        "non-key": "non-key",
        "non key": "non-key",
        "nonkey": "non-key",
        "non-key account": "non-key",
        "non key account": "non-key",
        "non_key": "non-key",
    }
    canonical = mapping.get(candidate)
    if canonical is None:
        return None
    available_lookup = {value.lower(): value for value in available}
    return available_lookup.get(canonical, available_lookup.get(canonical.lower()))


def _extract_subscription_top_clients_from_markets(
    markets: Iterable[Mapping[str, Any]] | None,
) -> List[Dict[str, Any]]:
    aggregated: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
    for market in markets or []:
        market_name = market.get("market")
        for subscription in market.get("subscriptions", []) or []:
            key, normalized_id, client_name, normalized_market = _normalize_client_key(
                subscription.get("project_id"),
                subscription.get("project_name"),
                market_name,
            )
            bucket = aggregated.setdefault(
                key,
                {
                    "project_id": normalized_id,
                    "client_name": client_name,
                    "market": normalized_market,
                    "total_revenue_aed": 0.0,
                    "request_count": 0,
                },
            )
            revenue_delta = float(subscription.get("aed_total", 0.0) or 0.0)
            bucket["total_revenue_aed"] += revenue_delta
            parent_tasks = subscription.get("subscription_parent_tasks")
            requests = len(parent_tasks) if isinstance(parent_tasks, list) else 0
            if requests > bucket["request_count"]:
                bucket["request_count"] = requests

    top_clients: List[Dict[str, Any]] = []
    for record in aggregated.values():
        total_revenue = float(record.get("total_revenue_aed", 0.0) or 0.0)
        record["total_revenue_aed"] = total_revenue
        record["total_revenue_aed_display"] = _format_aed_value(total_revenue)
        top_clients.append(record)

    top_clients.sort(
        key=lambda item: (
            -item["total_revenue_aed"],
            item["client_name"].lower(),
        )
    )
    return top_clients


def _apply_client_filters(
    sales_markets: Iterable[Mapping[str, Any]] | None,
    subscription_markets: Iterable[Mapping[str, Any]] | None,
    agreement_filter: Optional[str],
    account_filter: Optional[str],
) -> Dict[str, Any]:
    def _matches(entry: Mapping[str, Any]) -> bool:
        agreements = entry.get("_agreement_tokens", []) or []
        if agreement_filter:
            agreement_values = {token.lower() for token in agreements if isinstance(token, str)}
            if agreement_filter.lower() not in agreement_values:
                return False
        account = entry.get("_account_type")
        if account_filter:
            if not isinstance(account, str):
                return False
            if account.lower() != account_filter.lower():
                return False
        return True

    filtered_sales: List[Dict[str, Any]] = []
    total_projects = 0
    total_external_hours = 0.0
    total_revenue = 0.0
    total_invoices = 0

    for market in sales_markets or []:
        matching_projects = [
            deepcopy(project)
            for project in market.get("projects", []) or []
            if _matches(project)
        ]
        if not matching_projects:
            continue
        market_hours = sum(float(project.get("total_external_hours", 0.0) or 0.0) for project in matching_projects)
        market_revenue = sum(float(project.get("total_aed", 0.0) or 0.0) for project in matching_projects)
        market_invoices = sum(len(project.get("sales_orders") or []) for project in matching_projects)
        market_label = market.get("market") or "Unassigned Market"
        filtered_sales.append(
            {
                "market": market_label,
                "projects": matching_projects,
                "total_external_hours": market_hours,
                "total_external_hours_display": _format_hours_display(market_hours),
                "total_aed": market_revenue,
                "total_aed_display": _format_currency_display(market_revenue),
                "total_invoices": market_invoices,
            }
        )
        total_projects += len(matching_projects)
        total_external_hours += market_hours
        total_revenue += market_revenue
        total_invoices += market_invoices

    sales_summary = {
        "total_projects": total_projects,
        "total_external_hours": total_external_hours,
        "total_external_hours_display": _format_hours_display(total_external_hours),
        "total_revenue_aed": total_revenue,
        "total_revenue_aed_display": _format_currency_display(total_revenue),
        "total_invoices": total_invoices,
    }

    filtered_subscriptions: List[Dict[str, Any]] = []
    total_monthly_hours = 0.0
    total_subscription_used_hours = 0.0
    total_subscription_revenue = 0.0
    subscription_total_count: int = 0

    for market in subscription_markets or []:
        matching_subscriptions = [
            deepcopy(subscription)
            for subscription in market.get("subscriptions", []) or []
            if _matches(subscription)
        ]
        if not matching_subscriptions:
            continue
        market_label = market.get("market") or "Unassigned Market"
        # Deduplicate by order reference within a market to avoid duplicate cards
        order_map: Dict[str, Dict[str, Any]] = {}
        for subscription in matching_subscriptions:
            reference = str(subscription.get("order_reference") or "").strip()
            if not reference:
                reference = str(subscription.get("project_name") or "").strip()
            if not reference:
                continue
            order_map.setdefault(reference, subscription)

        deduped_subscriptions = list(order_map.values())
        market_monthly_hours = sum(
            float(subscription.get("monthly_billable_hours", 0.0) or 0.0)
            for subscription in deduped_subscriptions
        )
        market_revenue = sum(float(subscription.get("aed_total", 0.0) or 0.0) for subscription in deduped_subscriptions)
        market_used_hours = sum(
            float(subscription.get("subscription_used_hours", 0.0) or 0.0)
            for subscription in deduped_subscriptions
        )
        filtered_subscriptions.append(
            {
                "market": market_label,
                "subscriptions": deduped_subscriptions,
                "total_monthly_hours": market_monthly_hours,
                "total_monthly_hours_display": _format_hours_display(market_monthly_hours),
                "total_aed": market_revenue,
                "total_aed_display": _format_currency_display(market_revenue),
                "total_subscription_used_hours": market_used_hours,
                "total_subscription_used_hours_display": _format_hours_display(market_used_hours),
            }
        )
        total_monthly_hours += market_monthly_hours
        total_subscription_revenue += market_revenue
        total_subscription_used_hours += market_used_hours
        # Count one card per unique order reference
        subscription_total_count += len(deduped_subscriptions)

    subscription_summary = {
        "total_subscriptions": subscription_total_count,
        "total_monthly_hours": total_monthly_hours,
        "total_monthly_hours_display": _format_hours_display(total_monthly_hours),
        "total_revenue_aed": total_subscription_revenue,
        "total_revenue_aed_display": _format_currency_display(total_subscription_revenue),
        "total_subscription_used_hours": total_subscription_used_hours,
        "total_subscription_used_hours_display": _format_hours_display(total_subscription_used_hours),
    }

    sales_top_clients = _extract_sales_top_clients(filtered_sales)
    subscription_top_clients = _extract_subscription_top_clients_from_markets(filtered_subscriptions)

    return {
        "sales_markets": filtered_sales,
        "sales_summary": sales_summary,
        "subscription_markets": filtered_subscriptions,
        "subscription_summary": subscription_summary,
        "sales_top_clients": sales_top_clients,
        "subscription_top_clients": subscription_top_clients,
    }


def _build_client_dashboard_payload(
    selected_month: date,
    agreement_value: Optional[str],
    account_value: Optional[str],
) -> Tuple[Dict[str, Any], Dict[str, List[str]], Optional[str], Optional[str]]:
    month_start, month_end = _month_bounds(selected_month)
    external_hours_service = _get_external_hours_service()

    external_data = external_hours_service.external_hours_for_month(month_start, month_end)
    subscription_data = external_hours_service.subscription_hours_for_month(month_start, month_end)

    sales_markets = _annotate_client_markets(external_data.get("markets", []), "projects")
    subscription_markets = _annotate_client_markets(subscription_data.get("markets", []), "subscriptions")

    filter_options = _collect_client_filter_options(sales_markets, subscription_markets)
    agreement_filter = _normalize_agreement_filter(agreement_value, filter_options["agreement_types"])
    account_filter = _normalize_account_filter(account_value, filter_options["account_types"])

    filtered = _apply_client_filters(sales_markets, subscription_markets, agreement_filter, account_filter)
    subscription_used_hours_series = external_hours_service.external_used_hours_series(selected_month.year)

    payload = {
        "client_external_hours": filtered["sales_markets"],
        "client_external_hours_all": sales_markets,
        "client_sales_summary": filtered["sales_summary"],
        "client_subscription_hours": filtered["subscription_markets"],
        "client_subscription_hours_all": subscription_markets,
        "client_subscription_summary": filtered["subscription_summary"],
        "client_subscription_top_clients": _merge_top_clients(
            filtered["subscription_top_clients"],
            filtered["sales_top_clients"],
        ),
        "client_subscription_used_hours_series": subscription_used_hours_series,
        "client_subscription_used_hours_year": selected_month.year,
        "client_pool_external_summary": _compute_pool_external_summary(
            filtered["sales_markets"],
            filtered["subscription_markets"],
        ),
    }

    return payload, filter_options, agreement_filter, account_filter


def _empty_client_dashboard_payload(
    selected_month: date,
) -> Tuple[Dict[str, Any], Dict[str, List[str]], Optional[str], Optional[str]]:
    """Return an empty client dashboard payload for error states."""
    zero_hours = _format_hours_display(0.0)
    zero_currency = _format_currency_display(0.0)
    payload = {
        "client_external_hours": [],
        "client_external_hours_all": [],
        "client_sales_summary": {
            "total_projects": 0,
            "total_external_hours": 0.0,
            "total_external_hours_display": zero_hours,
            "total_revenue_aed": 0.0,
            "total_revenue_aed_display": zero_currency,
            "total_invoices": 0,
        },
        "client_subscription_hours": [],
        "client_subscription_hours_all": [],
        "client_subscription_summary": {
            "total_subscriptions": 0,
            "total_monthly_hours": 0.0,
            "total_monthly_hours_display": zero_hours,
            "total_revenue_aed": 0.0,
            "total_revenue_aed_display": zero_currency,
            "total_subscription_used_hours": 0.0,
            "total_subscription_used_hours_display": zero_hours,
        },
        "client_subscription_top_clients": [],
        "client_subscription_used_hours_series": [],
        "client_subscription_used_hours_year": selected_month.year,
        "client_pool_external_summary": {
            "pools": [],
            "totals": {
                "projects": 0,
                "projects_display": "0",
                "used_hours": 0.0,
                "used_hours_display": zero_hours,
                "revenue": 0.0,
                "revenue_display": zero_currency,
            },
        },
    }
    filter_options = {"agreement_types": [], "account_types": []}
    return payload, filter_options, None, None


def _compute_pool_external_summary(
    sales_markets: Iterable[Mapping[str, Any]] | None,
    subscription_markets: Iterable[Mapping[str, Any]] | None,
) -> Dict[str, Any]:
    pool_lookup = {definition["slug"]: definition for definition in POOL_DEFINITIONS}
    pools: Dict[str, Dict[str, Any]] = {
        slug: {
            "slug": slug,
            "label": definition["label"],
            "projects": set(),
            "used_hours": 0.0,
            "sold_hours": 0.0,
            "revenue": 0.0,
            "order_keys": set(),
            "sold_order_keys": set(),
            "invoice_keys": set(),
        }
        for slug, definition in pool_lookup.items()
    }
    totals: Dict[str, Any] = {
        "projects": set(),
        "used_hours": 0.0,
        "sold_hours": 0.0,
        "revenue": 0.0,
        "order_keys": set(),
        "sold_order_keys": set(),
        "invoice_keys": set(),
    }

    for market in sales_markets or []:
        for project in market.get("projects", []) or []:
            slug = _infer_pool_from_sources(project.get("tags"), project.get("project_name"), market.get("market"))
            if not slug or slug not in pools:
                continue
            pool_state = pools[slug]

            project_id = project.get("project_id")
            if not isinstance(project_id, (int, str)):
                project_id = project.get("project_name") or project.get("name")
            identifier = f"sales::{project_id}" if project_id is not None else None
            if identifier is not None:
                pool_state["projects"].add(identifier)
                totals["projects"].add(identifier)

            external_hours = float(project.get("total_external_hours", 0.0) or 0.0)
            revenue_value = float(project.get("total_aed", 0.0) or 0.0)

            pool_state["used_hours"] += external_hours
            pool_state["sold_hours"] += external_hours
            pool_state["revenue"] += revenue_value

            totals["used_hours"] += external_hours
            totals["sold_hours"] += external_hours
            totals["revenue"] += revenue_value

    for market in subscription_markets or []:
        for subscription in market.get("subscriptions", []) or []:
            slug = _infer_pool_from_sources(subscription.get("tags"), subscription.get("project_name"), market.get("market"))
            if not slug or slug not in pools:
                continue
            pool_state = pools[slug]

            # Treat each subscription order as a distinct project for pool counts
            order_reference = subscription.get("order_reference") or subscription.get("project_name")
            identifier = f"subscription::{order_reference}" if order_reference else None
            if identifier is not None:
                pool_state["projects"].add(identifier)
                totals["projects"].add(identifier)

            order_reference = subscription.get("order_reference")
            order_key = (slug, order_reference or identifier)
            if order_key not in pool_state["order_keys"]:
                used_hours = float(subscription.get("subscription_used_hours", 0.0) or 0.0)
                pool_state["used_hours"] += used_hours
                totals["used_hours"] += used_hours
                pool_state["order_keys"].add(order_key)
                totals["order_keys"].add(order_key)

            sold_key = (slug, order_reference or identifier)
            if sold_key not in pool_state["sold_order_keys"]:
                monthly_hours = float(subscription.get("monthly_billable_hours", 0.0) or 0.0)
                pool_state["sold_hours"] += monthly_hours
                totals["sold_hours"] += monthly_hours
                pool_state["sold_order_keys"].add(sold_key)
                totals["sold_order_keys"].add(sold_key)

            invoice_reference = subscription.get("invoice_reference")
            invoice_key = (slug, order_reference, invoice_reference)
            if invoice_key not in pool_state["invoice_keys"]:
                revenue_value = float(subscription.get("aed_total", 0.0) or 0.0)
                pool_state["revenue"] += revenue_value
                totals["revenue"] += revenue_value
                pool_state["invoice_keys"].add(invoice_key)
                totals["invoice_keys"].add(invoice_key)

    total_project_count = len(totals["projects"])
    total_used_hours = totals["used_hours"]
    total_revenue = totals["revenue"]

    pool_cards = []
    for slug, state in pools.items():
        project_count = len(state["projects"])
        used_hours = state["used_hours"]
        revenue_value = state["revenue"]

        pool_cards.append(
            {
                "slug": slug,
                "label": pool_lookup[slug]["label"],
                "metrics": {
                    "projects": {
                        "value": project_count,
                        "display": f"{project_count:,}",
                        "total_display": f"{total_project_count:,}",
                        "ratio": (project_count / total_project_count) if total_project_count else 0.0,
                    },
                    "used_hours": {
                        "value": used_hours,
                        "display": _format_hours_display(used_hours),
                        "total_display": _format_hours_display(total_used_hours),
                        "ratio": (used_hours / total_used_hours) if total_used_hours else 0.0,
                    },
                    "revenue": {
                        "value": revenue_value,
                        "display": _format_currency_display(revenue_value),
                        "total_display": _format_currency_display(total_revenue),
                        "ratio": (revenue_value / total_revenue) if total_revenue else 0.0,
                    },
                },
            }
        )

    return {
        "pools": pool_cards,
        "totals": {
            "projects": total_project_count,
            "projects_display": f"{total_project_count:,}",
            "used_hours": total_used_hours,
            "used_hours_display": _format_hours_display(total_used_hours),
            "revenue": total_revenue,
            "revenue_display": _format_currency_display(total_revenue),
        },
    }

def _merge_top_clients(
    subscription_clients: Iterable[Mapping[str, Any]] | None,
    sales_clients: Iterable[Mapping[str, Any]] | None,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    combined: Dict[Tuple[Any, ...], Dict[str, Any]] = {}

    def _ingest(entry: Mapping[str, Any]) -> None:
        key, normalized_id, client_name, market_name = _normalize_client_key(
            entry.get("project_id"),
            entry.get("client_name"),
            entry.get("market"),
        )
        record = combined.setdefault(
            key,
            {
                "project_id": normalized_id,
                "client_name": client_name,
                "market": market_name,
                "total_revenue_aed": 0.0,
                "request_count": 0,
            },
        )
        revenue_delta = entry.get("total_revenue_aed", 0.0)
        if isinstance(revenue_delta, (int, float)):
            record["total_revenue_aed"] += float(revenue_delta)
        request_delta = entry.get("request_count", 0)
        if isinstance(request_delta, (int, float)):
            record["request_count"] += int(request_delta)

    for entry in subscription_clients or []:
        _ingest(entry)
    for entry in sales_clients or []:
        _ingest(entry)

    top_clients: List[Dict[str, Any]] = []
    for record in combined.values():
        total_value = float(record.get("total_revenue_aed", 0.0) or 0.0)
        record["total_revenue_aed"] = total_value
        record["total_revenue_aed_display"] = _format_aed_value(total_value)
        top_clients.append(record)

    top_clients.sort(
        key=lambda item: (
            -item["total_revenue_aed"],
            item["client_name"].lower(),
        )
    )
    return top_clients[:limit]


def _base_dashboard_state(selected_month: date) -> Dict[str, Any]:
    """Provide a minimal dashboard state when downstream services are unavailable."""
    client_payload, filter_options, _, _ = _empty_client_dashboard_payload(selected_month)
    zero_display = _format_hours_minutes(0.0)
    aggregates = {
        "planned": 0.0,
        "logged": 0.0,
        "available": 0.0,
        "max": 0.0,
        "display": {
            "planned": zero_display,
            "logged": zero_display,
            "available": zero_display,
        },
    }
    state: Dict[str, Any] = {
        "creatives": [],
        "stats": {"total": 0, "available": 0, "active": 0},
        "aggregates": aggregates,
        "pool_stats": _pool_stats([]),
        "client_filter_options": filter_options,
        "selected_agreement_type": "",
        "selected_account_type": "",
        "odoo_unavailable": True,
    }
    state.update(client_payload)
    return state


def _empty_dashboard_context(selected_month: date, error_message: str) -> Dict[str, Any]:
    """Compose the context for rendering the dashboard when Odoo is unreachable."""
    context = _base_dashboard_state(selected_month)
    context.update(
        {
            "month_options": _month_options(selected_month),
            "selected_month": selected_month.strftime("%Y-%m"),
            "readable_month": selected_month.strftime("%B %Y"),
            "odoo_error_message": error_message,
        }
    )
    return context


def _empty_utilization_summary() -> Dict[str, Any]:
    """Provide default utilization metrics when backend data cannot be loaded."""
    zero_hours = _format_hours_display(0.0)
    return {
        "available_creatives": 0,
        "total_available_hours": 0.0,
        "total_planned_hours": 0.0,
        "total_logged_hours": 0.0,
        "total_external_used_hours": 0.0,
        "available_hours_display": zero_hours,
        "planned_hours_display": zero_hours,
        "logged_hours_display": zero_hours,
        "external_used_hours_display": zero_hours,
        "pool_stats": [],
    }
