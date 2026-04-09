"""Authentication routes for dashboard access control."""
from __future__ import annotations

from functools import wraps

from flask import Blueprint, Response, current_app, jsonify, make_response, request, session

from ..integrations.odoo_client import OdooClient, OdooUnavailableError

auth_bp = Blueprint("auth", __name__)
ACCESS_DENIED_MESSAGE = "Access restricted. Please contact the AI team for permissions."


def require_sales_auth(f):
    """Decorator that requires authenticated + whitelisted user for Sales Dashboard access."""
    @wraps(f)
    def decorated(*args, **kwargs):
        is_authenticated = session.get("dashboard_authenticated", False)
        username = session.get("dashboard_user_email")
        if not is_authenticated or not _is_email_whitelisted(username):
            return jsonify({
                "error": "unauthorized",
                "message": "Please log in with an allowed email to access the Sales Dashboard.",
            }), 403
        return f(*args, **kwargs)
    return decorated


def _get_email_whitelist() -> set[str]:
    allowed_emails = current_app.config.get("DASHBOARD_ALLOWED_EMAILS")
    if not allowed_emails:
        return set()
    if isinstance(allowed_emails, set):
        return allowed_emails
    if isinstance(allowed_emails, str):
        tokens = [token.strip().lower() for token in allowed_emails.split(",") if token.strip()]
        return set(tokens)
    return {str(email).strip().lower() for email in allowed_emails if str(email).strip()}


def _is_email_whitelisted(email: str | None) -> bool:
    allowed_emails = _get_email_whitelist()
    if not allowed_emails:
        return True
    if not email:
        return False
    return email.strip().lower() in allowed_emails


def _clear_dashboard_session() -> None:
    session.pop("dashboard_authenticated", None)
    session.pop("dashboard_user_email", None)
    session.pop("dashboard_user_id", None)
    session.pop("login_event_logged", None)
    session.pop("dashboard_sales_eligible", None)
    session.pop("dashboard_market_filter_visible", None)


def _market_filter_target_department_lower() -> str:
    return (current_app.config.get("DASHBOARD_MARKET_FILTER_DEPARTMENT") or "Operations").strip().lower()


def _department_matches_market_filter_target(dep: object) -> bool:
    """True if Odoo department_id value matches configured market-filter department (case-insensitive)."""
    target = _market_filter_target_department_lower()
    if not target:
        return True
    if not dep:
        return False
    if isinstance(dep, (list, tuple)) and len(dep) >= 2:
        name = str(dep[1] or "").strip().lower()
    elif isinstance(dep, dict):
        name = str(dep.get("display_name") or dep.get("name") or "").strip().lower()
    else:
        return False
    return name == target


def _hr_employee_department_as_user(
    odoo_client: OdooClient, user_uid: int, user_password: str
) -> object | None:
    """Return department_id for the user's hr.employee row using that user's Odoo ACLs."""
    try:
        rows = odoo_client.execute_kw_as_user(
            int(user_uid),
            user_password,
            "hr.employee",
            "search_read",
            [[["user_id", "=", int(user_uid)]]],
            {"fields": ["department_id"], "limit": 1},
        )
    except Exception as e:
        current_app.logger.debug("hr.employee lookup (user context) for market filter failed: %s", e)
        return None
    if not rows:
        return None
    return rows[0].get("department_id")


def _compute_market_filter_visibility(
    odoo_client: OdooClient, user_uid: int | None, user_password: str | None
) -> bool:
    """Fresh visibility: integration hr.employee read first, then user-context RPC if needed."""
    if not user_uid:
        return False
    target = _market_filter_target_department_lower()
    if not target:
        return True

    uid_int = int(user_uid)
    domain = [[["user_id", "=", uid_int]]]
    read_kw = {"fields": ["department_id"], "limit": 1}

    rows: list | None = None
    try:
        rows = odoo_client.execute_kw("hr.employee", "search_read", domain, read_kw)
    except OdooUnavailableError:
        raise
    except Exception as e:
        current_app.logger.debug("hr.employee search_read (integration) for market filter: %s", e)
        rows = None

    if rows:
        return _department_matches_market_filter_target(rows[0].get("department_id"))

    if user_password:
        dep = _hr_employee_department_as_user(odoo_client, uid_int, user_password)
        return _department_matches_market_filter_target(dep) if dep is not None else False

    return False


