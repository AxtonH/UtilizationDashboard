"""Store which ramp-period new joiners count toward utilization (Supabase).

A row in ``new_joiner_inclusions`` means that employee's hours ARE included in
utilization while they are inside their 3-month new-joiner ramp. No row means
the default: ramp hours excluded. Rows are harmless once the ramp ends, so
they are not cleaned up automatically.
"""
from __future__ import annotations

import os
from typing import Set

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


class NewJoinerInclusionsService:
    """CRUD for new_joiner_inclusions."""

    def __init__(self, supabase_url: str, supabase_key: str) -> None:
        self.supabase_url = supabase_url.rstrip("/")
        self.supabase_key = supabase_key
        self.table_name = "new_joiner_inclusions"

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
            raise RuntimeError("supabase-py or postgrest is required for NewJoinerInclusionsService")

    @classmethod
    def from_env(cls) -> "NewJoinerInclusionsService":
        url = os.getenv("SUPABASE_URL", "").strip()
        key = os.getenv("SUPABASE_KEY", "").strip()
        if not url or not key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_KEY are required")
        return cls(url, key)

    def _table(self):
        if POSTGREST_AVAILABLE:
            return self.client.from_(self.table_name)
        return self.client.table(self.table_name)

    def get_included_ids(self) -> Set[int]:
        """Employee ids whose ramp hours should count toward utilization."""
        try:
            response = self._table().select("employee_id").execute()
            return {
                row["employee_id"]
                for row in (response.data or [])
                if isinstance(row.get("employee_id"), int)
            }
        except Exception as e:
            print(f"Error listing new joiner inclusions: {e}")
            return set()

    def set_inclusion(self, employee_id: int, included: bool) -> bool:
        """Persist the toggle: included=True inserts the row, False removes it."""
        if not isinstance(employee_id, int):
            return False
        try:
            if included:
                self._table().upsert({"employee_id": employee_id}).execute()
            else:
                self._table().delete().eq("employee_id", employee_id).execute()
            return True
        except Exception as e:
            print(f"Error saving new joiner inclusion for {employee_id}: {e}")
            return False
