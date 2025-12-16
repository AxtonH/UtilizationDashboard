"""Service for tracking user login events in Supabase."""
from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

# Python 3.13 compatibility workaround: supabase's realtime dependency has issues
try:
    from postgrest import SyncPostgrestClient
    POSTGREST_AVAILABLE = True
except ImportError:
    POSTGREST_AVAILABLE = False
    try:
        from supabase import create_client, Client
        SUPABASE_CLIENT_AVAILABLE = True
    except Exception:
        SUPABASE_CLIENT_AVAILABLE = False
        Client = None  # type: ignore


class LoginTrackingService:
    """Service for tracking user login events in Supabase."""

    def __init__(self, supabase_url: str, supabase_key: str):
        """Initialize the Supabase client for login tracking.
        
        Args:
            supabase_url: Your Supabase project URL
            supabase_key: Your Supabase service role key (for server-side operations)
        """
        self.supabase_url = supabase_url.rstrip('/')
        self.supabase_key = supabase_key
        self.table_name = "login_events"
        
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
    def from_env(cls) -> LoginTrackingService:
        """Create LoginTrackingService from environment variables.
        
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

    def log_login(
        self,
        user_id: int,
        username: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> bool:
        """Log a user login event.
        
        Args:
            user_id: Odoo user ID
            username: Odoo username (email)
            ip_address: Optional IP address of the user
            user_agent: Optional user agent string
            
        Returns:
            True if logged successfully, False otherwise
        """
        try:
            login_data = {
                "user_id": user_id,
                "username": username,
                "login_timestamp": datetime.utcnow().isoformat(),
            }
            
            # Add optional fields if provided
            if ip_address:
                login_data["ip_address"] = ip_address
            if user_agent:
                login_data["user_agent"] = user_agent
            
            if POSTGREST_AVAILABLE:
                response = (
                    self.client.from_(self.table_name)
                    .insert(login_data)
                    .execute()
                )
            else:
                # Use supabase client
                response = (
                    self.client.table(self.table_name)
                    .insert(login_data)
                    .execute()
                )
            
            return True
        except Exception as e:
            # Log error but don't fail login process
            print(f"Error logging login event: {e}")
            return False

    def get_user_login_history(
        self,
        user_id: int,
        limit: int = 50
    ) -> list[dict]:
        """Get login history for a specific user.
        
        Args:
            user_id: Odoo user ID
            limit: Maximum number of records to return
            
        Returns:
            List of login event dictionaries
        """
        try:
            if POSTGREST_AVAILABLE:
                response = (
                    self.client.from_(self.table_name)
                    .select("*")
                    .eq("user_id", user_id)
                    .order("login_timestamp", desc=True)
                    .limit(limit)
                    .execute()
                )
                return response.data or []
            else:
                # Use supabase client
                response = (
                    self.client.table(self.table_name)
                    .select("*")
                    .eq("user_id", user_id)
                    .order("login_timestamp", desc=True)
                    .limit(limit)
                    .execute()
                )
                return response.data or []
        except Exception as e:
            print(f"Error fetching login history: {e}")
            return []

    def get_recent_logins(self, limit: int = 100) -> list[dict]:
        """Get recent login events across all users.
        
        Args:
            limit: Maximum number of records to return
            
        Returns:
            List of login event dictionaries
        """
        try:
            if POSTGREST_AVAILABLE:
                response = (
                    self.client.from_(self.table_name)
                    .select("*")
                    .order("login_timestamp", desc=True)
                    .limit(limit)
                    .execute()
                )
                return response.data or []
            else:
                # Use supabase client
                response = (
                    self.client.table(self.table_name)
                    .select("*")
                    .order("login_timestamp", desc=True)
                    .limit(limit)
                    .execute()
                )
                return response.data or []
        except Exception as e:
            print(f"Error fetching recent logins: {e}")
            return []

    def get_login_count_by_user(self, user_id: int) -> int:
        """Get total login count for a specific user.
        
        Args:
            user_id: Odoo user ID
            
        Returns:
            Total number of login events for the user
        """
        try:
            if POSTGREST_AVAILABLE:
                # PostgREST: use count with select
                response = (
                    self.client.from_(self.table_name)
                    .select("*", count="exact")
                    .eq("user_id", user_id)
                    .execute()
                )
                # Check if count is in response headers or use data length
                if hasattr(response, 'count') and response.count is not None:
                    return response.count
                return len(response.data) if response.data else 0
            else:
                # Use supabase client
                response = (
                    self.client.table(self.table_name)
                    .select("*", count="exact")
                    .eq("user_id", user_id)
                    .execute()
                )
                # Supabase client may return count in response
                if hasattr(response, 'count') and response.count is not None:
                    return response.count
                return len(response.data) if response.data else 0
        except Exception as e:
            print(f"Error counting user logins: {e}")
            return 0
