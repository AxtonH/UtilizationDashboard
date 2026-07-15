"""Hour adjustments, Strategy& hours, and creative-group endpoints."""
from __future__ import annotations

import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from dataclasses import dataclass
from calendar import month_name, monthrange
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Mapping, Optional, Set, Tuple
from flask import Blueprint, current_app, g, jsonify, render_template, request, session
from ...integrations.odoo_client import OdooClient, OdooUnavailableError
from ...services.assignment_service import (
    BusinessUnitAssignment,
    creative_matches_bu_assignment_filters,
    resolve_business_unit_for_month,
    split_assignment_field_tokens,
    use_business_unit_model,
)
from ...services.availability_service import AvailabilityService, AvailabilitySummary
from ...services.employee_service import EmployeeService
from ...services.external_hours_service import ExternalHoursService
from ...services.planning_service import PlanningService
from ...services.timesheet_service import TimesheetService
from ...services.utilization_service import (
    MONTHLY_UTILIZATION_CACHE_MIN,
    UtilizationService,
    _inclusive_month_tuple_sequence,
)
from ...services.supabase_cache_service import SupabaseCacheService
from ...services.sales_cache_service import SalesCacheService
from ...services.creative_market import (
    _get_creative_market_for_month,
    _normalize_market_name,
)
from ...services.comparison_service import ComparisonService
from ...services.email_settings_service import EmailSettingsService
from ...services.creative_hour_adjustments_service import CreativeHourAdjustmentsService
from ...services.strategy_and_external_hours_service import StrategyAndExternalHoursService
from ...services.email_service import EmailService
from ...services.alert_service import AlertService
from ...services.headcount_service import HeadcountService
from ...services.new_joiner_period import parse_joining_date, period_overlaps_new_joiner_ramp
from ..auth import require_sales_auth
from .blueprint import creatives_bp


@creatives_bp.route("/api/creative-hour-adjustments", methods=["GET"])
def get_creative_hour_adjustments_api():
    """List per-employee monthly hour overrides (dashboard availability)."""
    try:
        svc = CreativeHourAdjustmentsService.from_env()
        rows = svc.list_all()
        return jsonify({"success": True, "adjustments": rows})
    except RuntimeError as e:
        current_app.logger.warning("Creative hour adjustments unavailable: %s", e)
        return jsonify({"success": False, "error": "Supabase not configured", "adjustments": []}), 503
    except Exception as exc:
        current_app.logger.error("Error loading creative hour adjustments", exc_info=True)
        return jsonify({"success": False, "error": "Failed to load adjustments", "adjustments": []}), 500


@creatives_bp.route("/api/creatives/<int:creative_id>/new-joiner-inclusion", methods=["POST"])
def set_new_joiner_inclusion_api(creative_id: int):
    """Toggle whether a ramp-period new joiner's hours count toward utilization."""
    from ...services.new_joiner_inclusions_service import NewJoinerInclusionsService

    try:
        payload = request.get_json(silent=True) or {}
        included = payload.get("included")
        if not isinstance(included, bool):
            return jsonify({"success": False, "error": "included must be a boolean"}), 400

        svc = NewJoinerInclusionsService.from_env()
        if not svc.set_inclusion(creative_id, included):
            return jsonify({"success": False, "error": "Failed to save inclusion"}), 500
        return jsonify({"success": True, "included": included})
    except RuntimeError as e:
        current_app.logger.error("New joiner inclusion save: %s", e)
        return jsonify({"success": False, "error": "Supabase not configured"}), 503
    except Exception:
        current_app.logger.error("Error saving new joiner inclusion", exc_info=True)
        return jsonify({"success": False, "error": "Failed to save inclusion"}), 500