def _password_from_refresh_cookie_for_uid(expected_uid: int) -> str | None:
    refresh_token = request.cookies.get("nasma_refresh_token")
    if not refresh_token:
        return None
    try:
        from ..services.auth_token_service import AuthTokenService

        auth_token_service = AuthTokenService.from_env()
        result = auth_token_service.verify_refresh_token(refresh_token)
        if not result:
            return None
        user_id, _username, password = result[:3]
        if int(user_id) != int(expected_uid):
            return None
        return password
    except Exception as e:
        current_app.logger.debug("refresh token read for market filter sync: %s", e)
        return None


def _sync_session_market_filter_visibility(odoo_client: OdooClient) -> None:
    """Update session flag from Odoo on each auth check (same cadence as live sales_access)."""
    uid = session.get("dashboard_user_id")
    if not uid:
        session["dashboard_market_filter_visible"] = False
        return
    password = _password_from_refresh_cookie_for_uid(int(uid))
    try:
        session["dashboard_market_filter_visible"] = _compute_market_filter_visibility(
            odoo_client, int(uid), password
        )
    except OdooUnavailableError:
        pass


def _revoke_nasma_refresh_token_cookie(response: Response) -> None:
    """Invalidate server-side refresh token and clear browser cookie."""
    refresh_token = request.cookies.get("nasma_refresh_token")
    if refresh_token:
        try:
            from ..services.auth_token_service import AuthTokenService

            AuthTokenService.from_env().revoke_token(refresh_token)
        except Exception as e:
            current_app.logger.debug("Failed to revoke refresh token: %s", e)
    response.set_cookie("nasma_refresh_token", "", expires=0)


def _get_odoo_client_for_auth() -> OdooClient:
    """Get Odoo client for authentication (uses env credentials for connection only)."""
    settings = current_app.config["ODOO_SETTINGS"]
    # Create a new client instance for auth verification
    # This uses the env credentials only for connection, not for user verification
    return OdooClient(settings)


