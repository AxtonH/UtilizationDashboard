"""Business logic for retrieving creative employees from Odoo."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional
import xmlrpc.client

from ..config import OdooSettings
from ..integrations.odoo_client import OdooClient

DEPARTMENT_KEYWORD = "creative"


class EmployeeService:
    """Encapsulates employee search logic and formatting for the dashboard."""

    def __init__(self, client: OdooClient):
        self.client = client

    @classmethod
    def from_settings(cls, settings: OdooSettings) -> "EmployeeService":
        return cls(OdooClient(settings))

    def get_all_creatives(self, include_inactive: bool = True) -> List[Dict[str, object]]:
        """Fetch all creative employees (including inactive) for total count.

        Args:
            include_inactive: If True, includes inactive creatives. If False, only active.

        Returns:
            List of all creative employees
        """
        department_ids = self._get_target_department_ids()
        if not department_ids:
            return []

        domain = [
            ("department_id", "in", department_ids),
        ]

        # If include_inactive is False, filter to only active
        if not include_inactive:
            domain.append(("active", "=", True))
        
        # Base fields that should always exist
        base_fields = [
            "name",
            "department_id",
            "work_email",
            "resource_calendar_id",
            "company_id",
            "x_studio_joining_date",
            "x_studio_rf_contract_end_date",
        ]
        
        # Current market fields
        current_market_fields = [
            "x_studio_market",
            "x_studio_start_date",
            "x_studio_end_date",
            "x_studio_pool",
        ]
        
        # Previous market fields (may not exist yet)
        previous_market_fields = [
            "x_studio_rf_market_1",
            "x_studio_start_date_1",
            "x_studio_end_date_1",
            "x_studio_rf_pool_1",
            "x_studio_rf_market_2",
            "x_studio_start_date_2",
            "x_studio_end_date_2",
            "x_studio_rf_pool_2",
        ]
        
        # Test fields incrementally to determine which ones exist
        fields_to_use = base_fields.copy()
        has_current_market_fields = False
        has_previous_fields = False
        
        # Test base fields first
        try:
            self.client.execute_kw(
                "hr.employee",
                "search_read",
                [[("id", ">", 0)]],
                {"fields": base_fields, "limit": 1}
            )
        except xmlrpc.client.Fault as e:
            # If base fields fail, something is seriously wrong
            error_str = str(e)
            if "Invalid field" in error_str:
                # Try with minimal fields
                fields_to_use = ["name", "department_id", "work_email"]
            else:
                raise
        
        # Test current market fields
        try:
            test_fields = base_fields + current_market_fields
            self.client.execute_kw(
                "hr.employee",
                "search_read",
                [[("id", ">", 0)]],
                {"fields": test_fields, "limit": 1}
            )
            fields_to_use = test_fields
            has_current_market_fields = True
        except xmlrpc.client.Fault as e:
            # Current market fields don't exist, use only base fields
            error_str = str(e)
            if "Invalid field" in error_str:
                # Keep only base fields
                pass
            else:
                raise
        
        # Test previous market fields (only if current market fields exist)
        if has_current_market_fields:
            try:
                test_fields = fields_to_use + previous_market_fields
                self.client.execute_kw(
                    "hr.employee",
                    "search_read",
                    [[("id", ">", 0)]],
                    {"fields": test_fields, "limit": 1}
                )
                fields_to_use = test_fields
                has_previous_fields = True
            except xmlrpc.client.Fault as e:
                # Previous market fields don't exist, that's okay
                error_str = str(e)
                if "Invalid field" in error_str:
                    # Keep current fields without previous market fields
                    pass
                else:
                    raise

        creatives: List[Dict[str, object]] = []

        for batch in self.client.search_read_chunked(
            "hr.employee",
            domain=domain,
            fields=fields_to_use,
            order="name asc",
        ):
            for record in batch:
                department_display = None
                department_value = record.get("department_id") or []
                if isinstance(department_value, (list, tuple)) and len(department_value) >= 2:
                    department_display = department_value[1]

                calendar_value = record.get("resource_calendar_id") or []
                calendar_id = None
                calendar_name = None
                if isinstance(calendar_value, (list, tuple)) and len(calendar_value) >= 2:
                    calendar_id = calendar_value[0]
                    calendar_name = calendar_value[1]

                company_value = record.get("company_id") or []
                company_id = None
                company_name = None
                if isinstance(company_value, (list, tuple)) and len(company_value) >= 2:
                    company_id = company_value[0]
                    company_name = company_value[1]

                # Parse current market fields (only if they exist)
                current_market = None
                current_start = None
                current_end = None
                current_pool = None
                
                if has_current_market_fields:
                    current_market = self._extract_market_name(record.get("x_studio_market"))
                    current_start = self._parse_odoo_date(record.get("x_studio_start_date"))
                    current_end = self._parse_odoo_date(record.get("x_studio_end_date"))
                    current_pool = self._extract_pool_name(record.get("x_studio_pool"))
                
                # Parse previous market fields (only if they exist)
                previous_market_1 = None
                previous_start_1 = None
                previous_end_1 = None
                previous_pool_1 = None
                previous_market_2 = None
                previous_start_2 = None
                previous_end_2 = None
                previous_pool_2 = None
                
                if has_previous_fields:
                    previous_market_1 = self._extract_market_name(record.get("x_studio_rf_market_1"))
                    previous_start_1 = self._parse_odoo_date(record.get("x_studio_start_date_1"))
                    previous_end_1 = self._parse_odoo_date(record.get("x_studio_end_date_1"))
                    previous_pool_1 = self._extract_pool_name(record.get("x_studio_rf_pool_1"))
                    
                    previous_market_2 = self._extract_market_name(record.get("x_studio_rf_market_2"))
                    previous_start_2 = self._parse_odoo_date(record.get("x_studio_start_date_2"))
                    previous_end_2 = self._parse_odoo_date(record.get("x_studio_end_date_2"))
                    previous_pool_2 = self._extract_pool_name(record.get("x_studio_rf_pool_2"))

                creatives.append(
                    {
                        "id": record.get("id"),
                        "name": record.get("name"),
                        "department": department_display,
                        "email": record.get("work_email"),
                        "resource_calendar_id": calendar_id,
                        "resource_calendar_name": calendar_name,
                        "company_id": company_id,
                        "company_name": company_name,
                        "x_studio_joining_date": record.get("x_studio_joining_date"),
                        "x_studio_rf_contract_end_date": record.get("x_studio_rf_contract_end_date"),
                        # Current market fields
                        "current_market": current_market,
                        "current_market_start": current_start,
                        "current_market_end": current_end,
                        "current_pool": current_pool,
                        # Previous market 1 fields
                        "previous_market_1": previous_market_1,
                        "previous_market_1_start": previous_start_1,
                        "previous_market_1_end": previous_end_1,
                        "previous_pool_1": previous_pool_1,
                        # Previous market 2 fields
                        "previous_market_2": previous_market_2,
                        "previous_market_2_start": previous_start_2,
                        "previous_market_2_end": previous_end_2,
                        "previous_pool_2": previous_pool_2,
                        # Keep tags for backward compatibility (will be empty or legacy)
                        "tags": [],
                    }
                )

        return creatives

    def get_creatives(self) -> List[Dict[str, object]]:
        """Fetch and normalize creative employees with their market information."""
        return self.get_all_creatives(include_inactive=False)

    def _extract_market_name(self, market_field: Any) -> Optional[str]:
        """Extract market name from Odoo field (can be a list or string)."""
        if not market_field:
            return None
        if isinstance(market_field, (list, tuple)) and len(market_field) >= 2:
            return str(market_field[1]).strip() if market_field[1] else None
        if isinstance(market_field, str):
            return market_field.strip() if market_field.strip() else None
        return None
    
    def _extract_pool_name(self, pool_field: Any) -> Optional[str]:
        """Extract pool name from Odoo field (can be a list or string)."""
        if not pool_field:
            return None
        if isinstance(pool_field, (list, tuple)) and len(pool_field) >= 2:
            return str(pool_field[1]).strip() if pool_field[1] else None
        if isinstance(pool_field, str):
            return pool_field.strip() if pool_field.strip() else None
        return None

    def _parse_odoo_date(self, value: Any) -> Optional[date]:
        """Parse a date value from Odoo."""
        if value is None:
            return None
        if isinstance(value, date):
            return value
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value).date()
            except ValueError:
                try:
                    return datetime.strptime(value, "%Y-%m-%d").date()
                except ValueError:
                    return None
        return None

    def _get_target_department_ids(self) -> List[int]:
        """Locate department ids that match the creative keyword."""
        domain = [
            ("name", "ilike", DEPARTMENT_KEYWORD),
        ]
        departments = self.client.search_read_all(
            "hr.department",
            domain=domain,
            fields=["name"],
        )
        if not departments:
            return []

        # Only return departments with name exactly "Creative" (case-insensitive)
        # This excludes "Creative Strategy" and other departments with "creative" in the name
        keyword = DEPARTMENT_KEYWORD.lower()
        exact = [dept["id"] for dept in departments if dept.get("name", "").strip().lower() == keyword]
        return exact if exact else [dept["id"] for dept in departments]
