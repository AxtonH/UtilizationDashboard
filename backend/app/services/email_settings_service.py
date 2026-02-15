"""Service for managing email settings in Supabase."""
from __future__ import annotations

import os
from datetime import date, time
from typing import Any, Dict, List, Optional

try:
    from postgrest import SyncPostgrestClient
    POSTGREST_AVAILABLE = True
except ImportError:
    POSTGREST_AVAILABLE = False
    try:
        from supabase import create_client
        SUPABASE_CLIENT_AVAILABLE = True
    except ImportError:
        SUPABASE_CLIENT_AVAILABLE = False
        create_client = None  # type: ignore


class EmailSettingsService:
    """Service for managing email settings in Supabase."""

    def __init__(self, supabase_url: str, supabase_key: str):
        """Initialize the email settings service.
        
        Args:
            supabase_url: Your Supabase project URL
            supabase_key: Your Supabase service role key
        """
        self.supabase_url = supabase_url.rstrip('/')
        self.supabase_key = supabase_key
        self.table_name = "email_settings"
        
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
    def from_env(cls) -> EmailSettingsService:
        """Create EmailSettingsService instance from environment variables.
        
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

    def get_settings(self) -> Optional[Dict[str, Any]]:
        """Get current email settings.
        
        Returns:
            Dictionary with email settings or None if not found
        """
        try:
            if POSTGREST_AVAILABLE:
                response = (
                    self.client.from_(self.table_name)
                    .select("*")
                    .eq("id", 1)
                    .execute()
                )
                if response.data and len(response.data) > 0:
                    settings = response.data[0]
                    # Ensure internal_external_imbalance_enabled exists (for backward compatibility)
                    if "internal_external_imbalance_enabled" not in settings:
                        settings["internal_external_imbalance_enabled"] = False
                    else:
                        # Convert to proper boolean (handle string "true"/"false" or PostgreSQL boolean)
                        val = settings["internal_external_imbalance_enabled"]
                        if isinstance(val, str):
                            settings["internal_external_imbalance_enabled"] = val.lower() in ("true", "t", "1")
                        else:
                            settings["internal_external_imbalance_enabled"] = bool(val)
                    # Ensure overbooking_enabled exists (for backward compatibility)
                    if "overbooking_enabled" not in settings:
                        settings["overbooking_enabled"] = False
                    else:
                        # Convert to proper boolean (handle string "true"/"false" or PostgreSQL boolean)
                        val = settings["overbooking_enabled"]
                        if isinstance(val, str):
                            settings["overbooking_enabled"] = val.lower() in ("true", "t", "1")
                        else:
                            settings["overbooking_enabled"] = bool(val)
                    # Ensure underbooking_enabled exists (for backward compatibility)
                    if "underbooking_enabled" not in settings:
                        settings["underbooking_enabled"] = False
                    else:
                        # Convert to proper boolean (handle string "true"/"false" or PostgreSQL boolean)
                        val = settings["underbooking_enabled"]
                        if isinstance(val, str):
                            settings["underbooking_enabled"] = val.lower() in ("true", "t", "1")
                        else:
                            settings["underbooking_enabled"] = bool(val)
                    # Ensure subscription_hours_alert_enabled exists (for backward compatibility)
                    if "subscription_hours_alert_enabled" not in settings:
                        settings["subscription_hours_alert_enabled"] = False
                    else:
                        # Convert to proper boolean (handle string "true"/"false" or PostgreSQL boolean)
                        val = settings["subscription_hours_alert_enabled"]
                        if isinstance(val, str):
                            settings["subscription_hours_alert_enabled"] = val.lower() in ("true", "t", "1")
                        else:
                            settings["subscription_hours_alert_enabled"] = bool(val)
                    return settings
                return None
            else:
                # Use supabase client
                response = (
                    self.client.table(self.table_name)
                    .select("*")
                    .eq("id", 1)
                    .execute()
                )
                if response.data and len(response.data) > 0:
                    settings = response.data[0]
                    # Ensure internal_external_imbalance_enabled exists (for backward compatibility)
                    if "internal_external_imbalance_enabled" not in settings:
                        settings["internal_external_imbalance_enabled"] = False
                    else:
                        # Convert to proper boolean (handle string "true"/"false" or PostgreSQL boolean)
                        val = settings["internal_external_imbalance_enabled"]
                        if isinstance(val, str):
                            settings["internal_external_imbalance_enabled"] = val.lower() in ("true", "t", "1")
                        else:
                            settings["internal_external_imbalance_enabled"] = bool(val)
                    # Ensure overbooking_enabled exists (for backward compatibility)
                    if "overbooking_enabled" not in settings:
                        settings["overbooking_enabled"] = False
                    else:
                        # Convert to proper boolean (handle string "true"/"false" or PostgreSQL boolean)
                        val = settings["overbooking_enabled"]
                        if isinstance(val, str):
                            settings["overbooking_enabled"] = val.lower() in ("true", "t", "1")
                        else:
                            settings["overbooking_enabled"] = bool(val)
                    # Ensure underbooking_enabled exists (for backward compatibility)
                    if "underbooking_enabled" not in settings:
                        settings["underbooking_enabled"] = False
                    else:
                        # Convert to proper boolean (handle string "true"/"false" or PostgreSQL boolean)
                        val = settings["underbooking_enabled"]
                        if isinstance(val, str):
                            settings["underbooking_enabled"] = val.lower() in ("true", "t", "1")
                        else:
                            settings["underbooking_enabled"] = bool(val)
                    # Ensure subscription_hours_alert_enabled exists (for backward compatibility)
                    if "subscription_hours_alert_enabled" not in settings:
                        settings["subscription_hours_alert_enabled"] = False
                    else:
                        # Convert to proper boolean (handle string "true"/"false" or PostgreSQL boolean)
                        val = settings["subscription_hours_alert_enabled"]
                        if isinstance(val, str):
                            settings["subscription_hours_alert_enabled"] = val.lower() in ("true", "t", "1")
                        else:
                            settings["subscription_hours_alert_enabled"] = bool(val)
                    return settings
                return None
        except Exception as e:
            print(f"Error fetching email settings: {e}")
            return None

    def save_settings(
        self,
        recipients: List[str],
        cc_recipients: List[str],
        send_date: Optional[date] = None,
        send_time: Optional[time] = None,
        enabled: bool = True,
        internal_external_imbalance_enabled: bool = False,
        overbooking_enabled: bool = False,
        underbooking_enabled: bool = False,
        subscription_hours_alert_enabled: bool = False,
    ) -> bool:
        """Save or update email settings.
        
        Args:
            recipients: List of email addresses to send to
            cc_recipients: List of email addresses to CC
            send_date: Date to send email (optional)
            send_time: Time to send email (optional)
            enabled: Whether email sending is enabled
            internal_external_imbalance_enabled: Whether internal/external imbalance alert is enabled
            overbooking_enabled: Whether overbooking alert is enabled
            underbooking_enabled: Whether underbooking alert is enabled
            subscription_hours_alert_enabled: Whether subscription hours alert is enabled
            
        Returns:
            True if successful, False otherwise
        """
        try:
            data: Dict[str, Any] = {
                "id": 1,  # Explicitly set id=1 to ensure we update the existing row
                "recipients": recipients,
                "cc_recipients": cc_recipients,
                "enabled": enabled,
                "internal_external_imbalance_enabled": internal_external_imbalance_enabled,
                "overbooking_enabled": overbooking_enabled,
                "underbooking_enabled": underbooking_enabled,
                "subscription_hours_alert_enabled": subscription_hours_alert_enabled,
            }
            
            if send_date:
                data["send_date"] = send_date.isoformat()
            else:
                data["send_date"] = None
                
            if send_time:
                data["send_time"] = send_time.isoformat()
            else:
                data["send_time"] = None
            
            if POSTGREST_AVAILABLE:
                # Use upsert for PostgREST (update id=1 or insert if doesn't exist)
                response = (
                    self.client.from_(self.table_name)
                    .upsert(data, on_conflict="id")
                    .execute()
                )
            else:
                # Use supabase client
                response = (
                    self.client.table(self.table_name)
                    .upsert(data, on_conflict="id")
                    .execute()
                )
            return True
        except Exception as e:
            print(f"Error saving email settings: {e}")
            return False
