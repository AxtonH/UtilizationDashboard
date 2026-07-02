"""SalesService facade composed from focused mixins.

Split from the former 2,890-line services/sales_service.py. All methods
moved verbatim into mixins; self.* calls resolve via the MRO, so no call
sites changed. services/sales_service.py re-exports SalesService.
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple
import re
from ...integrations.odoo_client import OdooClient
from .statistics import SalesStatisticsMixin
from .invoiced import InvoicedMixin
from .orders import SalesOrdersMixin
from .subscriptions import SubscriptionsMixin
from .external_hours import ExternalHoursMixin
from .master_data import MasterDataMixin
from .common import CommonMixin


class SalesService(
    SalesStatisticsMixin,
    InvoicedMixin,
    SalesOrdersMixin,
    SubscriptionsMixin,
    ExternalHoursMixin,
    MasterDataMixin,
    CommonMixin,
):
    """Calculate sales statistics from Odoo invoices."""

    def __init__(self, odoo_client: OdooClient):
        self.odoo_client = odoo_client
        self._project_cache: Dict[int, Dict[str, Any]] = {}
        self._agreement_cache: Dict[int, str] = {}
        self._tag_cache: Dict[int, str] = {}


__all__ = ["SalesService"]
