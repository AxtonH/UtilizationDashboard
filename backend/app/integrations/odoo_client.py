"""Odoo XML-RPC client with chunked retrieval helpers."""
from __future__ import annotations

import socket
import xmlrpc.client
from typing import Any, Dict, Iterable, Iterator, List, Optional
from urllib.parse import urlparse

from ..config import OdooSettings


class OdooUnavailableError(RuntimeError):
    """Raised when the Odoo backend cannot be reached."""


class _TimeoutTransport(xmlrpc.client.Transport):
    """HTTP transport with per-connection timeouts."""

    def __init__(self, timeout: float):
        super().__init__()
        self._timeout = timeout

    def make_connection(self, host: str):
        connection = super().make_connection(host)
        try:
            connection.timeout = self._timeout
        except AttributeError:
            # Some transports may not expose a timeout attribute; ignore silently.
            pass
        return connection


class _TimeoutSafeTransport(xmlrpc.client.SafeTransport):
    """HTTPS transport with per-connection timeouts."""

    def __init__(self, timeout: float):
        super().__init__()
        self._timeout = timeout

    def make_connection(self, host: str):
        connection = super().make_connection(host)
        try:
            connection.timeout = self._timeout
        except AttributeError:
            pass
        return connection


def _transport_for_url(url: str, timeout: float) -> xmlrpc.client.Transport:
    """Select an appropriate transport implementation for the given URL."""
    scheme = urlparse(url).scheme.lower()
    if scheme == "https":
        return _TimeoutSafeTransport(timeout)
    return _TimeoutTransport(timeout)


class OdooClient:
    """Lightweight wrapper around Odoo's XML-RPC API."""

    def __init__(self, settings: OdooSettings):
        self.settings = settings
        base_url = settings.url.rstrip("/")
        self._timeout = float(settings.timeout)
        common_url = f"{base_url}/xmlrpc/2/common"
        object_url = f"{base_url}/xmlrpc/2/object"
        common_transport = _transport_for_url(common_url, self._timeout)
        object_transport = _transport_for_url(object_url, self._timeout)
        self._common = xmlrpc.client.ServerProxy(common_url, allow_none=True, transport=common_transport)
        self._models = xmlrpc.client.ServerProxy(object_url, allow_none=True, transport=object_transport)
        self._uid: Optional[int] = None

    def authenticate(self) -> int:
        """Authenticate and cache the Odoo user id."""
        if self._uid is None:
            try:
                uid = self._common.authenticate(
                    self.settings.db,
                    self.settings.username,
                    self.settings.password,
                    {},
                )
            except (socket.timeout, OSError, xmlrpc.client.ProtocolError) as exc:
                raise OdooUnavailableError("Unable to reach Odoo. Check network access and credentials.") from exc
            if not uid:
                raise RuntimeError("Authentication against Odoo failed. Check credentials.")
            self._uid = uid
        return self._uid

    def verify_user_credentials(self, username: str, password: str) -> bool:
        """Verify user credentials against Odoo without caching the UID.
        
        This method is used to verify user login credentials without affecting
        the cached authentication used for data retrieval.
        
        Args:
            username: Odoo username (email)
            password: Odoo password
            
        Returns:
            True if credentials are valid, False otherwise
        """
        try:
            uid = self._common.authenticate(
                self.settings.db,
                username,
                password,
                {},
            )
            return bool(uid)
        except (socket.timeout, OSError, xmlrpc.client.ProtocolError):
            # Network/connection errors - treat as invalid for security
            return False
        except Exception:
            # Any other error - treat as invalid
            return False

    def execute_kw(
        self,
        model: str,
        method: str,
        args: Optional[List[Any]] = None,
        kwargs: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Execute an arbitrary Odoo model method."""
        args = args or []
        kwargs = kwargs or {}
        uid = self.authenticate()
        try:
            return self._models.execute_kw(
                self.settings.db,
                uid,
                self.settings.password,
                model,
                method,
                args,
                kwargs,
            )
        except (socket.timeout, OSError, xmlrpc.client.ProtocolError) as exc:
            raise OdooUnavailableError("Odoo API request failed due to a connection error.") from exc

    def search(self, model: str, domain: Iterable[Any], *, limit: Optional[int] = None) -> List[int]:
        """Search for records matching a domain."""
        kwargs: Dict[str, Any] = {}
        if limit is not None:
            kwargs["limit"] = limit
        return self.execute_kw(model, "search", [list(domain)], kwargs)

    def read(self, model: str, ids: Iterable[int], fields: Optional[Iterable[str]] = None) -> List[Dict[str, Any]]:
        """Read specific fields for a set of ids."""
        kwargs: Dict[str, Any] = {}
        if fields is not None:
            kwargs["fields"] = list(fields)
        return self.execute_kw(model, "read", [list(ids)], kwargs)

    def search_read_chunked(
        self,
        model: str,
        domain: Optional[Iterable[Any]] = None,
        *,
        fields: Optional[Iterable[str]] = None,
        order: Optional[str] = None,
        chunk_size: Optional[int] = None,
    ) -> Iterator[List[Dict[str, Any]]]:
        """Yield search_read results in chunks to handle large datasets."""
        effective_domain = list(domain or [])
        requested_fields = list(fields or [])
        size = chunk_size or self.settings.chunk_size
        offset = 0

        def _with_stable_order(spec: Optional[str]) -> str:
            """Ensure the search order is stable across paginated requests."""
            if not spec or not spec.strip():
                return "id asc"

            segments = [segment.strip() for segment in spec.split(",") if segment.strip()]
            normalized = {segment.split()[0].lower() for segment in segments}
            if "id" not in normalized:
                segments.append("id asc")
            return ", ".join(segments)

        stable_order = _with_stable_order(order)

        while True:
            kwargs: Dict[str, Any] = {"fields": requested_fields, "limit": size, "offset": offset, "order": stable_order}
            batch = self.execute_kw(model, "search_read", [effective_domain], kwargs)
            if not batch:
                break

            yield batch

            if len(batch) < size:
                break
            offset += size

    def search_read_all(
        self,
        model: str,
        domain: Optional[Iterable[Any]] = None,
        *,
        fields: Optional[Iterable[str]] = None,
        order: Optional[str] = None,
        chunk_size: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Collect all chunks into a single list."""
        records: List[Dict[str, Any]] = []
        for batch in self.search_read_chunked(
            model,
            domain=domain,
            fields=fields,
            order=order,
            chunk_size=chunk_size,
        ):
            records.extend(batch)
        return records

    def close(self) -> None:
        """Release underlying XML-RPC connections when the client is discarded."""
        for attr in ("_common", "_models"):
            proxy = getattr(self, attr, None)
            close = getattr(proxy, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    continue
        self._common = None  # type: ignore[assignment]
        self._models = None  # type: ignore[assignment]
        self._uid = None
