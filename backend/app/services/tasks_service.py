"""Tasks statistics service for creative dashboard."""
from __future__ import annotations

from calendar import monthrange
import re
from datetime import date
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from .comparison_service import ComparisonService


class TasksService:
    """Calculate task statistics from planning slots."""

    def __init__(self, comparison_service: ComparisonService):
        self.comparison_service = comparison_service
        self.planning_service = getattr(comparison_service, "planning_service", None)

    @classmethod
    def from_comparison_service(cls, comparison_service: ComparisonService) -> "TasksService":
        """Create a TasksService instance from a ComparisonService."""
        return cls(comparison_service)

    def _extract_agreement_tokens(self, raw: Any) -> list[str]:
        if raw is None:
            return []
        if isinstance(raw, str):
            stripped = raw.strip()
            if not stripped:
                return []
            parts = re.split(r"[,/&|]+", stripped)
            return [part.strip() for part in parts if part.strip()]
        if isinstance(raw, (list, tuple, set)):
            tokens: list[str] = []
            for item in raw:
                tokens.extend(self._extract_agreement_tokens(item))
            return tokens
        return []

    def _categorize_agreement(self, agreement_type: Any, tags: Any = None) -> str:
        """Categorize into ad-hoc, framework, or retainer using labels and tags."""
        tokens = self._extract_agreement_tokens(agreement_type)
        if isinstance(tags, (list, tuple, set)):
            for tag in tags:
                tokens.extend(self._extract_agreement_tokens(tag))

        normalized = [token.lower() for token in tokens if token]
        for token in normalized:
            if any(key in token for key in ("retainer", "subscription", "subscr")):
                return "retainer"
        for token in normalized:
            if "framework" in token:
                return "framework"
        for token in normalized:
            if "ad-hoc" in token or "adhoc" in token or "ad hoc" in token:
                return "ad-hoc"

        return "other"

    def calculate_tasks_statistics(
        self,
        creatives: Sequence[Mapping[str, Any]],
        month_start: date,
        month_end: date,
        available_creatives: int,
    ) -> Dict[str, Any]:
        """Calculate task statistics from planning slots for the selected month."""
        current_tasks = self._tasks_for_month(creatives, month_start, month_end)
        summary = self._summarize_tasks(current_tasks, available_creatives)

        previous_bounds = self._previous_month_bounds(month_start)
        if previous_bounds and self.planning_service:
            prev_start, prev_end = previous_bounds
            prev_tasks = self._tasks_for_month(creatives, prev_start, prev_end)
            prev_summary = self._summarize_tasks(prev_tasks, available_creatives) # Use summarize to get total_tasks too
            
            previous_total = prev_summary["total"]
            previous_total_tasks = prev_summary["total_tasks"]
            
            comparison = self._calculate_comparison(summary["total"], previous_total)
            if comparison:
                summary["comparison"] = comparison
                summary["previous_total"] = previous_total
            
            # Add comparison for total_tasks
            tasks_comparison = self._calculate_comparison(summary["total_tasks"], previous_total_tasks)
            if tasks_comparison:
                summary["tasks_comparison"] = tasks_comparison
                summary["previous_total_tasks"] = previous_total_tasks

        return summary

    def _summarize_tasks(
        self,
        tasks: Sequence[Mapping[str, Any]],
        available_creatives: int,
    ) -> Dict[str, Any]:
        adhoc = 0
        framework = 0
        retainer = 0
        market_counts: Dict[str, int] = {}
        project_ids: set[int] = set()
        all_parent_tasks: set[str] = set()

        for task in tasks:
            project_id = task.get("project_id")
            if isinstance(project_id, int) and project_id > 0:
                project_ids.add(project_id)
            
            # Aggregate parent tasks
            parent_tasks = task.get("parent_tasks")
            if isinstance(parent_tasks, list):
                for pt in parent_tasks:
                    if pt:
                        all_parent_tasks.add(pt)

            category = self._categorize_agreement(task.get("agreement_type"), task.get("tags"))
            if category == "ad-hoc":
                adhoc += 1
            elif category == "framework":
                framework += 1
            elif category == "retainer":
                retainer += 1

            market_label = str(task.get("market") or "").strip()
            if market_label:
                market_counts[market_label] = market_counts.get(market_label, 0) + 1

        total = len(tasks)
        total_tasks = len(all_parent_tasks)
        average_per_creator = round(total / available_creatives, 2) if available_creatives > 0 else 0.0
        average_tasks_per_creator = round(total_tasks / available_creatives, 2) if available_creatives > 0 else 0.0

        return {
            "total": total,
            "total_tasks": total_tasks,
            "adhoc": adhoc,
            "framework": framework,
            "retainer": retainer,
            "average_per_creator": average_per_creator,
            "average_tasks_per_creator": average_tasks_per_creator,
            "by_market": market_counts,
            "project_ids": sorted(project_ids),
            "parent_task_names": sorted(all_parent_tasks),  # Add sorted list of parent task names for tooltip
            "tasks": list(tasks),
        }

    def _tasks_for_month(
        self,
        creatives: Sequence[Mapping[str, Any]],
        month_start: date,
        month_end: date,
    ) -> Sequence[Mapping[str, Any]]:
        if not self.planning_service:
            return []
        return self.planning_service.tasks_for_month(creatives, month_start, month_end)

    def _previous_month_bounds(self, current_month_start: date) -> Optional[Tuple[date, date]]:
        """Return the start and end dates for the previous month."""
        if current_month_start.month == 1:
            prev_month = date(current_month_start.year - 1, 12, 1)
        else:
            prev_month = date(current_month_start.year, current_month_start.month - 1, 1)

        _, last_day = monthrange(prev_month.year, prev_month.month)
        prev_end = date(prev_month.year, prev_month.month, last_day)
        return prev_month, prev_end

    def _calculate_comparison(self, current: int, previous: int) -> Optional[Dict[str, Any]]:
        """Calculate comparison between current and previous month totals."""
        if previous == 0:
            if current > 0:
                return {"change_percentage": 100.0, "trend": "up"}
            return None

        change = ((current - previous) / previous) * 100
        trend = "up" if change >= 0 else "down"

        return {
            "change_percentage": abs(change),
            "trend": trend,
        }
