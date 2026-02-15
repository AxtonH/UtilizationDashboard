"""Supabase cache service for monthly utilization data."""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

try:
    from postgrest import SyncPostgrestClient
    POSTGREST_AVAILABLE = True
    SUPABASE_CLIENT_AVAILABLE = False
except ImportError:
    POSTGREST_AVAILABLE = False
    try:
        from supabase import create_client, Client
        SUPABASE_CLIENT_AVAILABLE = True
        POSTGREST_AVAILABLE = False
    except Exception:
        SUPABASE_CLIENT_AVAILABLE = False
        Client = None  # type: ignore
        create_client = None  # type: ignore


class UtilizationCacheService:
    """Service for caching monthly utilization data per creative in Supabase."""

    def __init__(self, supabase_url: str, supabase_key: str):
        """Initialize the Supabase client.
        
        Args:
            supabase_url: Your Supabase project URL
            supabase_key: Your Supabase service role key
        """
        self.supabase_url = supabase_url.rstrip('/')
        self.supabase_key = supabase_key
        self.table_name = "monthly_utilization_cache"
        
        # Use PostgREST directly if available (Python 3.13 compatible)
        if POSTGREST_AVAILABLE:
            rest_url = f"{self.supabase_url}/rest/v1"
            self.client = SyncPostgrestClient(
                base_url=rest_url,
                schema="public",
                headers={
                    "apikey": self.supabase_key,
                    "Authorization": f"Bearer {self.supabase_key}",
                    "Content-Type": "application/json",
                }
            )
        elif SUPABASE_CLIENT_AVAILABLE and create_client:
            try:
                self.client = create_client(supabase_url, supabase_key)
            except Exception as e:
                raise RuntimeError(
                    f"Failed to initialize Supabase client: {e}. "
                    f"Check your SUPABASE_URL and SUPABASE_KEY environment variables."
                ) from e
        else:
            raise RuntimeError(
                "supabase-py or postgrest is not available. "
                "Install it with: pip install supabase"
            )

    @classmethod
    def from_env(cls) -> UtilizationCacheService:
        """Create a UtilizationCacheService instance from environment variables.
        
        Requires:
            SUPABASE_URL: Your Supabase project URL
            SUPABASE_KEY: Your Supabase service role key
        """
        url = os.getenv("SUPABASE_URL", "").strip()
        key = os.getenv("SUPABASE_KEY", "").strip()
        if not url or not key:
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_KEY environment variables are required"
            )
        return cls(url, key)

    def get_month_data(
        self, year: int, month: int
    ) -> List[Dict[str, Any]]:
        """Retrieve cached data for all creatives in a specific year-month.
        
        Args:
            year: The year (e.g., 2025)
            month: The month (1-12)
            
        Returns:
            List of dictionaries with cached data for each creative
        """
        try:
            if POSTGREST_AVAILABLE:
                response = (
                    self.client.from_(self.table_name)
                    .select("*")
                    .eq("year", year)
                    .eq("month", month)
                    .execute()
                )
                return response.data if response.data else []
            else:
                response = (
                    self.client.table(self.table_name)
                    .select("*")
                    .eq("year", year)
                    .eq("month", month)
                    .execute()
                )
                return response.data if response.data else []
        except Exception as e:
            print(f"Error fetching from utilization cache: {e}")
            return []

    def save_month_data(
        self,
        year: int,
        month: int,
        creative_data: List[Dict[str, Any]],
    ) -> bool:
        """Save cached data for all creatives in a specific year-month.
        
        Args:
            year: The year (e.g., 2025)
            month: The month (1-12)
            creative_data: List of dicts with keys: creative_id, available_hours, 
                          logged_hours, planned_hours (optional), utilization_percent (optional),
                          market_slug, pool_name
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # First, delete existing data for this month
            self.delete_month_data(year, month)
            
            # Prepare data for insertion
            records = [
                {
                    "year": year,
                    "month": month,
                    "creative_id": int(item["creative_id"]),
                    "available_hours": float(item["available_hours"]),
                    "logged_hours": float(item["logged_hours"]),
                    "planned_hours": float(item.get("planned_hours") or 0.0),
                    "utilization_percent": float(item["utilization_percent"]) if item.get("utilization_percent") is not None else None,
                    "market_slug": item.get("market_slug"),
                    "pool_name": item.get("pool_name"),
                }
                for item in creative_data
            ]
            
            if not records:
                return True
            
            if POSTGREST_AVAILABLE:
                response = (
                    self.client.from_(self.table_name)
                    .insert(records)
                    .execute()
                )
            else:
                response = (
                    self.client.table(self.table_name)
                    .insert(records)
                    .execute()
                )
            return True
        except Exception as e:
            print(f"Error saving to utilization cache: {e}")
            return False

    def delete_month_data(self, year: int, month: int) -> bool:
        """Delete cached data for a specific year-month.
        
        Args:
            year: The year (e.g., 2025)
            month: The month (1-12)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if POSTGREST_AVAILABLE:
                self.client.from_(self.table_name).delete().eq("year", year).eq(
                    "month", month
                ).execute()
            else:
                self.client.table(self.table_name).delete().eq("year", year).eq(
                    "month", month
                ).execute()
            return True
        except Exception as e:
            print(f"Error deleting from utilization cache: {e}")
            return False

    def is_month_cached(self, year: int, month: int) -> bool:
        """Check if data exists in cache for a specific year-month.
        
        Args:
            year: The year (e.g., 2025)
            month: The month (1-12)
            
        Returns:
            True if cached, False otherwise
        """
        data = self.get_month_data(year, month)
        return len(data) > 0
