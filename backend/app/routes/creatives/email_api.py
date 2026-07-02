"""Email settings and alert-report endpoints."""
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
from .deps import (
    _get_availability_service,
    _get_comparison_service,
    _get_employee_service,
    _get_planning_service,
    _get_sales_service,
    _get_timesheet_service,
)
from .view_period import _month_bounds, _resolve_month


@creatives_bp.route("/api/email-settings", methods=["GET"])
def get_email_settings_api():
    """Get current email settings."""
    try:
        email_settings_service = EmailSettingsService.from_env()
        settings = email_settings_service.get_settings()
        
        if settings:
            # Convert date/time strings to proper format
            # Ensure boolean values are properly converted
            internal_external_imbalance_enabled = settings.get("internal_external_imbalance_enabled", False)
            if isinstance(internal_external_imbalance_enabled, str):
                internal_external_imbalance_enabled = internal_external_imbalance_enabled.lower() in ("true", "t", "1")
            else:
                internal_external_imbalance_enabled = bool(internal_external_imbalance_enabled)
            
            enabled = settings.get("enabled", False)
            if isinstance(enabled, str):
                enabled = enabled.lower() in ("true", "t", "1")
            else:
                enabled = bool(enabled)
            
            overbooking_enabled = settings.get("overbooking_enabled", False)
            if isinstance(overbooking_enabled, str):
                overbooking_enabled = overbooking_enabled.lower() in ("true", "t", "1")
            else:
                overbooking_enabled = bool(overbooking_enabled)
            
            underbooking_enabled = settings.get("underbooking_enabled", False)
            if isinstance(underbooking_enabled, str):
                underbooking_enabled = underbooking_enabled.lower() in ("true", "t", "1")
            else:
                underbooking_enabled = bool(underbooking_enabled)
            
            subscription_hours_alert_enabled = settings.get("subscription_hours_alert_enabled", False)
            if isinstance(subscription_hours_alert_enabled, str):
                subscription_hours_alert_enabled = subscription_hours_alert_enabled.lower() in ("true", "t", "1")
            else:
                subscription_hours_alert_enabled = bool(subscription_hours_alert_enabled)
            
            result = {
                "recipients": settings.get("recipients", []),
                "cc_recipients": settings.get("cc_recipients", []),
                "send_date": settings.get("send_date"),
                "send_time": settings.get("send_time"),
                "enabled": enabled,
                "internal_external_imbalance_enabled": internal_external_imbalance_enabled,
                "overbooking_enabled": overbooking_enabled,
                "underbooking_enabled": underbooking_enabled,
                "subscription_hours_alert_enabled": subscription_hours_alert_enabled,
            }
            return jsonify({"success": True, "settings": result})
        else:
            return jsonify({
                "success": True,
                "settings": {
                    "recipients": [],
                    "cc_recipients": [],
                    "send_date": None,
                "send_time": None,
                "enabled": False,
                "internal_external_imbalance_enabled": False,
                "overbooking_enabled": False,
                "underbooking_enabled": False,
                "subscription_hours_alert_enabled": False,
                }
            })
    except RuntimeError as e:
        current_app.logger.error(f"Email settings service not configured: {e}")
        return jsonify({
            "success": False,
            "error": "Email settings service not configured",
            "settings": {
                "recipients": [],
                "cc_recipients": [],
                "send_date": None,
                "send_time": None,
                "enabled": False,
                "internal_external_imbalance_enabled": False,
                "overbooking_enabled": False,
                "underbooking_enabled": False,
                "subscription_hours_alert_enabled": False,
            }
        }), 503
    except Exception as exc:
        current_app.logger.error("Error fetching email settings", exc_info=True)
        return jsonify({"success": False, "error": "Failed to fetch email settings"}), 500


