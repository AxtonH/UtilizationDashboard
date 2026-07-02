"""Module-level constants/helpers and parsing/formatting mixin methods."""
from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple
import re
from ...integrations.odoo_client import OdooClient


# sale.order.line — Order Date SOL v1; used only for external-hours sales-order scope.
EXTERNAL_HOURS_SOL_LINE_DATETIME_FIELD = "x_studio_related_field_642_1j455dnkh"

def _datetime_in_gmt3_month(
    dt: datetime,
    start_date: date,
    end_date: date,
    *,
    gmt3_offset_hours: int = 3,
) -> bool:
    gmt3_offset = timedelta(hours=gmt3_offset_hours)
    cal = (dt + gmt3_offset).date()
    return start_date <= cal <= end_date

# product.product IDs: exclude confirmed sale orders that include any line with one of these products.
# Aligns with Odoo domain ("order_line.product_id", "not in", [...]).
EXCLUDED_ORDER_LINE_PRODUCT_IDS: Tuple[int, ...] = (
    625,
    626,
    627,
    658,
    659,
    660,
    668,
    700,
    714,
    718,
    719,
    720,
    721,
    722,
)

def _parse_odoo_datetime_field(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        clean = value.replace("T", " ").split(".")[0].strip()
        try:
            return datetime.strptime(clean, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            try:
                return datetime.strptime(clean[:10], "%Y-%m-%d")
            except ValueError:
                return None
    return None

def _parent_order_date_in_gmt3_month(order: Mapping[str, Any], start_date: date, end_date: date) -> bool:
    dt = _parse_odoo_datetime_field(order.get("date_order"))
    if dt is None:
        return False
    return _datetime_in_gmt3_month(dt, start_date, end_date)


class CommonMixin:
    """Module-level constants/helpers and parsing/formatting mixin methods."""

    @staticmethod
    def _infer_account_type(tags: Iterable[Any]) -> str:
        """Infer account type from tag labels."""
        normalized_tags = []
        for tag in tags or []:
            if isinstance(tag, str):
                normalized_tags.append(tag.strip().lower())
        for tag in normalized_tags:
            if "non-key" in tag or "non key" in tag:
                return "non-key"
        for tag in normalized_tags:
            if "key account" in tag:
                return "key"
        return "non-key"

    @staticmethod
    def _canonical_agreement_label(raw: Optional[str]) -> str:
        if not raw:
            return "Unknown"
        val = str(raw).strip().lower()
        if "retainer" in val or "subscription" in val:
            return "Retainer"
        if "framework" in val:
            return "Framework"
        if "ad hoc" in val or "adhoc" in val or "ad-hoc" == val:
            return "Ad Hoc"
        return "Unknown"

    def _parse_odoo_date(self, value: Any) -> Optional[date]:
        """Parse Odoo date value to Python date object.
        
        Args:
            value: Odoo date value (string in YYYY-MM-DD format or False/None)
            
        Returns:
            date object or None if invalid/False
        """
        if not value or value is False:
            return None
        
        if isinstance(value, date):
            return value
        
        if isinstance(value, str):
            try:
                return datetime.strptime(value.split()[0], "%Y-%m-%d").date()
            except (ValueError, AttributeError):
                pass
        
        return None

    def _parse_odoo_datetime(self, value: Any) -> Optional[datetime]:
        """Parse Odoo datetime value to Python datetime object."""
        if not value or value is False:
            return None

        if isinstance(value, datetime):
            return value

        if isinstance(value, date):
            # If it's a date object, convert to datetime at midnight
            return datetime.combine(value, datetime.min.time())

        if isinstance(value, str):
            try:
                # Try ISO format first
                return datetime.fromisoformat(value.replace("T", " "))
            except ValueError:
                try:
                    return datetime.strptime(value.split(".")[0], "%Y-%m-%d %H:%M:%S")
                except (ValueError, AttributeError):
                    pass

        return None

    def _format_hours_minutes(self, hours: float) -> str:
        """Format a float hour value as HH:MM."""
        if not hours or hours <= 0:
            return "0:00"
        total_minutes = int(round(hours * 60))
        h = total_minutes // 60
        m = total_minutes % 60
        return f"{h}:{m:02d}"

    def _categorize_agreement_type(self, agreement_type: Any, tags: Any = None) -> str:
        """Categorize agreement type into Retainer, Framework, Ad Hoc, or Unknown.
        
        Args:
            agreement_type: The agreement type string or value
            tags: Optional list of tags
            
        Returns:
            One of: "Retainer", "Framework", "Ad Hoc", "Unknown"
        """
        tokens = self._extract_agreement_tokens(agreement_type)
        if isinstance(tags, (list, tuple, set)):
            for tag in tags:
                tokens.extend(self._extract_agreement_tokens(tag))
        
        normalized = [token.lower() for token in tokens if token]
        
        # Check for retainer
        for token in normalized:
            if any(key in token for key in ("retainer", "subscription", "subscr")):
                return "Retainer"
        
        # Check for framework
        for token in normalized:
            if "framework" in token:
                return "Framework"
        
        # Check for ad hoc
        for token in normalized:
            if "ad-hoc" in token or "adhoc" in token or "ad hoc" in token:
                return "Ad Hoc"
        
        return "Unknown"

    def _extract_agreement_tokens(self, raw: Any) -> List[str]:
        """Extract tokens from agreement type string.
        
        Args:
            raw: Agreement type value (string, list, etc.)
            
        Returns:
            List of token strings
        """
        if raw is None:
            return []
        if isinstance(raw, str):
            stripped = raw.strip()
            if not stripped:
                return []
            parts = re.split(r"[,/&|]+", stripped)
            return [part.strip() for part in parts if part.strip()]
        if isinstance(raw, (list, tuple, set)):
            tokens: List[str] = []
            for item in raw:
                tokens.extend(self._extract_agreement_tokens(item))
            return tokens
        return []