@auth_bp.route("/api/verify-dashboard-password", methods=["POST"])
def verify_dashboard_password():
    """Verify user's Odoo credentials and set session flag."""
    data = request.get_json()
    email = data.get("email", "").strip()
    password = data.get("password", "")
    remember_me = data.get("remember_me", False)
    
    # Validate input
    if not email:
        return jsonify({"success": False, "message": "Email is required"}), 400
    
    if not password:
        return jsonify({"success": False, "message": "Password is required"}), 400
    
    # Verify credentials against Odoo
    try:
        odoo_client = _get_odoo_client_for_auth()
        is_valid = odoo_client.verify_user_credentials(email, password)
        
        if is_valid:
            # Whitelist gates Sales dashboard only; any valid Odoo user may use Creatives.
            sales_access = _is_email_whitelisted(email)
            # Get user_id first (needed for tracking and token creation)
            uid = odoo_client._common.authenticate(
                odoo_client.settings.db,
                email,
                password,
                {},
            )
            
            session["dashboard_authenticated"] = True
            session["dashboard_user_email"] = email  # Store email for reference
            if uid:
                session["dashboard_user_id"] = uid  # Store user_id for tracking
            session["login_event_logged"] = True  # Mark login as logged
            session["dashboard_sales_eligible"] = sales_access  # last known Sales whitelist state
            session["dashboard_market_filter_visible"] = _compute_market_filter_visibility(
                odoo_client, uid, password
            )

            # Log login event (non-blocking)
            if uid:
                try:
                    from ..services.login_tracking_service import LoginTrackingService
                    login_tracking = LoginTrackingService.from_env()
                    
                    # Get IP address and user agent from request
                    ip_address = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
                    if ip_address:
                        # Handle multiple IPs (take first)
                        ip_address = ip_address.split(',')[0].strip()
                    user_agent = request.headers.get('User-Agent')
                    
                    login_tracking.log_login(
                        user_id=uid,
                        username=email,
                        ip_address=ip_address,
                        user_agent=user_agent
                    )
                except Exception as e:
                    # Log error but don't fail login
                    current_app.logger.debug(f"Failed to log login event: {e}")
            
            response = make_response(
                jsonify({
                    "success": True,
                    "message": "Access granted",
                    "sales_access": sales_access,
                    "market_filter_visible": bool(session.get("dashboard_market_filter_visible")),
                })
            )
            response.headers["Cache-Control"] = "private, no-store"
            
            # Create refresh token if remember_me is checked
            if remember_me:
                try:
                    from ..services.auth_token_service import AuthTokenService
                    auth_token_service = AuthTokenService.from_env()
                    
                    # uid is already available from above
                    if uid:
                        refresh_token = auth_token_service.create_refresh_token(
                            user_id=uid,
                            username=email,
                            password=password,
                            sales_eligible=sales_access,
                        )
                        
                        # Set cookie with refresh token (1 year expiry)
                        # Use secure=True only in production (when not localhost)
                        is_production = not current_app.debug and 'localhost' not in request.host
                        response.set_cookie(
                            'nasma_refresh_token',
                            refresh_token,
                            max_age=365 * 24 * 60 * 60,  # 1 year in seconds
                            httponly=True,
                            secure=is_production,  # HTTPS only in production
                            samesite='Lax'
                        )
                except Exception as e:
                    # If token creation fails, log but don't fail login
                    current_app.logger.warning(f"Failed to create refresh token: {e}")
            
            return response
        else:
            resp = jsonify({"success": False, "message": "Invalid email or password"})
            resp.headers["Cache-Control"] = "private, no-store"
            return resp, 401
    
    except OdooUnavailableError:
        return jsonify({
            "success": False, 
            "message": "Unable to connect to Odoo. Please try again later."
        }), 503
    except Exception as e:
        current_app.logger.error(f"Error verifying credentials: {e}", exc_info=True)
        return jsonify({
            "success": False, 
            "message": "An error occurred during authentication. Please try again."
        }), 500