@creatives_bp.route("/api/creative-hour-adjustments", methods=["PUT", "POST"])
def save_creative_hour_adjustments_api():
    """Replace all creative hour overrides."""
    try:
        payload = request.get_json()
        if not payload:
            return jsonify({"success": False, "error": "No data provided"}), 400
        raw = payload.get("adjustments")
        if not isinstance(raw, list):
            return jsonify({"success": False, "error": "adjustments must be a list"}), 400
        parsed: List[Tuple[int, float]] = []
        seen_ids: Set[int] = set()
        for item in raw:
            if not isinstance(item, dict):
                continue
            eid = item.get("employee_id")
            hrs = item.get("monthly_hours")
            if not isinstance(eid, int):
                try:
                    eid = int(eid)
                except (TypeError, ValueError):
                    continue
            try:
                h = float(hrs)
            except (TypeError, ValueError):
                continue
            if h < 0 or h > 400:
                return jsonify({"success": False, "error": "monthly_hours must be between 0 and 400"}), 400
            if eid in seen_ids:
                continue
            seen_ids.add(eid)
            parsed.append((eid, h))

        # Empty list = explicit "clear all". Non-empty but nothing parsed = invalid payload; do not wipe DB.
        if len(raw) > 0 and len(parsed) == 0:
            return jsonify(
                {
                    "success": False,
                    "error": "No valid adjustment rows. Existing settings were not changed.",
                }
            ), 400

        svc = CreativeHourAdjustmentsService.from_env()
        allow_clear = len(raw) == 0
        if not svc.replace_all(parsed, allow_empty_replace=allow_clear):
            return jsonify({"success": False, "error": "Failed to save adjustments"}), 500
        return jsonify({"success": True, "message": "Hour adjustments saved."})
    except RuntimeError as e:
        current_app.logger.error("Creative hour adjustments save: %s", e)
        return jsonify({"success": False, "error": "Supabase not configured"}), 503
    except Exception as exc:
        current_app.logger.error("Error saving creative hour adjustments", exc_info=True)
        return jsonify({"success": False, "error": "Failed to save adjustments"}), 500


@creatives_bp.route("/api/strategy-and-external-hours", methods=["GET"])
def get_strategy_and_external_hours_api():
    """List manual Strategy& external hours by calendar month (Supabase)."""
    try:
        svc = StrategyAndExternalHoursService.from_env()
        rows = svc.list_all()
        return jsonify({"success": True, "entries": rows})
    except RuntimeError as e:
        current_app.logger.warning("Strategy& external hours unavailable: %s", e)
        return jsonify({"success": False, "error": "Supabase not configured", "entries": []}), 503
    except Exception as exc:
        current_app.logger.error("Error loading Strategy& external hours", exc_info=True)
        return jsonify({"success": False, "error": "Failed to load entries", "entries": []}), 500


