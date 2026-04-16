"""Store per-employee monthly hour overrides in Supabase (dashboard availability)."""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

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


class CreativeHourAdjustmentsService:
    """CRUD for creative_hour_adjustments."""

    def __init__(self, supabase_url: str, supabase_key: str) -> None:
        self.supabase_url = supabase_url.rstrip("/")
        self.supabase_key = supabase_key
        self.table_name = "creative_hour_adjustments"

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
            raise RuntimeError("supabase-py or postgrest is required for CreativeHourAdjustmentsService")

    @classmethod
    def from_env(cls) -> "CreativeHourAdjustmentsService":
        url = os.getenv("SUPABASE_URL", "").strip()
        key = os.getenv("SUPABASE_KEY", "").strip()
        if not url or not key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_KEY are required")
        return cls(url, key)

    def list_all(self) -> List[Dict[str, Any]]:
        """Return all rows as dicts with employee_id and monthly_hours."""
        try:
            if POSTGREST_AVAILABLE:
                response = self.client.from_(self.table_name).select("employee_id,monthly_hours").execute()
                return list(response.data or [])
            response = self.client.table(self.table_name).select("employee_id,monthly_hours").execute()
            return list(response.data or [])
        except Exception as e:
            print(f"Error listing creative hour adjustments: {e}")
            return []

    def get_adjustments_map(self) -> Dict[int, float]:
        """employee_id -> monthly_hours for dashboard enrichment."""
        out: Dict[int, float] = {}
        for row in self.list_all():
            eid = row.get("employee_id")
            mh = row.get("monthly_hours")
            if isinstance(eid, int) and mh is not None:
                try:
                    out[eid] = float(mh)
                except (TypeError, ValueError):
                    continue
        return out

    def _delete_all_rows(self) -> bool:
        """Remove every row (used for explicit clear)."""
        try:
            if POSTGREST_AVAILABLE:
                existing = self.client.from_(self.table_name).select("employee_id").execute()
                for r in existing.data or []:
                    oid = r.get("employee_id")
                    if isinstance(oid, int):
                        self.client.from_(self.table_name).delete().eq("employee_id", oid).execute()
            else:
                existing = self.client.table(self.table_name).select("employee_id").execute()
                for r in existing.data or []:
                    oid = r.get("employee_id")
                    if isinstance(oid, int):
                        self.client.table(self.table_name).delete().eq("employee_id", oid).execute()
            return True
        except Exception as e:
            print(f"Error deleting creative hour adjustments: {e}")
            return False

    def replace_all(
        self,
        rows: List[Tuple[int, float]],
        *,
        allow_empty_replace: bool = False,
    ) -> bool:
        """Replace table contents with validated (employee_id, monthly_hours) pairs.

        If validation yields no rows: no database writes unless ``allow_empty_replace`` is True
        (meaning the client sent an explicit empty list to clear all rows).
        """
        clean: List[Dict[str, Any]] = []
        for eid, hrs in rows:
            if not isinstance(eid, int):
                continue
            try:
                h = float(hrs)
            except (TypeError, ValueError):
                continue
            if h < 0 or h > 400:
                continue
            clean.append({"employee_id": eid, "monthly_hours": round(h, 2)})

        if not clean:
            if allow_empty_replace:
                return self._delete_all_rows()
            return True

        try:
            if POSTGREST_AVAILABLE:
                existing = self.client.from_(self.table_name).select("employee_id").execute()
                for r in existing.data or []:
                    oid = r.get("employee_id")
                    if isinstance(oid, int):
                        self.client.from_(self.table_name).delete().eq("employee_id", oid).execute()
                self.client.from_(self.table_name).insert(clean).execute()
            else:
                existing = self.client.table(self.table_name).select("employee_id").execute()
                for r in existing.data or []:
                    oid = r.get("employee_id")
                    if isinstance(oid, int):
                        self.client.table(self.table_name).delete().eq("employee_id", oid).execute()
                self.client.table(self.table_name).insert(clean).execute()
            return True
        except Exception as e:
            print(f"Error replacing creative hour adjustments: {e}")
            return False
