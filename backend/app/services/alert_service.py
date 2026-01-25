"""Alert service for detecting dashboard metric imbalances."""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, List

from .sales_service import SalesService


class AlertService:
    """Service for detecting and reporting dashboard alerts."""

    def __init__(self, sales_service: SalesService):
        """Initialize the alert service.
        
        Args:
            sales_service: SalesService instance for fetching sales order data
        """
        self.sales_service = sales_service

    def detect_internal_external_imbalance(
        self,
        month_start: date,
        month_end: date,
    ) -> Dict[str, Any]:
        """Detect projects with internal hours greater than external hours.
        
        Groups sales orders by project and checks if internal hours > external hours.
        
        Args:
            month_start: First day of the month
            month_end: Last day of the month
            
        Returns:
            Dictionary with:
            - count: Number of imbalanced projects
            - projects: List of project details with imbalance information
        """
        # Get sales orders for the month
        sales_orders = self.sales_service._get_sales_order_details(month_start, month_end)
        
        if not sales_orders:
            return {
                "count": 0,
                "projects": [],
            }
        
        # Group orders by project and aggregate hours
        project_hours: Dict[str, Dict[str, Any]] = {}
        
        for order in sales_orders:
            project_name = order.get("project_name", "Unassigned Project")
            
            # Skip unassigned projects
            if project_name == "Unassigned Project":
                continue
            
            internal_hours = order.get("internal_hours", 0.0)
            external_hours = order.get("external_hours", 0.0)
            
            # Convert to float if needed
            try:
                internal_hours = float(internal_hours or 0.0)
                external_hours = float(external_hours or 0.0)
            except (ValueError, TypeError):
                internal_hours = 0.0
                external_hours = 0.0
            
            # Initialize project entry if not exists
            if project_name not in project_hours:
                project_hours[project_name] = {
                    "project_name": project_name,
                    "market": order.get("market", "Unassigned Market"),
                    "agreement_type": order.get("agreement_type", "Unknown"),
                    "internal_hours": 0.0,
                    "external_hours": 0.0,
                    "imbalance_degree": 0.0,
                }
            
            # Aggregate hours
            project_hours[project_name]["internal_hours"] += internal_hours
            project_hours[project_name]["external_hours"] += external_hours
        
        # Calculate imbalance degree and filter projects where internal > external
        imbalanced_projects = []
        for project_name, project_data in project_hours.items():
            internal = project_data["internal_hours"]
            external = project_data["external_hours"]
            imbalance_degree = internal - external
            
            # Only include projects where internal hours > external hours
            if internal > external:
                project_data["imbalance_degree"] = imbalance_degree
                imbalanced_projects.append(project_data)
        
        # Sort by imbalance degree (descending)
        imbalanced_projects.sort(key=lambda x: x["imbalance_degree"], reverse=True)
        
        return {
            "count": len(imbalanced_projects),
            "projects": imbalanced_projects,
        }
