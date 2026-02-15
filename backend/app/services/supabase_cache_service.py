"""Supabase database service for caching external hours data."""
from __future__ import annotations

import os
from datetime import date
from typing import Any, Dict, List, Optional

# Python 3.13 compatibility workaround: supabase's realtime dependency has issues
# with websockets.asyncio in Python 3.13. We'll use postgrest directly.
try:
    from postgrest import SyncPostgrestClient
    from postgrest import SyncRequestBuilder
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


def _retry_on_socket_error(func: Callable, max_retries: int = 3, initial_delay: float = 0.1) -> Any:
    """Retry a function on Windows socket errors (WinError 10035).
    
    Args:
        func: The function to retry (should be a callable that takes no args)
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds (will be doubled each retry)
        
    Returns:
        The result of the function call
        
    Raises:
        The last exception if all retries fail
    """
    last_exception = None
    delay = initial_delay
    
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            error_str = str(e)
            # Check if it's a Windows socket error
            is_socket_error = (
                "WinError 10035" in error_str or
                "non-blocking socket" in error_str.lower() or
                (hasattr(e, 'winerror') and e.winerror == 10035)
            )
            
            if is_socket_error and attempt < max_retries - 1:
                # Wait before retrying with exponential backoff
                time.sleep(delay)
                delay *= 2
                last_exception = e
                continue
            else:
                # Not a socket error or out of retries, raise immediately
                raise
    
    # If we exhausted retries, raise the last exception
    if last_exception:
        raise last_exception