@creatives_bp.route("/api/email-settings", methods=["POST"])
def save_email_settings_api():
    """Save email settings."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "No data provided"}), 400
        
        recipients = data.get("recipients", [])
        cc_recipients = data.get("cc_recipients", [])
        send_date_str = data.get("send_date")
        send_time_str = data.get("send_time")
        enabled = data.get("enabled", True)
        internal_external_imbalance_enabled = data.get("internal_external_imbalance_enabled", False)
        overbooking_enabled = data.get("overbooking_enabled", False)
        underbooking_enabled = data.get("underbooking_enabled", False)
        subscription_hours_alert_enabled = data.get("subscription_hours_alert_enabled", False)
        
        # Validate recipients
        if not recipients or len(recipients) == 0:
            return jsonify({"success": False, "error": "At least one recipient is required"}), 400
        
        # Validate email addresses
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        all_emails = recipients + cc_recipients
        for email in all_emails:
            if not re.match(email_pattern, email):
                return jsonify({"success": False, "error": f"Invalid email address: {email}"}), 400
        
        # Parse date and time
        send_date = None
        if send_date_str:
            try:
                send_date = datetime.strptime(send_date_str, "%Y-%m-%d").date()
            except ValueError:
                return jsonify({"success": False, "error": "Invalid date format. Use YYYY-MM-DD"}), 400
        
        send_time = None
        if send_time_str:
            try:
                send_time = datetime.strptime(send_time_str, "%H:%M").time()
            except ValueError:
                return jsonify({"success": False, "error": "Invalid time format. Use HH:MM"}), 400
        
        # Save settings
        email_settings_service = EmailSettingsService.from_env()
        success = email_settings_service.save_settings(
            recipients=recipients,
            cc_recipients=cc_recipients,
            send_date=send_date,
            send_time=send_time,
            enabled=enabled,
            internal_external_imbalance_enabled=internal_external_imbalance_enabled,
            overbooking_enabled=overbooking_enabled,
            underbooking_enabled=underbooking_enabled,
            subscription_hours_alert_enabled=subscription_hours_alert_enabled,
        )
        
        if success:
            return jsonify({"success": True, "message": "Email settings saved successfully"})
        else:
            return jsonify({"success": False, "error": "Failed to save email settings"}), 500
            
    except RuntimeError as e:
        current_app.logger.error(f"Email settings service not configured: {e}")
        return jsonify({
            "success": False,
            "error": "Email settings service not configured"
        }), 503
    except Exception as exc:
        current_app.logger.error("Error saving email settings", exc_info=True)
        return jsonify({"success": False, "error": "Failed to save email settings"}), 500


@creatives_bp.route("/api/email-settings/test", methods=["POST"])
def test_email_settings_api():
    """Send an alert report email (test mode)."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "No data provided"}), 400
        
        recipients = data.get("recipients", [])
        cc_recipients = data.get("cc_recipients", [])
        internal_external_imbalance_enabled = data.get("internal_external_imbalance_enabled", False)
        overbooking_enabled = data.get("overbooking_enabled", False)
        underbooking_enabled = data.get("underbooking_enabled", False)
        subscription_hours_alert_enabled = data.get("subscription_hours_alert_enabled", False)
        test_month_str = data.get("test_month")  # Format: YYYY-MM or None
        
        # Validate recipients
        if not recipients or len(recipients) == 0:
            return jsonify({"success": False, "error": "At least one recipient is required"}), 400
        
        # Validate email addresses
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        all_emails = recipients + cc_recipients
        for email in all_emails:
            if not re.match(email_pattern, email):
                return jsonify({"success": False, "error": f"Invalid email address: {email}"}), 400
        
        # Parse test month or use current month
        if test_month_str:
            try:
                # Parse YYYY-MM format
                year, month = map(int, test_month_str.split('-'))
                selected_month = date(year, month, 1)
            except (ValueError, TypeError):
                return jsonify({"success": False, "error": "Invalid month format. Use YYYY-MM"}), 400
        else:
            # Use current month if not specified
            selected_month = _resolve_month()
        
        month_start, month_end = _month_bounds(selected_month)
        
        # Get alert data if enabled
        internal_external_imbalance = None
        overbooking = None
        underbooking = None
        declining_utilization_trend = None
        subscription_hours_alert = None
        
        # Initialize alert service with required services
        sales_service = _get_sales_service()
        employee_service = _get_employee_service()
        availability_service = _get_availability_service()
        planning_service = _get_planning_service()
        timesheet_service = _get_timesheet_service()
        comparison_service = _get_comparison_service()
        
        alert_service = AlertService(
            sales_service,
            employee_service=employee_service,
            availability_service=availability_service,
            planning_service=planning_service,
            timesheet_service=timesheet_service,
            comparison_service=comparison_service,
        )
        
        # Always check for declining utilization trend (no toggle needed - always enabled)
        declining_utilization_trend = alert_service.detect_declining_utilization_trend(
            month_start, month_end
        )
        
        if internal_external_imbalance_enabled:
            internal_external_imbalance = alert_service.detect_internal_external_imbalance(
                month_start, month_end
            )
        
        if overbooking_enabled:
            overbooking = alert_service.detect_overbooking(
                month_start, month_end
            )
        
        if underbooking_enabled:
            underbooking = alert_service.detect_underbooking(
                month_start, month_end
            )
        
        if subscription_hours_alert_enabled:
            subscription_hours_alert = alert_service.detect_subscription_hours_alert(
                month_start, month_end
            )
        
        # Send alert report
        email_service = EmailService.from_env()
        success = email_service.send_alert_report(
            to_recipients=recipients,
            month_start=month_start,
            month_end=month_end,
            internal_external_imbalance=internal_external_imbalance,
            overbooking=overbooking,
            underbooking=underbooking,
            declining_utilization_trend=declining_utilization_trend,
            subscription_hours_alert=subscription_hours_alert,
            cc_recipients=cc_recipients if cc_recipients else None,
        )
        
        if success:
            return jsonify({"success": True, "message": "Alert report sent successfully"})
        else:
            return jsonify({"success": False, "error": "Failed to send alert report"}), 500
            
    except RuntimeError as e:
        current_app.logger.error(f"Email service not configured: {e}")
        return jsonify({
            "success": False,
            "error": "Email service not configured. Please check Azure credentials."
        }), 503
    except Exception as exc:
        current_app.logger.error("Error sending alert report", exc_info=True)
        return jsonify({
            "success": False,
            "error": f"Failed to send alert report: {str(exc)}"
        }), 500


