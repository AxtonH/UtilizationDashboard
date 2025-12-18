"""Service for managing refresh tokens for dashboard authentication."""
from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timedelta
from typing import Optional, Tuple

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


class AuthTokenService:
    """Service for managing refresh tokens stored in Supabase."""

    def __init__(self, supabase_url: str, supabase_key: str):
        """Initialize the Supabase client for auth tokens.
        
        Args:
            supabase_url: Your Supabase project URL
            supabase_key: Your Supabase service role key (for server-side operations)
        """
        self.supabase_url = supabase_url.rstrip('/')
        self.supabase_key = supabase_key
        self.table_name = "refresh_tokens"
        self.token_expiry_days = 365  # 1 year
        
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
    def from_env(cls) -> AuthTokenService:
        """Create AuthTokenService from environment variables.
        
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

    def _generate_token(self) -> str:
        """Generate a secure random refresh token (86 characters, URL-safe)."""
        return secrets.token_urlsafe(64)  # 64 bytes = 86 characters when base64 encoded

    def _hash_token(self, token: str) -> str:
        """Hash a token using SHA-256."""
        return hashlib.sha256(token.encode('utf-8')).hexdigest()

    def _xor_encrypt(self, password: str, token: str) -> str:
        """Encrypt password using XOR with token as key."""
        # Convert to bytes
        password_bytes = password.encode('utf-8')
        token_bytes = token.encode('utf-8')
        
        # Repeat token to match password length
        key = (token_bytes * ((len(password_bytes) // len(token_bytes)) + 1))[:len(password_bytes)]
        
        # XOR encrypt
        encrypted = bytes(a ^ b for a, b in zip(password_bytes, key))
        
        # Return as base64 string
        import base64
        return base64.b64encode(encrypted).decode('utf-8')

    def _xor_decrypt(self, encrypted_password: str, token: str) -> str:
        """Decrypt password using XOR with token as key."""
        import base64
        encrypted_bytes = base64.b64decode(encrypted_password.encode('utf-8'))
        token_bytes = token.encode('utf-8')
        
        # Repeat token to match encrypted length
        key = (token_bytes * ((len(encrypted_bytes) // len(token_bytes)) + 1))[:len(encrypted_bytes)]
        
        # XOR decrypt
        decrypted = bytes(a ^ b for a, b in zip(encrypted_bytes, key))
        
        return decrypted.decode('utf-8')

    def create_refresh_token(self, user_id: int, username: str, password: str) -> str:
        """Create a new refresh token and store it in Supabase.
        
        Args:
            user_id: Odoo user ID
            username: Odoo username (email)
            password: Odoo password
            
        Returns:
            The refresh token (store this in a cookie, don't store in DB)
        """
        # Generate token
        token = self._generate_token()
        token_hash = self._hash_token(token)
        
        # Encrypt password
        encrypted_password = self._xor_encrypt(password, token)
        
        # Store in Supabase
        try:
            if POSTGREST_AVAILABLE:
                response = (
                    self.client.from_(self.table_name)
                    .insert({
                        "token_hash": token_hash,
                        "user_id": user_id,
                        "username": username,
                        "encrypted_password": encrypted_password,
                        "created_at": datetime.utcnow().isoformat(),
                        "revoked_at": None,
                    })
                    .execute()
                )
            else:
                # Use supabase client
                response = (
                    self.client.table(self.table_name)
                    .insert({
                        "token_hash": token_hash,
                        "user_id": user_id,
                        "username": username,
                        "encrypted_password": encrypted_password,
                        "created_at": datetime.utcnow().isoformat(),
                        "revoked_at": None,
                    })
                    .execute()
                )
            
            return token
        except Exception as e:
            raise RuntimeError(f"Failed to create refresh token: {e}") from e

    def verify_refresh_token(self, token: str) -> Optional[Tuple[int, str, str]]:
        """Verify a refresh token and return user credentials.
        
        Args:
            token: The refresh token from cookie
            
        Returns:
            Tuple of (user_id, username, password) if valid, None otherwise
        """
        if not token:
            return None
        
        token_hash = self._hash_token(token)
        
        try:
            # Find token in database
            if POSTGREST_AVAILABLE:
                response = (
                    self.client.from_(self.table_name)
                    .select("*")
                    .eq("token_hash", token_hash)
                    .is_("revoked_at", "null")
                    .execute()
                )
                if not response.data or len(response.data) == 0:
                    return None
                token_data = response.data[0]
            else:
                # Use supabase client
                response = (
                    self.client.table(self.table_name)
                    .select("*")
                    .eq("token_hash", token_hash)
                    .is_("revoked_at", "null")
                    .execute()
                )
                if not response.data or len(response.data) == 0:
                    return None
                token_data = response.data[0]
            
            # Check if token has expired (365 days)
            created_at_str = token_data.get("created_at")
            if created_at_str:
                created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                if created_at.tzinfo:
                    created_at = created_at.replace(tzinfo=None)
                
                expiry_date = created_at + timedelta(days=self.token_expiry_days)
                if datetime.utcnow() > expiry_date:
                    # Token expired, revoke it
                    self.revoke_token(token)
                    return None
            
            # Decrypt password
            encrypted_password = token_data.get("encrypted_password")
            if not encrypted_password:
                return None
            
            password = self._xor_decrypt(encrypted_password, token)
            user_id = token_data.get("user_id")
            username = token_data.get("username")
            
            if user_id and username and password:
                return (user_id, username, password)
            
            return None
        except Exception as e:
            # Log error but don't expose details
            print(f"Error verifying refresh token: {e}")
            return None

    def revoke_token(self, token: str) -> bool:
        """Revoke a refresh token by setting revoked_at timestamp.
        
        Args:
            token: The refresh token to revoke
            
        Returns:
            True if revoked successfully, False otherwise
        """
        if not token:
            return False
        
        token_hash = self._hash_token(token)
        
        try:
            if POSTGREST_AVAILABLE:
                response = (
                    self.client.from_(self.table_name)
                    .update({"revoked_at": datetime.utcnow().isoformat()})
                    .eq("token_hash", token_hash)
                    .execute()
                )
            else:
                # Use supabase client
                response = (
                    self.client.table(self.table_name)
                    .update({"revoked_at": datetime.utcnow().isoformat()})
                    .eq("token_hash", token_hash)
                    .execute()
                )
            
            return True
        except Exception as e:
            print(f"Error revoking token: {e}")
            return False

    def revoke_all_user_tokens(self, user_id: int) -> bool:
        """Revoke all refresh tokens for a specific user.
        
        Args:
            user_id: Odoo user ID
            
        Returns:
            True if revoked successfully, False otherwise
        """
        try:
            if POSTGREST_AVAILABLE:
                response = (
                    self.client.from_(self.table_name)
                    .update({"revoked_at": datetime.utcnow().isoformat()})
                    .eq("user_id", user_id)
                    .is_("revoked_at", "null")
                    .execute()
                )
            else:
                # Use supabase client
                response = (
                    self.client.table(self.table_name)
                    .update({"revoked_at": datetime.utcnow().isoformat()})
                    .eq("user_id", user_id)
                    .is_("revoked_at", "null")
                    .execute()
                )
            
            return True
        except Exception as e:
            print(f"Error revoking user tokens: {e}")
            return False

