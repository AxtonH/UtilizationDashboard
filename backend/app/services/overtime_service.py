"""Overtime statistics service for creative dashboard."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional, Sequence

from ..config import OdooSettings
from ..integrations.odoo_client import OdooClient


def format_hours(hours: float) -> str:
    """Format an hours value as a compact display string (e.g. 7.5h, 45m)."""
    if hours == 0:
        return "0h"
    if hours < 1:
        minutes = int(hours * 60)
        return f"{minutes}m"
    if hours == int(hours):
        return f"{int(hours)}h"
    return f"{hours:.1f}h"


def attach_overtime_to_creatives(
    creatives: Sequence[Dict[str, Any]],
    overtime_stats: Optional[Dict[str, Any]],
) -> None:
    """Set per-creative overtime_hours(+display) from computed overtime stats.

    Mutates the creative dicts in place so both the SSR template and the JSON
    API expose the same fields without recomputing the match.
    """
    totals: Dict[int, float] = {}
    for request in (overtime_stats or {}).get("requests", []):
        creative_id = request.get("creative_id")
        if isinstance(creative_id, int):
            totals[creative_id] = totals.get(creative_id, 0.0) + float(request.get("hours") or 0.0)

    for creative in creatives:
        creative_id = creative.get("id")
        hours = totals.get(creative_id, 0.0) if isinstance(creative_id, int) else 0.0
        creative["overtime_hours"] = hours
        creative["overtime_hours_display"] = format_hours(hours)


def _normalize_name(name: str) -> str:
    """Lowercase, strip, and collapse internal whitespace for comparison."""
    if not name:
        return ""
    return " ".join(name.lower().split())


def _extract_owner_id(owner_field: Any) -> Optional[int]:
    """Extract the res.users id from an Odoo many2one value ([id, name])."""
    if (
        isinstance(owner_field, (list, tuple))
        and owner_field
        and isinstance(owner_field[0], int)
    ):
        return owner_field[0]
    return None


def _extract_owner_name(owner_field: Any) -> Optional[str]:
    """Extract the display name from an Odoo many2one value ([id, name])."""
    if not owner_field:
        return None
    if isinstance(owner_field, (list, tuple)) and len(owner_field) >= 2:
        return str(owner_field[1])
    if isinstance(owner_field, str):
        return owner_field
    return None


class _CreativeMatcher:
    """Resolves approval-request owners to creative employees.

    Primary strategy is an exact join on the shared res.users id
    (``hr.employee.user_id`` == ``approval.request.request_owner_id``).
    Fuzzy name matching remains only as a fallback for creatives with no
    linked user account, so a name similarity can never override the ID
    join. Fuzzy results are memoized per owner name because the same owner
    typically appears on many requests in a month.
    """

    def __init__(self, creatives: Sequence[Dict[str, Any]]):
        self._by_user_id: Dict[int, int] = {}
        # Normalized name -> creative id, only for creatives without user_id.
        self._fallback_names: Dict[str, int] = {}
        self._fuzzy_cache: Dict[str, Optional[int]] = {}

        for creative in creatives:
            creative_id = creative.get("id")
            if not isinstance(creative_id, int):
                continue
            user_id = creative.get("user_id")
            if isinstance(user_id, int):
                self._by_user_id[user_id] = creative_id
                continue
            name = creative.get("name")
            if isinstance(name, str):
                normalized = _normalize_name(name)
                if normalized:
                    self._fallback_names[normalized] = creative_id

    def resolve(self, owner_id: Optional[int], owner_name: Optional[str]) -> Optional[int]:
        """Return the matched creative id, or None if the owner is not a creative."""
        if owner_id is not None:
            creative_id = self._by_user_id.get(owner_id)
            if creative_id is not None:
                return creative_id
        return self._resolve_by_name(owner_name)

    def _resolve_by_name(self, owner_name: Optional[str]) -> Optional[int]:
        if not owner_name or not self._fallback_names:
            return None
        normalized = _normalize_name(owner_name)
        if not normalized:
            return None
        if normalized in self._fuzzy_cache:
            return self._fuzzy_cache[normalized]
        result = self._fuzzy_match(normalized)
        self._fuzzy_cache[normalized] = result
        return result

    def _fuzzy_match(self, normalized_owner: str) -> Optional[int]:
        # Strategy 1: exact match after normalization.
        exact = self._fallback_names.get(normalized_owner)
        if exact is not None:
            return exact

        # Strategy 2: owner's first and last name both appear, in order,
        # inside a creative's full name. Handles short display names vs
        # long HR legal names (e.g. "Farah Hdaib" vs "Farah Mohammad SH. Hdaib").
        parts = normalized_owner.split()
        if len(parts) >= 2:
            first, last = parts[0], parts[-1]
            for candidate, creative_id in self._fallback_names.items():
                first_idx = candidate.find(first)
                if first_idx == -1:
                    continue
                last_idx = candidate.find(last)
                if last_idx != -1 and first_idx < last_idx:
                    return creative_id

        # Strategy 3: a creative's full name contained in the owner name.
        for candidate, creative_id in self._fallback_names.items():
            if candidate in normalized_owner:
                return creative_id

        return None


class OvertimeService:
    """Calculate overtime statistics from approval requests."""

    def __init__(self, client: OdooClient):
        self.client = client

    @classmethod
    def from_settings(cls, settings: OdooSettings) -> "OvertimeService":
        """Create an OvertimeService instance from Odoo settings."""
        return cls(OdooClient(settings))

    def calculate_overtime_statistics(
        self,
        month_start: date,
        month_end: date,
        creatives: Optional[Sequence[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Calculate overtime statistics for a given month.

        Requests are attributed to creatives by joining the request owner's
        res.users id against each employee's ``user_id``; name matching is
        used only for creatives with no linked user (see _CreativeMatcher).

        Args:
            month_start: Start date of the month
            month_end: End date of the month
            creatives: Optional list of creatives to filter overtime by. If provided,
                      only overtime requests from these creatives will be included.

        Returns:
            Dictionary with total overtime hours and top projects
        """
        start_dt = datetime.combine(month_start, datetime.min.time())
        end_dt = datetime.combine(month_end + timedelta(days=1), datetime.min.time())

        domain = [
            ("date_start", ">=", start_dt.isoformat(sep=" ")),
            ("date_start", "<", end_dt.isoformat(sep=" ")),
            ("request_status", "=", "approved"),
        ]

        fields = ["id", "x_studio_hours", "x_studio_project", "date_start", "request_owner_id"]

        overtime_requests = []
        try:
            for batch in self.client.search_read_chunked(
                "approval.request",
                domain=domain,
                fields=fields,
                order="date_start asc, id asc",
            ):
                overtime_requests.extend(batch)
        except Exception as e:
            # Log error and return empty result
            print(f"Error fetching overtime requests: {e}")
            return {
                "total_hours": 0.0,
                "total_hours_display": "0h",
                "top_projects": [],
                "requests": [],  # Include empty requests array for consistency
            }

        matcher = _CreativeMatcher(creatives) if creatives else None

        # Process requests and match to creatives
        processed_requests = []

        for request in overtime_requests:
            owner_field = request.get("request_owner_id")
            request_owner = _extract_owner_name(owner_field)
            matched_creative_id = None

            if matcher is not None:
                matched_creative_id = matcher.resolve(
                    _extract_owner_id(owner_field), request_owner
                )
                # Only include requests attributed to a creative retrieved from Odoo
                if matched_creative_id is None:
                    continue

            hours = self._safe_float(request.get("x_studio_hours"))
            if hours <= 0:
                continue

            # Group by project
            project_field = request.get("x_studio_project")
            if isinstance(project_field, (list, tuple)) and len(project_field) >= 2:
                project_name = str(project_field[1])
            else:
                project_name = "Unassigned Project"

            date_start = request.get("date_start")
            processed_requests.append({
                "hours": hours,
                "date": str(date_start)[:10] if date_start else None,
                "project_name": project_name,
                "request_owner": request_owner,
                "creative_id": matched_creative_id,
            })

        # Calculate statistics from all matched requests
        total_hours = sum(req["hours"] for req in processed_requests)
        project_hours: Dict[str, float] = {}
        project_contributors: Dict[str, set[str]] = {}

        for req in processed_requests:
            project_name = req["project_name"]
            project_hours[project_name] = project_hours.get(project_name, 0.0) + req["hours"]

            contributor = req.get("request_owner")
            if contributor:
                if project_name not in project_contributors:
                    project_contributors[project_name] = set()
                project_contributors[project_name].add(contributor)

        # Get top 5 projects
        top_projects = sorted(
            [
                {
                    "project_name": name,
                    "hours": hours,
                    "hours_display": self._format_hours(hours),
                    "contributors": sorted(list(project_contributors.get(name, set())))
                }
                for name, hours in project_hours.items()
            ],
            key=lambda x: x["hours"],
            reverse=True,
        )[:5]

        return {
            "total_hours": total_hours,
            "total_hours_display": self._format_hours(total_hours),
            "top_projects": top_projects,
            "requests": processed_requests,  # Include individual requests for client-side filtering
        }

    def _safe_float(self, value: Any) -> float:
        """Safely convert value to float."""
        if value is None:
            return 0.0
        try:
            return float(value)
        except (ValueError, TypeError):
            return 0.0

    def _format_hours(self, hours: float) -> str:
        """Format hours as a string."""
        return format_hours(hours)