@auth_bp.route("/api/check-dashboard-auth", methods=["GET"])
def check_dashboard_auth():
    """Check if user is authenticated for dashboard access.
    
    Also checks for refresh token and auto-authenticates if valid.
    Tracks login events for both new and existing sessions.
    """
    # Snapshot from refresh token when Flask session is empty (see sales whitelist revocation below)
    restored_sales_snapshot: bool | None = None

    # Check session first
    is_authenticated = session.get("dashboard_authenticated", False)
    login_logged = session.get("login_event_logged", False)
    username = session.get("dashboard_user_email")
    
    # If already authenticated via session but login not logged yet, log it
    if is_authenticated and not login_logged:
        if username:
            # Try to get user_id from refresh token if available
            refresh_token = request.cookies.get('nasma_refresh_token')
            user_id = None
            
            if refresh_token:
                try:
                    from ..services.auth_token_service import AuthTokenService
                    auth_token_service = AuthTokenService.from_env()
                    result = auth_token_service.verify_refresh_token(refresh_token)
                    if result:
                        user_id = result[0]
                except Exception:
                    pass
            
            # Log login event if we have user_id (non-blocking)
            if user_id:
                try:
                    from ..services.login_tracking_service import LoginTrackingService
                    login_tracking = LoginTrackingService.from_env()
                    
                    # Get IP address and user agent from request
                    ip_address = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
                    if ip_address:
                        ip_address = ip_address.split(',')[0].strip()
                    user_agent = request.headers.get('User-Agent')
                    
                    login_tracking.log_login(
                        user_id=user_id,
                        username=username,
                        ip_address=ip_address,
                        user_agent=user_agent
                    )
                    # Mark as logged to prevent duplicate logs
                    session["login_event_logged"] = True
                except Exception as e:
                    current_app.logger.debug(f"Failed to log existing session login event: {e}")
            else:
                # If no user_id available, still mark as logged to prevent repeated attempts
                # This happens when session exists but no refresh token (rare case)
                session["login_event_logged"] = True
    
    # If not authenticated, check for refresh token
    if not is_authenticated:
        refresh_token = request.cookies.get('nasma_refresh_token')
        if refresh_token:
            try:
                from ..services.auth_token_service import AuthTokenService
                auth_token_service = AuthTokenService.from_env()
                
                result = auth_token_service.verify_refresh_token(refresh_token)
                if result:
                    user_id, username, password, restored_sales_snapshot = result

                    # Verify credentials are still valid against Odoo
                    odoo_client = _get_odoo_client_for_auth()
                    is_valid = odoo_client.verify_user_credentials(username, password)

                    if is_valid:
                        session["dashboard_authenticated"] = True
                        session["dashboard_user_email"] = username
                        session["dashboard_user_id"] = user_id  # Store user_id for tracking
                        session["login_event_logged"] = True  # Mark as logged
                        is_authenticated = True

                        # Log auto-login event (non-blocking)
                        try:
                            from ..services.login_tracking_service import LoginTrackingService
                            login_tracking = LoginTrackingService.from_env()

                            # Get IP address and user agent from request
                            ip_address = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
                            if ip_address:
                                ip_address = ip_address.split(',')[0].strip()
                            user_agent = request.headers.get('User-Agent')

                            login_tracking.log_login(
                                user_id=user_id,
                                username=username,
                                ip_address=ip_address,
                                user_agent=user_agent
                            )
                        except Exception as e:
                            current_app.logger.debug(f"Failed to log auto-login event: {e}")
                    else:
                        # Credentials invalid, revoke token
                        auth_token_service.revoke_token(refresh_token)
            except Exception as e:
                current_app.logger.debug(f"Error checking refresh token: {e}")

    # Live Sales eligibility (require_sales_auth also checks each API call)
    sales_whitelisted = bool(
        is_authenticated and username and _is_email_whitelisted(username)
    )
    sales_access = sales_whitelisted

    revoke_refresh = False
    if is_authenticated and username:
        prev_sales_eligible = session.get("dashboard_sales_eligible")
        # Session cookie may be gone but remember-me still valid — use snapshot from token row
        if prev_sales_eligible is None and restored_sales_snapshot is not None:
            prev_sales_eligible = restored_sales_snapshot
        session["dashboard_sales_eligible"] = sales_whitelisted
        if (
            bool(_get_email_whitelist())
            and prev_sales_eligible is True
            and not sales_whitelisted
        ):
            # User lost Sales whitelist while still logged in — drop remember-me token
            revoke_refresh = True

    if is_authenticated:
        try:
            _sync_session_market_filter_visibility(_get_odoo_client_for_auth())
        except Exception as e:
            current_app.logger.debug("market filter visibility sync failed: %s", e)

    payload = {
        "authenticated": is_authenticated,
        "sales_access": sales_access,
        "market_filter_visible": bool(session.get("dashboard_market_filter_visible")),
    }
    response = make_response(jsonify(payload))
    response.headers["Cache-Control"] = "private, no-store"
    if revoke_refresh:
        _revoke_nasma_refresh_token_cookie(response)
    return response


@auth_bp.route("/api/logout", methods=["POST"])
def logout():
    """Clear dashboard authentication session and revoke refresh token."""
    # Revoke refresh token if exists
    refresh_token = request.cookies.get('nasma_refresh_token')
    if refresh_token:
        try:
            from ..services.auth_token_service import AuthTokenService
            auth_token_service = AuthTokenService.from_env()
            auth_token_service.revoke_token(refresh_token)
        except Exception as e:
            current_app.logger.debug(f"Error revoking refresh token: {e}")
    
    # Clear session
    _clear_dashboard_session()
    
    # Clear cookie
    response = jsonify({"success": True, "message": "Logged out successfully"})
    response.set_cookie('nasma_refresh_token', '', expires=0)
    
    return response
