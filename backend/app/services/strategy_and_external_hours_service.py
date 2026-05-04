"""Manual Strategy& external hours (per calendar month) in Supabase for sales dashboard totals."""
from __future__ import annotations

import os
from calendar import monthrange
from datetime import date
from typing import Any, Dict, List, Set, Tuple

try:
    from postgrest import SyncPostgrestClient

    POSTGREST_AVAILABLE = True
except ImportError:
    POSTGREST_AVAILABLE = False
    SyncPostgrestClient = None  # type: ignore

try:
    from supabase import create_client

    SUPABASE_CLIENT_AVAILABLE = True
except ImportError:
    SUPABASE_CLIENT_AVAILABLE = False
    create_client = None  # type: ignore


def _month_overlaps_range(year: int, month: int, range_start: date, range_end: date) -> bool:
    """True if calendar month ``year``/``month`` overlaps ``[range_start, range_end]`` (inclusive)."""
    first = date(year, month, 1)
    last = date(year, month, monthrange(year, month)[1])
    return first <= range_end and last >= range_start


class StrategyAndExternalHoursService:
    """CRUD for strategy_and_external_hours."""

    def __init__(self, supabase_url: str, supabase_key: str) -> None:
        self.supabase_url = supabase_url.rstrip("/")
        self.supabase_key = supabase_key
        self.table_name = "strategy_and_external_hours"

        if POSTGREST_AVAILABLE and SyncPostgrestClient is not None:
            rest_url = f"{self.supabase_url}/rest/v1"
            self.client = SyncPostgrestClient(
                base_url=rest_url,
                schema="public",
                headers={
                    "apikey": self.supabase_key,
                    "Authorization": f"Bearer {self.supabase_key}",
                    "Content-Type": "application/json",
                },
            )
        elif SUPABASE_CLIENT_AVAILABLE and create_client:
            self.client = create_client(supabase_url, supabase_key)
        else:
            raise RuntimeError("supabase-py or postgrest is required for StrategyAndExternalHoursService")

    @classmethod
    def from_env(cls) -> "StrategyAndExternalHoursService":
        url = os.getenv("SUPABASE_URL", "").strip()
        key = os.getenv("SUPABASE_KEY", "").strip()
        if not url or not key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_KEY are required")
        return cls(url, key)

    def list_all(self) -> List[Dict[str, Any]]:
        """Return all rows (year, month, external_hours_sold, external_hours_used), sorted newest first."""
        try:
            if POSTGREST_AVAILABLE:
                response = (
                    self.client.from_(self.table_name)
                    .select("year,month,external_hours_sold,external_hours_used")
                    .execute()
                )
                rows = list(response.data or [])
            else:
                response = self.client.table(self.table_name).select(
                    "year,month,external_hours_sold,external_hours_used"
                ).execute()
                rows = list(response.data or [])
        except Exception as e:
            print(f"Error listing strategy and external hours: {e}")
            return []

        def sort_key(r: Dict[str, Any]) -> Tuple[int, int]:
            y = r.get("year")
            m = r.get("month")
            if isinstance(y, int) and isinstance(m, int):
                return (y, m)
            return (0, 0)

        rows.sort(key=sort_key, reverse=True)
        return rows

    def sum_for_date_range(self, range_start: date, range_end: date) -> Tuple[float, float]:
        """Sum sold/used for stored months that overlap the inclusive dashboard period."""
        sold_total = 0.0
        used_total = 0.0
        for row in self.list_all():
            y = row.get("year")
            m = row.get("month")
            if not isinstance(y, int) or not isinstance(m, int):
                continue
            if not _month_overlaps_range(y, m, range_start, range_end):
                continue
            try:
                sold_total += float(row.get("external_hours_sold") or 0)
                used_total += float(row.get("external_hours_used") or 0)
            except (TypeError, ValueError):
                continue
        return sold_total, used_total

    def _delete_all_rows(self) -> bool:
        try:
            if POSTGREST_AVAILABLE:
                existing = self.client.from_(self.table_name).select("year,month").execute()
                for r in existing.data or []:
                    y, m = r.get("year"), r.get("month")
                    if isinstance(y, int) and isinstance(m, int):
                        (
                            self.client.from_(self.table_name)
                            .delete()
                            .eq("year", y)
                            .eq("month", m)
                            .execute()
                        )
            else:
                existing = self.client.table(self.table_name).select("year,month").execute()
                for r in existing.data or []:
                    y, m = r.get("year"), r.get("month")
                    if isinstance(y, int) and isinstance(m, int):
                        self.client.table(self.table_name).delete().eq("year", y).eq("month", m).execute()
            return True
        except Exception as e:
            print(f"Error deleting strategy and external hours: {e}")
            return False

    def replace_all(
        self,
        rows: List[Dict[str, Any]],
        *,
        allow_empty_replace: bool = False,
    ) -> bool:
        """Replace table with validated rows. Each item: year, month, external_hours_sold, external_hours_used."""
        clean: List[Dict[str, Any]] = []
        seen: Set[Tuple[int, int]] = set()
        for item in rows:
            if not isinstance(item, dict):
                continue
            y = item.get("year")
            m = item.get("month")
            try:
                yi = int(y)
                mi = int(m)
            except (TypeError, ValueError):
                continue
            if yi < 2000 or yi > 2100 or mi < 1 or mi > 12:
                continue
            if (yi, mi) in seen:
                continue
            seen.add((yi, mi))
            try:
                sold = float(item.get("external_hours_sold") or 0)
                used = float(item.get("external_hours_used") or 0)
            except (TypeError, ValueError):
                continue
            if sold < 0 or sold > 10000000 or used < 0 or used > 10000000:
                continue
            clean.append(
                {
                    "year": yi,
                    "month": mi,
                    "external_hours_sold": round(sold, 2),
                    "external_hours_used": round(used, 2),
                }
            )

        if not clean:
            if allow_empty_replace:
                return self._delete_all_rows()
            return True

        try:
            if POSTGREST_AVAILABLE:
                existing = self.client.from_(self.table_name).select("year,month").execute()
                for r in existing.data or []:
                    y, m = r.get("year"), r.get("month")
                    if isinstance(y, int) and isinstance(m, int):
                        (
                            self.client.from_(self.table_name)
                            .delete()
                            .eq("year", y)
                            .eq("month", m)
                            .execute()
                        )
                self.client.from_(self.table_name).insert(clean).execute()
            else:
                existing = self.client.table(self.table_name).select("year,month").execute()
                for r in existing.data or []:
                    y, m = r.get("year"), r.get("month")
                    if isinstance(y, int) and isinstance(m, int):
                        self.client.table(self.table_name).delete().eq("year", y).eq("month", m).execute()
                self.client.table(self.table_name).insert(clean).execute()
            return True
        except Exception as e:
            print(f"Error replacing strategy and external hours: {e}")
            return False