@creatives_bp.route("/api/strategy-and-external-hours", methods=["PUT", "POST"])
def save_strategy_and_external_hours_api():
    """Replace manual Strategy& external hours rows."""
    try:
        payload = request.get_json()
        if not payload:
            return jsonify({"success": False, "error": "No data provided"}), 400
        raw = payload.get("entries")
        if not isinstance(raw, list):
            return jsonify({"success": False, "error": "entries must be a list"}), 400
        parsed: List[Dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            try:
                y = int(item.get("year"))
                m = int(item.get("month"))
                sold = float(item.get("external_hours_sold") or 0)
                used = float(item.get("external_hours_used") or 0)
            except (TypeError, ValueError):
                continue
            if y < 2000 or y > 2100 or m < 1 or m > 12:
                continue
            if sold < 0 or sold > 10000000 or used < 0 or used > 10000000:
                return jsonify({"success": False, "error": "Hours must be between 0 and 10,000,000"}), 400
            parsed.append(
                {
                    "year": y,
                    "month": m,
                    "external_hours_sold": sold,
                    "external_hours_used": used,
                }
            )

        if len(raw) > 0 and len(parsed) == 0:
            return jsonify(
                {
                    "success": False,
                    "error": "No valid rows. Existing settings were not changed.",
                }
            ), 400

        svc = StrategyAndExternalHoursService.from_env()
        allow_clear = len(raw) == 0
        if not svc.replace_all(parsed, allow_empty_replace=allow_clear):
            return jsonify({"success": False, "error": "Failed to save entries"}), 500
        return jsonify({"success": True, "message": "Strategy& hours saved."})
    except RuntimeError as e:
        current_app.logger.error("Strategy& external hours save: %s", e)
        return jsonify({"success": False, "error": "Supabase not configured"}), 503
    except Exception as exc:
        current_app.logger.error("Error saving Strategy& external hours", exc_info=True)
        return jsonify({"success": False, "error": "Failed to save entries"}), 500


@creatives_bp.route("/api/creative-groups", methods=["GET"])
def get_creative_groups_api():
    """Get all saved creative groups."""
    try:
        cache_service = None
        try:
            cache_service = SupabaseCacheService.from_env()
        except RuntimeError as e:
            # Supabase not configured, log the actual error
            current_app.logger.warning(f"Supabase not configured: {e}")
            return jsonify({"groups": []})
        
        groups = cache_service.get_creative_groups()
        return jsonify({"groups": groups})
    except Exception as exc:
        current_app.logger.error("Error fetching creative groups", exc_info=True)
        return jsonify({"error": "Failed to fetch groups", "groups": []}), 500


@creatives_bp.route("/api/creative-groups", methods=["POST"])
def create_creative_group_api():
    """Create a new creative group."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        name = data.get("name", "").strip()
        creative_ids = data.get("creative_ids", [])
        
        if not name:
            return jsonify({"error": "Group name is required"}), 400
        
        if not isinstance(creative_ids, list) or len(creative_ids) == 0:
            return jsonify({"error": "At least one creative ID is required"}), 400
        
        # Validate creative IDs are integers
        try:
            creative_ids = [int(id) for id in creative_ids]
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid creative IDs"}), 400
        
        cache_service = None
        try:
            cache_service = SupabaseCacheService.from_env()
        except RuntimeError as e:
            error_msg = str(e)
            current_app.logger.error(f"Failed to initialize Supabase service: {error_msg}")
            return jsonify({"error": "Supabase not configured", "details": error_msg}), 503
        
        group = cache_service.save_creative_group(name, creative_ids)
        if group:
            return jsonify({"success": True, "group": group}), 201
        else:
            return jsonify({"error": "Failed to save group"}), 500
    except Exception as exc:
        current_app.logger.error("Error creating creative group", exc_info=True)
        return jsonify({"error": "Failed to create group"}), 500


@creatives_bp.route("/api/creative-groups/<int:group_id>", methods=["PUT"])
def update_creative_group_api(group_id: int):
    """Update an existing creative group."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        name = data.get("name", "").strip()
        creative_ids = data.get("creative_ids", [])
        
        if not name:
            return jsonify({"error": "Group name is required"}), 400
        
        if not isinstance(creative_ids, list) or len(creative_ids) == 0:
            return jsonify({"error": "At least one creative ID is required"}), 400
        
        # Validate creative IDs are integers
        try:
            creative_ids = [int(id) for id in creative_ids]
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid creative IDs"}), 400
        
        cache_service = None
        try:
            cache_service = SupabaseCacheService.from_env()
        except RuntimeError as e:
            error_msg = str(e)
            current_app.logger.error(f"Failed to initialize Supabase service: {error_msg}")
            return jsonify({"error": "Supabase not configured", "details": error_msg}), 503
        
        group = cache_service.save_creative_group(name, creative_ids, group_id)
        if group:
            return jsonify({"success": True, "group": group})
        else:
            return jsonify({"error": "Failed to update group"}), 500
    except Exception as exc:
        current_app.logger.error("Error updating creative group", exc_info=True)
        return jsonify({"error": "Failed to update group"}), 500


@creatives_bp.route("/api/creative-groups/<int:group_id>", methods=["DELETE"])
def delete_creative_group_api(group_id: int):
    """Delete a creative group."""
    try:
        cache_service = None
        try:
            cache_service = SupabaseCacheService.from_env()
        except RuntimeError as e:
            error_msg = str(e)
            current_app.logger.error(f"Failed to initialize Supabase service: {error_msg}")
            return jsonify({"error": "Supabase not configured", "details": error_msg}), 503
        
        success = cache_service.delete_creative_group(group_id)
        if success:
            return jsonify({"success": True})
        else:
            return jsonify({"error": "Failed to delete group"}), 500
    except Exception as exc:
        current_app.logger.error("Error deleting creative group", exc_info=True)
        return jsonify({"error": "Failed to delete group"}), 500
