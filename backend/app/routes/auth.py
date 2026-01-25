"""Authentication routes for dashboard access control."""
from __future__ import annotations

from flask import Blueprint, current_app, jsonify, make_response, request, session

from ..integrations.odoo_client import OdooClient, OdooUnavailableError

auth_bp = Blueprint("auth", __name__)
ACCESS_DENIED_MESSAGE = "Access restricted. Please contact the AI team for permissions."


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
            if not _is_email_whitelisted(email):
                return jsonify({"success": False, "message": ACCESS_DENIED_MESSAGE}), 403
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
            
            response = jsonify({"success": True, "message": "Access granted"})
            
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
                            password=password
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
            return jsonify({"success": False, "message": "Invalid email or password"}), 401
    
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
    # Check session first
    is_authenticated = session.get("dashboard_authenticated", False)
    login_logged = session.get("login_event_logged", False)
    whitelist_blocked = False
    username = session.get("dashboard_user_email")

    if is_authenticated and not _is_email_whitelisted(username):
        whitelist_blocked = True
        is_authenticated = False
        login_logged = False
        _clear_dashboard_session()
    
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
                        user_id, _, _ = result
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
    if not is_authenticated and not whitelist_blocked:
        refresh_token = request.cookies.get('nasma_refresh_token')
        if refresh_token:
            try:
                from ..services.auth_token_service import AuthTokenService
                auth_token_service = AuthTokenService.from_env()
                
                result = auth_token_service.verify_refresh_token(refresh_token)
                if result:
                    user_id, username, password = result

                    if not _is_email_whitelisted(username):
                        whitelist_blocked = True
                        auth_token_service.revoke_token(refresh_token)
                        result = None
                    
                    # Verify credentials are still valid against Odoo
                    if result:
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
    
    response_payload = {"authenticated": is_authenticated}
    if whitelist_blocked:
        response_payload["message"] = ACCESS_DENIED_MESSAGE
    return jsonify(response_payload)


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
