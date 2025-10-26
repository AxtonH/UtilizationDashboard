"""Business logic for retrieving creative employees from Odoo."""
from __future__ import annotations

from typing import Dict, List

from ..config import OdooSettings
from ..integrations.odoo_client import OdooClient

TARGET_TAGS = ("UAE", "KSA", "Nightshift")
DEPARTMENT_KEYWORD = "creative"


class EmployeeService:
    """Encapsulates employee search logic and formatting for the dashboard."""

    def __init__(self, client: OdooClient):
        self.client = client

    @classmethod
    def from_settings(cls, settings: OdooSettings) -> "EmployeeService":
        return cls(OdooClient(settings))

    def get_creatives(self) -> List[Dict[str, object]]:
        """Fetch and normalize creative employees and their tags."""
        department_ids = self._get_target_department_ids()
        if not department_ids:
            return []

        tag_map = self._get_target_tag_map()
        if not tag_map:
            return []

        domain = [
            ("department_id", "in", department_ids),
            ("category_ids", "in", list(tag_map.keys())),
            ("active", "=", True),
        ]
        fields = [
            "name",
            "category_ids",
            "department_id",
            "work_email",
            "resource_calendar_id",
            "company_id",
        ]

        creatives: List[Dict[str, object]] = []

        for batch in self.client.search_read_chunked(
            "hr.employee",
            domain=domain,
            fields=fields,
            order="name asc",
        ):
            for record in batch:
                categories = record.get("category_ids", [])
                tag_names = [tag_map[tag_id] for tag_id in categories if tag_id in tag_map]
                if not tag_names:
                    continue

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

                creatives.append(
                    {
                        "id": record.get("id"),
                        "name": record.get("name"),
                        "department": department_display,
                        "tags": tag_names,
                        "email": record.get("work_email"),
                        "resource_calendar_id": calendar_id,
                        "resource_calendar_name": calendar_name,
                        "company_id": company_id,
                        "company_name": company_name,
                    }
                )

        return creatives

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

        keyword = DEPARTMENT_KEYWORD.lower()
        exact = [dept["id"] for dept in departments if dept.get("name", "").strip().lower() == keyword]
        return exact if exact else [dept["id"] for dept in departments]

    def _get_target_tag_map(self) -> Dict[int, str]:
        """Return a mapping of tag id to display name for desired categories."""
        domain = [("name", "in", list(TARGET_TAGS))]
        categories = self.client.search_read_all(
            "hr.employee.category",
            domain=domain,
            fields=["name"],
        )
        return {category["id"]: category["name"] for category in categories}