class SupabaseCacheService:
    """Service for caching monthly external hours data in Supabase."""

    def __init__(self, supabase_url: str, supabase_key: str):
        """Initialize the Supabase client.
        
        Args:
            supabase_url: Your Supabase project URL
            supabase_key: Your Supabase service role key (for server-side operations)
        """
        self.supabase_url = supabase_url.rstrip('/')
        self.supabase_key = supabase_key
        self.table_name = "external_hours_monthly_cache"
        
        # Use PostgREST directly if available (Python 3.13 compatible)
        if POSTGREST_AVAILABLE:
            # PostgREST client uses the REST API endpoint
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
    def from_env(cls) -> SupabaseCacheService:
        """Create a SupabaseCacheService instance from environment variables.
        
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
    ) -> Optional[Dict[str, Any]]:
        """Retrieve cached data for a specific year-month.
        
        Args:
            year: The year (e.g., 2025)
            month: The month (1-12)
            
        Returns:
            Dictionary with cached data or None if not found
        """
        try:
            if POSTGREST_AVAILABLE:
                def _fetch():
                    response = (
                        self.client.from_(self.table_name)
                        .select("*")
                        .eq("year", year)
                        .eq("month", month)
                        .execute()
                    )
                    if response.data and len(response.data) > 0:
                        return response.data[0]
                    return None
                return _retry_on_socket_error(_fetch)
            else:
                # Use supabase client
                def _fetch():
                    response = (
                        self.client.table(self.table_name)
                        .select("*")
                        .eq("year", year)
                        .eq("month", month)
                        .execute()
                    )
                    if response.data and len(response.data) > 0:
                        return response.data[0]
                    return None
                return _retry_on_socket_error(_fetch)
        except Exception as e:
            # Log error but don't fail - fallback to Odoo
            print(f"Error fetching from Supabase cache: {e}")
            return None

    def get_year_data(self, year: int) -> List[Dict[str, Any]]:
        """Retrieve all cached months for a specific year.
        
        Args:
            year: The year (e.g., 2025)
            
        Returns:
            List of dictionaries with cached data, ordered by month
        """
        try:
            if POSTGREST_AVAILABLE:
                def _fetch():
                    response = (
                        self.client.from_(self.table_name)
                        .select("*")
                        .eq("year", year)
                        .order("month", desc=False)
                        .execute()
                    )
                    return response.data if response.data else []
                return _retry_on_socket_error(_fetch)
            else:
                def _fetch():
                    response = (
                        self.client.table(self.table_name)
                        .select("*")
                        .eq("year", year)
                        .order("month", desc=False)
                        .execute()
                    )
                    return response.data if response.data else []
                return _retry_on_socket_error(_fetch)
        except Exception as e:
            print(f"Error fetching year data from Supabase cache: {e}")
            return []

    def save_month_data(
        self,
        year: int,
        month: int,
        total_external_hours: float,
        total_subscription_used_hours: float,
        total_used_hours: float,
        total_monthly_subscription_hours: float,
        total_sold_hours: float,
    ) -> bool:
        """Save or update cached data for a specific year-month.
        
        Args:
            year: The year (e.g., 2025)
            month: The month (1-12)
            total_external_hours: Total external hours for the month
            total_subscription_used_hours: Total subscription used hours
            total_used_hours: Total used hours (external + subscription used)
            total_monthly_subscription_hours: Total monthly subscription hours
            total_sold_hours: Total sold hours (external + monthly subscription)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            data = {
                "year": year,
                "month": month,
                "total_external_hours": float(total_external_hours),
                "total_subscription_used_hours": float(total_subscription_used_hours),
                "total_used_hours": float(total_used_hours),
                "total_monthly_subscription_hours": float(total_monthly_subscription_hours),
                "total_sold_hours": float(total_sold_hours),
            }
            
            if POSTGREST_AVAILABLE:
                # Use upsert for PostgREST
                response = (
                    self.client.from_(self.table_name)
                    .upsert(data, on_conflict="year,month")
                    .execute()
                )
            else:
                # Use supabase client
                response = (
                    self.client.table(self.table_name)
                    .upsert(data, on_conflict="year,month")
                    .execute()
                )
            return True
        except Exception as e:
            print(f"Error saving to Supabase cache: {e}")
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
            print(f"Error deleting from Supabase cache: {e}")
            return False

    def delete_year_data(self, year: int) -> bool:
        """Delete all cached data for a specific year.
        
        Args:
            year: The year (e.g., 2025)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if POSTGREST_AVAILABLE:
                self.client.from_(self.table_name).delete().eq("year", year).execute()
            else:
                self.client.table(self.table_name).delete().eq("year", year).execute()
            return True
        except Exception as e:
            print(f"Error deleting year data from Supabase cache: {e}")
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
        return data is not None

    def convert_cache_to_series_format(
        self, cached_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Convert cached database record to the format expected by the frontend.
        
        Args:
            cached_data: Dictionary from database
            
        Returns:
            Dictionary in the format expected by external_used_hours_series
        """
        from calendar import monthrange
        
        year = int(cached_data["year"])
        month = int(cached_data["month"])
        month_start = date(year, month, 1)
        
        return {
            "year": year,
            "month": month,
            "label": month_start.strftime("%b"),
            "total_external_hours": float(cached_data["total_external_hours"]),
            "total_external_hours_display": self._format_hours(
                float(cached_data["total_external_hours"])
            ),
            "total_subscription_used_hours": float(
                cached_data["total_subscription_used_hours"]
            ),
            "total_subscription_used_hours_display": self._format_hours(
                float(cached_data["total_subscription_used_hours"])
            ),
            "total_used_hours": float(cached_data["total_used_hours"]),
            "total_used_hours_display": self._format_hours(
                float(cached_data["total_used_hours"])
            ),
            "total_monthly_subscription_hours": float(
                cached_data["total_monthly_subscription_hours"]
            ),
            "total_monthly_subscription_hours_display": self._format_hours(
                float(cached_data["total_monthly_subscription_hours"])
            ),
            "total_sold_hours": float(cached_data["total_sold_hours"]),
            "total_sold_hours_display": self._format_hours(
                float(cached_data["total_sold_hours"])
            ),
        }

    @staticmethod
    def _format_hours(value: float) -> str:
        """Format hours value for display."""
        return f"{value:,.1f}h" if value % 1 else f"{int(value)}h"

    # Creative Groups Methods
    def get_creative_groups(self) -> List[Dict[str, Any]]:
        """Retrieve all saved creative groups.
        
        Returns:
            List of dictionaries with group data
        """
        try:
            if POSTGREST_AVAILABLE:
                response = (
                    self.client.from_("creative_groups")
                    .select("*")
                    .order("created_at", desc=False)
                    .execute()
                )
                # Reverse to get newest first
                data = response.data if response.data else []
                return list(reversed(data))
            else:
                response = (
                    self.client.table("creative_groups")
                    .select("*")
                    .order("created_at", desc=True)
                    .execute()
                )
                return response.data if response.data else []
        except Exception as e:
            print(f"Error fetching creative groups from Supabase: {e}")
            return []

    def save_creative_group(
        self,
        name: str,
        creative_ids: List[int],
        group_id: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """Save or update a creative group.
        
        Args:
            name: Group name
            creative_ids: List of creative employee IDs
            group_id: Optional ID for updating existing group
            
        Returns:
            Dictionary with saved group data or None if failed
        """
        try:
            data = {
                "name": name,
                "creative_ids": creative_ids,
            }
            
            if POSTGREST_AVAILABLE:
                if group_id:
                    # Update existing
                    response = (
                        self.client.from_("creative_groups")
                        .update(data)
                        .eq("id", group_id)
                        .execute()
                    )
                else:
                    # Insert new
                    response = (
                        self.client.from_("creative_groups")
                        .insert(data)
                        .execute()
                    )
                return response.data[0] if response.data and len(response.data) > 0 else None
            else:
                if group_id:
                    response = (
                        self.client.table("creative_groups")
                        .update(data)
                        .eq("id", group_id)
                        .execute()
                    )
                else:
                    response = (
                        self.client.table("creative_groups")
                        .insert(data)
                        .execute()
                    )
                return response.data[0] if response.data and len(response.data) > 0 else None
        except Exception as e:
            print(f"Error saving creative group to Supabase: {e}")
            return None

    def delete_creative_group(self, group_id: int) -> bool:
        """Delete a creative group.
        
        Args:
            group_id: ID of the group to delete
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if POSTGREST_AVAILABLE:
                self.client.from_("creative_groups").delete().eq("id", group_id).execute()
            else:
                self.client.table("creative_groups").delete().eq("id", group_id).execute()
            return True
        except Exception as e:
            print(f"Error deleting creative group from Supabase: {e}")
            return False
