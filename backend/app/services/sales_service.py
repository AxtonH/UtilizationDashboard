"""Backward-compatible re-export: SalesService now lives in services/sales/."""
from .sales import SalesService

__all__ = ["SalesService"]
