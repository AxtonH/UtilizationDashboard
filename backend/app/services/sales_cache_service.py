"""Supabase database service for caching sales data."""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

# Python 3.13 compatibility workaround: supabase's realtime dependency has issues
# with websockets.asyncio in Python 3.13. We'll use postgrest directly.
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


class SalesCacheService:
    """Service for caching monthly invoiced totals in Supabase."""

    def __init__(self, supabase_url: str, supabase_key: str):
        """Initialize the Supabase client.
        
        Args:
            supabase_url: Your Supabase project URL
            supabase_key: Your Supabase service role key (for server-side operations)
        """
        self.supabase_url = supabase_url.rstrip('/')
        self.supabase_key = supabase_key
        self.table_name = "monthly_invoiced_totals"
        
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
    def from_env(cls) -> SalesCacheService:
        """Create a SalesCacheService instance from environment variables.
        
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
            else:
                # Use supabase client
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
                response = (
                    self.client.from_(self.table_name)
                    .select("*")
                    .eq("year", year)
                    .order("month", desc=False)
                    .execute()
                )
                return response.data if response.data else []
            else:
                response = (
                    self.client.table(self.table_name)
                    .select("*")
                    .eq("year", year)
                    .order("month", desc=False)
                    .execute()
                )
                return response.data if response.data else []
        except Exception as e:
            print(f"Error fetching year data from Supabase cache: {e}")
            return []

    def save_month_data(
        self,
        year: int,
        month: int,
        amount_aed: float,
    ) -> bool:
        """Save or update cached data for a specific year-month.
        
        Args:
            year: The year (e.g., 2025)
            month: The month (1-12)
            amount_aed: Total invoiced amount in AED
            
        Returns:
            True if successful, False otherwise
        """
        try:
            data = {
                "year": year,
                "month": month,
                "amount_aed": float(amount_aed),
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

    # ========================================================================
    # Sales Orders Cache Methods
    # ========================================================================

    def get_sales_order_month_data(
        self, year: int, month: int
    ) -> Optional[Dict[str, Any]]:
        """Retrieve cached Sales Orders data for a specific year-month.
        
        Args:
            year: The year (e.g., 2025)
            month: The month (1-12)
            
        Returns:
            Dictionary with cached data or None if not found
        """
        try:
            table_name = "monthly_sales_orders_totals"
            if POSTGREST_AVAILABLE:
                response = (
                    self.client.from_(table_name)
                    .select("*")
                    .eq("year", year)
                    .eq("month", month)
                    .execute()
                )
                if response.data and len(response.data) > 0:
                    return response.data[0]
                return None
            else:
                # Use supabase client
                response = (
                    self.client.table(table_name)
                    .select("*")
                    .eq("year", year)
                    .eq("month", month)
                    .execute()
                )
                if response.data and len(response.data) > 0:
                    return response.data[0]
                return None
        except Exception as e:
            # Log error but don't fail - fallback to Odoo
            print(f"Error fetching Sales Orders from Supabase cache: {e}")
            return None

    def get_sales_order_year_data(self, year: int) -> List[Dict[str, Any]]:
        """Retrieve all cached Sales Orders months for a specific year.
        
        Args:
            year: The year (e.g., 2025)
            
        Returns:
            List of dictionaries with cached data, ordered by month
        """
        try:
            table_name = "monthly_sales_orders_totals"
            if POSTGREST_AVAILABLE:
                response = (
                    self.client.from_(table_name)
                    .select("*")
                    .eq("year", year)
                    .order("month", desc=False)
                    .execute()
                )
                return response.data if response.data else []
            else:
                response = (
                    self.client.table(table_name)
                    .select("*")
                    .eq("year", year)
                    .order("month", desc=False)
                    .execute()
                )
                return response.data if response.data else []
        except Exception as e:
            print(f"Error fetching Sales Orders year data from Supabase cache: {e}")
            return []

    def save_sales_order_month_data(
        self,
        year: int,
        month: int,
        total_amount_aed: float,
    ) -> bool:
        """Save or update cached Sales Orders data for a specific year-month.
        
        Args:
            year: The year (e.g., 2025)
            month: The month (1-12)
            total_amount_aed: Total Sales Orders amount in AED
            
        Returns:
            True if successful, False otherwise
        """
        try:
            table_name = "monthly_sales_orders_totals"
            data = {
                "year": year,
                "month": month,
                "total_amount_aed": float(total_amount_aed),
            }
            
            if POSTGREST_AVAILABLE:
                # Use upsert for PostgREST
                response = (
                    self.client.from_(table_name)
                    .upsert(data, on_conflict="year,month")
                    .execute()
                )
            else:
                # Use supabase client
                response = (
                    self.client.table(table_name)
                    .upsert(data, on_conflict="year,month")
                    .execute()
                )
            return True
        except Exception as e:
            error_msg = str(e)
            # Provide more helpful error message for schema cache issues
            if "PGRST204" in error_msg or "schema cache" in error_msg.lower():
                print(f"Error saving Sales Orders to Supabase cache: {e}")
                print(f"  -> This usually means Supabase's schema cache needs to be refreshed.")
                print(f"  -> Please run the SQL in verify_sales_orders_table.sql or wait a few minutes for auto-refresh.")
                print(f"  -> Table: {table_name}, Data keys: {list(data.keys())}")
            else:
                print(f"Error saving Sales Orders to Supabase cache: {e}")
            return False

    def delete_sales_order_month_data(self, year: int, month: int) -> bool:
        """Delete cached Sales Orders data for a specific year-month.
        
        Args:
            year: The year (e.g., 2025)
            month: The month (1-12)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            table_name = "monthly_sales_orders_totals"
            if POSTGREST_AVAILABLE:
                self.client.from_(table_name).delete().eq("year", year).eq(
                    "month", month
                ).execute()
            else:
                self.client.table(table_name).delete().eq("year", year).eq(
                    "month", month
                ).execute()
            return True
        except Exception as e:
            print(f"Error deleting Sales Orders from Supabase cache: {e}")
            return False