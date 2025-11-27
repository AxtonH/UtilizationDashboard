"""Overtime statistics service for creative dashboard."""
from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence

from ..config import OdooSettings
from ..integrations.odoo_client import OdooClient


class OvertimeService:
    """Calculate overtime statistics from approval requests."""

    def __init__(self, client: OdooClient):
        self.client = client

    @classmethod
    def from_settings(cls, settings: OdooSettings) -> "OvertimeService":
        """Create an OvertimeService instance from Odoo settings."""
        return cls(OdooClient(settings))

    def calculate_overtime_statistics(
        self,
        month_start: date,
        month_end: date,
        creatives: Optional[Sequence[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Calculate overtime statistics for a given month.
        
        Args:
            month_start: Start date of the month
            month_end: End date of the month
            creatives: Optional list of creatives to filter overtime by. If provided,
                      only overtime requests from these creatives will be included.
            
        Returns:
            Dictionary with total overtime hours and top projects
        """
        start_dt = datetime.combine(month_start, datetime.min.time())
        end_dt = datetime.combine(month_end + timedelta(days=1), datetime.min.time())
        
        domain = [
            ("date_start", ">=", start_dt.isoformat(sep=" ")),
            ("date_start", "<", end_dt.isoformat(sep=" ")),
            ("request_status", "=", "approved"),
        ]
        
        fields = ["id", "x_studio_hours", "x_studio_project", "date_start", "request_owner_id"]
        
        # Build creative name matching map if creatives are provided
        creative_name_map = None
        if creatives:
            creative_name_map = self._build_creative_name_map(creatives)
        
        overtime_requests = []
        try:
            for batch in self.client.search_read_chunked(
                "approval.request",
                domain=domain,
                fields=fields,
                order="date_start asc, id asc",
            ):
                overtime_requests.extend(batch)
        except Exception as e:
            # Log error and return empty result
            print(f"Error fetching overtime requests: {e}")
            return {
                "total_hours": 0.0,
                "total_hours_display": "0h",
                "top_projects": [],
                "requests": [],  # Include empty requests array for consistency
            }
        
        # Process requests and match to creatives
        processed_requests = []
        creative_id_map = {}  # Map creative names to IDs for client-side filtering
        
        if creatives:
            # Build map of normalized creative names to creative IDs
            for creative in creatives:
                name = creative.get("name")
                creative_id = creative.get("id")
                if isinstance(name, str) and name.strip() and isinstance(creative_id, int):
                    normalized = self._normalize_name(name)
                    if normalized:
                        creative_id_map[normalized] = creative_id
        
        for request in overtime_requests:
            request_owner = self._extract_request_owner_name(request.get("request_owner_id"))
            matched_creative_id = None
            
            # Match request owner to creative
            if request_owner and creative_name_map:
                matched_creative_name = self._find_matching_creative(request_owner, creative_name_map)
                if matched_creative_name:
                    normalized = self._normalize_name(matched_creative_name)
                    matched_creative_id = creative_id_map.get(normalized)
            
            # If creatives are provided, only include requests that matched a creative
            # This ensures we only show overtime for creatives retrieved from Odoo
            if creatives and matched_creative_id is None:
                continue
            
            hours = self._safe_float(request.get("x_studio_hours"))
            if hours <= 0:
                continue
            
            # Group by project
            project_field = request.get("x_studio_project")
            if isinstance(project_field, (list, tuple)) and len(project_field) >= 2:
                project_id = project_field[0]
                project_name = str(project_field[1])
            else:
                project_name = "Unassigned Project"
            
            processed_requests.append({
                "hours": hours,
                "project_name": project_name,
                "request_owner": request_owner,
                "creative_id": matched_creative_id,
            })
        
        # Calculate statistics from all matched requests
        total_hours = sum(req["hours"] for req in processed_requests)
        project_hours: Dict[str, float] = {}
        project_contributors: Dict[str, set[str]] = {}

        for req in processed_requests:
            project_name = req["project_name"]
            project_hours[project_name] = project_hours.get(project_name, 0.0) + req["hours"]
            
            contributor = req.get("request_owner")
            if contributor:
                if project_name not in project_contributors:
                    project_contributors[project_name] = set()
                project_contributors[project_name].add(contributor)
        
        # Get top 5 projects
        top_projects = sorted(
            [
                {
                    "project_name": name, 
                    "hours": hours, 
                    "hours_display": self._format_hours(hours),
                    "contributors": sorted(list(project_contributors.get(name, set())))
                }
                for name, hours in project_hours.items()
            ],
            key=lambda x: x["hours"],
            reverse=True,
        )[:5]
        
        return {
            "total_hours": total_hours,
            "total_hours_display": self._format_hours(total_hours),
            "top_projects": top_projects,
            "requests": processed_requests,  # Include individual requests for client-side filtering
        }

    def _safe_float(self, value: Any) -> float:
        """Safely convert value to float."""
        if value is None:
            return 0.0
        try:
            return float(value)
        except (ValueError, TypeError):
            return 0.0

    def _format_hours(self, hours: float) -> str:
        """Format hours as a string."""
        if hours == 0:
            return "0h"
        if hours < 1:
            minutes = int(hours * 60)
            return f"{minutes}m"
        if hours == int(hours):
            return f"{int(hours)}h"
        return f"{hours:.1f}h"
    
    def _build_creative_name_map(self, creatives: Sequence[Dict[str, Any]]) -> Dict[str, str]:
        """Build a map of normalized creative names for fuzzy matching.
        
        Args:
            creatives: List of creative dictionaries with 'name' field
            
        Returns:
            Dictionary mapping normalized names to original names
        """
        name_map: Dict[str, str] = {}
        for creative in creatives:
            name = creative.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            normalized = self._normalize_name(name)
            if normalized:
                # Store both the normalized name and original name
                name_map[normalized] = name
        return name_map
    
    def _normalize_name(self, name: str) -> str:
        """Normalize a name for comparison by lowercasing and removing extra spaces.
        
        Args:
            name: Name string to normalize
            
        Returns:
            Normalized name string
        """
        if not name:
            return ""
        # Lowercase and strip whitespace
        normalized = name.lower().strip()
        # Replace multiple spaces with single space
        normalized = " ".join(normalized.split())
        return normalized
    
    def _extract_request_owner_name(self, request_owner_field: Any) -> Optional[str]:
        """Extract the owner name from request_owner_id field.
        
        Args:
            request_owner_field: The request_owner_id field value (can be list/tuple or string)
            
        Returns:
            Owner name string or None if not found
        """
        if not request_owner_field:
            return None
        
        if isinstance(request_owner_field, (list, tuple)) and len(request_owner_field) >= 2:
            # Odoo typically returns [id, name] for many2one fields
            return str(request_owner_field[1])
        elif isinstance(request_owner_field, str):
            return request_owner_field
        
        return None
    
    def _matches_creative(self, request_owner_name: str, creative_name_map: Dict[str, str]) -> bool:
        """Check if a request owner name matches any creative using fuzzy matching.
        
        Args:
            request_owner_name: Name from request_owner_id field
            creative_name_map: Map of normalized creative names
            
        Returns:
            True if the request owner matches a creative, False otherwise
        """
        return self._find_matching_creative(request_owner_name, creative_name_map) is not None
    
    def _find_matching_creative(self, request_owner_name: str, creative_name_map: Dict[str, str]) -> Optional[str]:
        """Find the matching creative name for a request owner using fuzzy matching.
        
        Args:
            request_owner_name: Name from request_owner_id field
            creative_name_map: Map of normalized creative names to original names
            
        Returns:
            Original creative name if match found, None otherwise
        """
        if not request_owner_name:
            return None
        
        normalized_owner = self._normalize_name(request_owner_name)
        if not normalized_owner:
            return None
        
        # Strategy 1: Exact match after normalization
        if normalized_owner in creative_name_map:
            return creative_name_map[normalized_owner]
        
        # Strategy 2: Check if request owner name is contained in any creative name
        # This handles cases like "Farah Hdaib" matching "Farah Mohammad SH. Hdaib"
        owner_parts = normalized_owner.split()
        if len(owner_parts) >= 2:
            # Extract first and last name parts
            first_name = owner_parts[0]
            last_name = owner_parts[-1]
            
            # Check if any creative name contains both first and last name
            for normalized_creative_name, original_name in creative_name_map.items():
                if first_name in normalized_creative_name and last_name in normalized_creative_name:
                    # Additional check: ensure the order is correct (first before last)
                    first_idx = normalized_creative_name.find(first_name)
                    last_idx = normalized_creative_name.find(last_name)
                    if first_idx != -1 and last_idx != -1 and first_idx < last_idx:
                        return original_name
        
        # Strategy 3: Check if any creative name is contained in request owner name
        # This handles reverse cases
        for normalized_creative_name, original_name in creative_name_map.items():
            if normalized_creative_name in normalized_owner:
                return original_name
        
        return None

