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
    password: str
    chunk_size: int
    timeout: float


class Config:
    """Default Flask configuration."""

    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
    ODOO_URL = _get_env("ODOO_URL")
    ODOO_DB = _get_env("ODOO_DB")
    ODOO_USERNAME = _get_env("ODOO_USERNAME")
    ODOO_PASSWORD = _get_env("ODOO_PASSWORD")
    ODOO_CHUNK_SIZE = int(os.getenv("ODOO_CHUNK_SIZE", "200"))
    ODOO_TIMEOUT_SECONDS = float(os.getenv("ODOO_TIMEOUT_SECONDS", "10"))
    DASHBOARD_PASSWORD = _get_env("DASHBOARD_PASSWORD", required=False, default=None)
    DASHBOARD_ALLOWED_EMAILS = _parse_email_whitelist(os.getenv("DASHBOARD_ALLOWED_EMAILS", ""))

    @classmethod
    def odoo_settings(cls) -> OdooSettings:
        """Expose Odoo connection settings as a dataclass."""
        return OdooSettings(
            url=cls.ODOO_URL,
            db=cls.ODOO_DB,
            username=cls.ODOO_USERNAME,
            password=cls.ODOO_PASSWORD,
            chunk_size=cls.ODOO_CHUNK_SIZE,
            timeout=cls.ODOO_TIMEOUT_SECONDS,
        )
