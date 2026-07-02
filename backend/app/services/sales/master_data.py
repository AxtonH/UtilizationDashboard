"""Odoo master-data fetch + per-instance caches and label accessors."""
from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple
import re
from ...integrations.odoo_client import OdooClient


class MasterDataMixin:
    """Odoo master-data fetch + per-instance caches and label accessors."""

    def _fetch_projects(self, project_ids: Iterable[int]) -> Dict[int, Dict[str, Any]]:
        ids = [project_id for project_id in project_ids if isinstance(project_id, int)]
        if not ids:
            return {}
        
        missing = [pid for pid in ids if pid not in self._project_cache]
        if missing:
            fields = ["x_studio_market_2", "x_studio_agreement_type_1", "tag_ids", "name"]
            records = self.odoo_client.read("project.project", missing, fields)
            for record in records:
                if isinstance(record.get("id"), int):
                    self._project_cache[record["id"]] = record
        
        project_map = {pid: self._project_cache[pid] for pid in ids if pid in self._project_cache}
        
        # Fetch related tags and agreement types
        tag_ids = set()
        agreement_ids = set()
        for record in project_map.values():
            for tag_id in record.get("tag_ids") or []:
                if isinstance(tag_id, int):
                    tag_ids.add(tag_id)
            for ag_id in record.get("x_studio_agreement_type_1") or []:
                if isinstance(ag_id, int):
                    agreement_ids.add(ag_id)
        
        agreement_map = self._fetch_agreement_types(agreement_ids) if agreement_ids else {}
        tag_names = self._fetch_project_tags(tag_ids) if tag_ids else {}
        
        # Enrich projects with names
        for project in project_map.values():
            ids = project.get("tag_ids") or []
            project["tag_names"] = [tag_names.get(tid, f"Tag {tid}") for tid in ids if isinstance(tid, int)]
            
            raw_agreements = project.get("x_studio_agreement_type_1") or []
            agreement_names = [agreement_map.get(aid, f"Agreement {aid}") for aid in raw_agreements if isinstance(aid, int)]
            project["agreement_type_names"] = [name for name in agreement_names if name]
            
        return project_map

    def _fetch_agreement_types(self, type_ids: Iterable[int]) -> Dict[int, str]:
        ids = [tid for tid in type_ids if isinstance(tid, int)]
        if not ids:
            return {}
        
        missing = [tid for tid in ids if tid not in self._agreement_cache]
        if missing:
            records = self.odoo_client.read("x_agreement_type", missing, ["display_name", "x_name"])
            for record in records:
                tid = record.get("id")
                if isinstance(tid, int):
                    name = record.get("display_name") or record.get("x_name")
                    self._agreement_cache[tid] = self._safe_str(name, default=f"Agreement {tid}")
        
        return {tid: self._agreement_cache[tid] for tid in ids if tid in self._agreement_cache}

    def _fetch_project_tags(self, tag_ids: Iterable[int]) -> Dict[int, str]:
        ids = [tid for tid in tag_ids if isinstance(tid, int)]
        if not ids:
            return {}
        
        missing = [tid for tid in ids if tid not in self._tag_cache]
        if missing:
            tags = self.odoo_client.read("project.tags", missing, ["name"])
            for tag in tags:
                tid = tag.get("id")
                if isinstance(tid, int):
                    self._tag_cache[tid] = str(tag.get("name", ""))
        
        return {tid: self._tag_cache.get(tid, f"Tag {tid}") for tid in ids if tid in self._tag_cache}

    def _market_label(self, project: Optional[Dict[str, Any]]) -> str:
        if not project:
            return "Unassigned Market"
        raw = project.get("x_studio_market_2")
        if isinstance(raw, (list, tuple)) and len(raw) >= 2:
            return self._safe_str(raw[1], default="Unassigned Market")
        return self._safe_str(raw, default="Unassigned Market")

    def _format_agreement_type(self, project: Optional[Dict[str, Any]]) -> str:
        if not project:
            return "Unknown"
        names = project.get("agreement_type_names")
        if isinstance(names, list):
            cleaned = [self._safe_str(name).strip() for name in names if isinstance(name, str)]
            cleaned = [name for name in cleaned if name]
            if cleaned:
                return ", ".join(cleaned)
        return "Unknown"

    def _project_tags(self, project: Optional[Dict[str, Any]]) -> List[str]:
        if not project:
            return []
        names = project.get("tag_names")
        if isinstance(names, list):
            return [str(name) for name in names if isinstance(name, str)]
        return []

    def _safe_str(self, value: Any, *, default: str = "") -> str:
        if value is None:
            return default
        return str(value).strip() or default

    def _previous_month_bounds(self, current_month_start: date) -> Optional[Tuple[date, date]]:
        """Return the start and end dates for the previous month.
        
        Args:
            current_month_start: First day of current month
            
        Returns:
            Tuple of (prev_month_start, prev_month_end) or None
        """
        if current_month_start.month == 1:
            prev_month = date(current_month_start.year - 1, 12, 1)
        else:
            prev_month = date(current_month_start.year, current_month_start.month - 1, 1)
        
        _, last_day = monthrange(prev_month.year, prev_month.month)
        prev_end = date(prev_month.year, prev_month.month, last_day)
        
        return prev_month, prev_end

    def _calculate_comparison(self, current: float, previous: float) -> Optional[Dict[str, Any]]:
        """Calculate comparison between current and previous month values.
        
        Args:
            current: Current month value (can be int or float)
            previous: Previous month value (can be int or float)
            
        Returns:
            Dictionary with change_percentage and trend, or None if no comparison
        """
        # Handle zero previous safely
        if previous == 0:
            if current > 0:
                return {"change_percentage": 100.0, "trend": "up"}
            if current == 0:
                return {"change_percentage": 0.0, "trend": "flat"}
            # Negative current not expected, but treat as down
            return {"change_percentage": 100.0, "trend": "down"}

        change = ((current - previous) / previous) * 100
        change_pct = abs(change)

        # Treat near-zero change as flat to avoid misleading arrows
        if abs(change_pct) < 1e-6:
            return {"change_percentage": 0.0, "trend": "flat"}

        trend = "up" if change > 0 else "down"

        return {
            "change_percentage": change_pct,
            "trend": trend,
        }