@creatives_bp.route("/api/email-settings/send-monthly-alert", methods=["POST"])
def send_monthly_alert_api():
    """Send monthly alert report based on saved settings (for cron jobs).
    
    This endpoint reads settings from the database and sends all enabled alerts in one email.
    Railway's cron scheduler should call this endpoint monthly.
    """
    try:
        # Get settings from database
        email_settings_service = EmailSettingsService.from_env()
        settings = email_settings_service.get_settings()
        
        if not settings:
            current_app.logger.warning("No email settings found in database")
            return jsonify({
                "success": False,
                "error": "No email settings configured"
            }), 404
        
        # Check if alerts are enabled
        if not settings.get("enabled", False):
            current_app.logger.info("Email alerts are disabled in settings")
            return jsonify({
                "success": True,
                "message": "Email alerts are disabled"
            })
        
        recipients = settings.get("recipients", [])
        if not recipients or len(recipients) == 0:
            current_app.logger.warning("No recipients configured for email alerts")
            return jsonify({
                "success": False,
                "error": "No recipients configured"
            }), 400
        
        cc_recipients = settings.get("cc_recipients", [])
        
        # Get enabled alert types
        internal_external_imbalance_enabled = settings.get("internal_external_imbalance_enabled", False)
        overbooking_enabled = settings.get("overbooking_enabled", False)
        underbooking_enabled = settings.get("underbooking_enabled", False)
        subscription_hours_alert_enabled = settings.get("subscription_hours_alert_enabled", False)
        
        # Use previous month for the alert report (typical use case)
        from datetime import datetime, timedelta
        today = datetime.now().date()
        # Get first day of previous month
        if today.month == 1:
            selected_month = date(today.year - 1, 12, 1)
        else:
            selected_month = date(today.year, today.month - 1, 1)
        
        month_start, month_end = _month_bounds(selected_month)
        
        # Get alert data if enabled
        internal_external_imbalance = None
        overbooking = None
        underbooking = None
        declining_utilization_trend = None
        subscription_hours_alert = None
        
        # Initialize alert service with required services
        sales_service = _get_sales_service()
        employee_service = _get_employee_service()
        availability_service = _get_availability_service()
        planning_service = _get_planning_service()
        timesheet_service = _get_timesheet_service()
        comparison_service = _get_comparison_service()
        
        alert_service = AlertService(
            sales_service,
            employee_service=employee_service,
            availability_service=availability_service,
            planning_service=planning_service,
            timesheet_service=timesheet_service,
            comparison_service=comparison_service,
        )
        
        # Always check for declining utilization trend (no toggle needed - always enabled)
        declining_utilization_trend = alert_service.detect_declining_utilization_trend(
            month_start, month_end
        )
        
        if internal_external_imbalance_enabled:
            internal_external_imbalance = alert_service.detect_internal_external_imbalance(
                month_start, month_end
            )
        
        if overbooking_enabled:
            overbooking = alert_service.detect_overbooking(
                month_start, month_end
            )
        
        if underbooking_enabled:
            underbooking = alert_service.detect_underbooking(
                month_start, month_end
            )
        
        if subscription_hours_alert_enabled:
            subscription_hours_alert = alert_service.detect_subscription_hours_alert(
                month_start, month_end
            )
        
        # Only send email if at least one alert has data
        has_any_alerts = (
            declining_utilization_trend is not None or
            (internal_external_imbalance and internal_external_imbalance.get("count", 0) > 0) or
            (overbooking and overbooking.get("count", 0) > 0) or
            (underbooking and underbooking.get("count", 0) > 0) or
            (subscription_hours_alert and subscription_hours_alert.get("count", 0) > 0)
        )
        
        if not has_any_alerts:
            current_app.logger.info(f"No alerts detected for {selected_month.strftime('%B %Y')}")
            return jsonify({
                "success": True,
                "message": "No alerts detected for this month"
            })
        
        # Send alert report with ALL enabled alerts in ONE email
        email_service = EmailService.from_env()
        success = email_service.send_alert_report(
            to_recipients=recipients,
            month_start=month_start,
            month_end=month_end,
            internal_external_imbalance=internal_external_imbalance,
            overbooking=overbooking,
            underbooking=underbooking,
            declining_utilization_trend=declining_utilization_trend,
            subscription_hours_alert=subscription_hours_alert,
            cc_recipients=cc_recipients if cc_recipients else None,
        )
        
        if success:
            current_app.logger.info(f"Monthly alert report sent successfully for {selected_month.strftime('%B %Y')}")
            return jsonify({
                "success": True,
                "message": f"Alert report sent successfully for {selected_month.strftime('%B %Y')}"
            })
        else:
            return jsonify({"success": False, "error": "Failed to send alert report"}), 500
            
    except RuntimeError as e:
        current_app.logger.error(f"Email service not configured: {e}")
        return jsonify({
            "success": False,
            "error": "Email service not configured. Please check Azure credentials."
        }), 503
    except Exception as exc:
        current_app.logger.error("Error sending monthly alert report", exc_info=True)
        return jsonify({
            "success": False,
            "error": f"Failed to send alert report: {str(exc)}"
        }), 500
