"""Configuration helpers for application settings."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


def _get_env(key: str, *, required: bool = True, default: str | None = None) -> str | None:
    """Fetch environment variables with optional defaults and validation."""
    value = os.getenv(key, default)
    if required and (value is None or value == ""):
        raise RuntimeError(f"Missing required environment variable: {key}")
    return value


def _parse_email_whitelist(raw: str | None) -> set[str]:
    """Parse a comma/space-delimited whitelist string into normalized emails."""
    if not raw:
        return set()
    tokens = re.split(r"[,\s;]+", raw.strip())
    return {token.strip().lower() for token in tokens if token.strip()}


@dataclass(frozen=True)
class OdooSettings:
    """Strongly-typed container for Odoo connection settings."""

    url: str
    db: str
    username: str
    api_key: str
    chunk_size: int
    timeout: float


class Config:
    """Default Flask configuration."""

    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
    ODOO_URL = _get_env("ODOO_URL")
    ODOO_DB = _get_env("ODOO_DB")
    ODOO_USERNAME = _get_env("ODOO_USERNAME")
    # Odoo API key for the integration account (passed wherever XML-RPC expects
    # the password; required once 2FA is enforced on the account). Falls back to
    # the legacy ODOO_PASSWORD until the key is provisioned.
    ODOO_API_KEY = os.getenv("ODOO_API_KEY") or os.getenv("ODOO_PASSWORD")
    if not ODOO_API_KEY:
        raise RuntimeError("Missing required environment variable: ODOO_API_KEY (or legacy ODOO_PASSWORD)")
    ODOO_CHUNK_SIZE = int(os.getenv("ODOO_CHUNK_SIZE", "200"))
    ODOO_TIMEOUT_SECONDS = float(os.getenv("ODOO_TIMEOUT_SECONDS", "10"))
    DASHBOARD_PASSWORD = _get_env("DASHBOARD_PASSWORD", required=False, default=None)
    DASHBOARD_ALLOWED_EMAILS = _parse_email_whitelist(os.getenv("DASHBOARD_ALLOWED_EMAILS", ""))
    # Comma-separated hr.department names (case-insensitive) allowed to see Creatives Market filter
    DASHBOARD_MARKET_FILTER_DEPARTMENT = (os.getenv("DASHBOARD_MARKET_FILTER_DEPARTMENT") or "Operations,AI").strip()
    # Comma-separated hr.department names whose employees load into the Creatives dashboard (pools/markets from their Odoo fields)
    DASHBOARD_CREATIVE_DEPARTMENTS = (os.getenv("DASHBOARD_CREATIVE_DEPARTMENTS") or "Creative,Creative Strategy").strip()
    # Optional per-department SBU restriction for the dashboard roster.
    # Format: "Department:SBU" with "|" between multiple SBUs and ";" between
    # departments, e.g. "Product:Purple - Creative|Explore;Ops:Design".
    # Departments not listed are unrestricted. Employees in a restricted
    # department stay on the roster only if ANY of their SBU assignment slots
    # (current or previous) matches an allowed SBU (case-insensitive).
    DASHBOARD_DEPARTMENT_SBU_FILTER = (os.getenv("DASHBOARD_DEPARTMENT_SBU_FILTER") or "").strip()

    @classmethod
    def department_sbu_filter(cls) -> dict[str, frozenset[str]]:
        """Parse DASHBOARD_DEPARTMENT_SBU_FILTER into {department: allowed SBUs} (lowercased)."""
        out: dict[str, frozenset[str]] = {}
        for entry in (cls.DASHBOARD_DEPARTMENT_SBU_FILTER or "").split(";"):
            entry = entry.strip()
            if not entry or ":" not in entry:
                continue
            department, _, sbus = entry.partition(":")
            allowed = frozenset(s.strip().lower() for s in sbus.split("|") if s.strip())
            if department.strip() and allowed:
                out[department.strip().lower()] = allowed
        return out

    @classmethod
    def odoo_settings(cls) -> OdooSettings:
        """Expose Odoo connection settings as a dataclass."""
        return OdooSettings(
            url=cls.ODOO_URL,
            db=cls.ODOO_DB,
            username=cls.ODOO_USERNAME,
            api_key=cls.ODOO_API_KEY,
            chunk_size=cls.ODOO_CHUNK_SIZE,
            timeout=cls.ODOO_TIMEOUT_SECONDS,
        )
