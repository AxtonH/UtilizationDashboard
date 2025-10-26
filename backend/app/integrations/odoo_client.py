"""Odoo XML-RPC client with chunked retrieval helpers."""
from __future__ import annotations

from typing import Any, Dict, Iterable, Iterator, List, Optional
import xmlrpc.client

from ..config import OdooSettings


class OdooClient:
    """Lightweight wrapper around Odoo's XML-RPC API."""

    def __init__(self, settings: OdooSettings):
        self.settings = settings
        base_url = settings.url.rstrip("/")
        self._common = xmlrpc.client.ServerProxy(f"{base_url}/xmlrpc/2/common", allow_none=True)
        self._models = xmlrpc.client.ServerProxy(f"{base_url}/xmlrpc/2/object", allow_none=True)
        self._uid: Optional[int] = None

    def authenticate(self) -> int:
        """Authenticate and cache the Odoo user id."""
        if self._uid is None:
            uid = self._common.authenticate(
                self.settings.db,
                self.settings.username,
                self.settings.password,
                {},
            )
            if not uid:
                raise RuntimeError("Authentication against Odoo failed. Check credentials.")
            self._uid = uid
        return self._uid

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
        return self._models.execute_kw(
            self.settings.db,
            uid,
            self.settings.password,
            model,
            method,
            args,
            kwargs,
        )

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
