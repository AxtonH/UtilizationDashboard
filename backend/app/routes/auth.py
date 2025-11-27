"""Authentication routes for dashboard access control."""
from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request, session

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/api/verify-dashboard-password", methods=["POST"])
def verify_dashboard_password():
    """Verify the dashboard password and set session flag."""
    data = request.get_json()
    password = data.get("password", "")
    
    configured_password = current_app.config.get("DASHBOARD_PASSWORD")
    
    # If no password is configured, allow access
    if not configured_password:
        session["dashboard_authenticated"] = True
        return jsonify({"success": True, "message": "Access granted"})
    
    # Verify password
    if password == configured_password:
        session["dashboard_authenticated"] = True
        return jsonify({"success": True, "message": "Access granted"})
    else:
        return jsonify({"success": False, "message": "Incorrect password"}), 401


@auth_bp.route("/api/check-dashboard-auth", methods=["GET"])
def check_dashboard_auth():
    """Check if user is authenticated for dashboard access."""
    configured_password = current_app.config.get("DASHBOARD_PASSWORD")
    
    # If no password is configured, allow access
    if not configured_password:
        return jsonify({"authenticated": True})
    
    # Check session
    is_authenticated = session.get("dashboard_authenticated", False)
    return jsonify({"authenticated": is_authenticated})
