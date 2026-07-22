"""Interactive Odoo web-session login with TOTP (2FA) support.

Ported from Nasma's production-tested OdooService. Used ONLY to verify a
user's identity at dashboard login: Odoo accounts with two-factor
authentication enabled reject password-based XML-RPC, so the login step
drives Odoo's web login flow instead (/web/session/authenticate, then the
/web/login/totp challenge). Data retrieval stays on the integration
account's XML-RPC client (odoo_client.py).

All functions are stateless and use one-shot ``requests`` calls: no shared
Session object, so no process-wide cookie jar that could leak one user's
Odoo session into another user's login (the exact bug Nasma had to fix).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_TIMEOUT = 10

# Login outcome statuses
SUCCESS = "success"
TOTP_REQUIRED = "totp_required"
INVALID = "invalid"
EXPIRED = "expired"  # pre-auth session gone; user must restart from the password step
ERROR = "error"


@dataclass(frozen=True)
class WebAuthResult:
    """Outcome of a web-session login step."""

    status: str  # SUCCESS | TOTP_REQUIRED | INVALID | ERROR
    message: str
    session_id: Optional[str] = None
    user_id: Optional[int] = None
    pre_session_id: Optional[str] = None
    trusted_device_key: Optional[str] = None


def _base_url(url: str) -> str:
    # A trailing slash in ODOO_URL produces '//web/...' URLs.
    return (url or "").rstrip("/")


def _fetch_session_uid(url: str, session_id: str) -> Optional[int]:
    """Ask Odoo for the uid bound to a session. Returns None if the session
    is not fully authenticated (e.g. parked pending a 2FA challenge)."""
    try:
        resp = requests.post(
            f"{_base_url(url)}/web/session/get_session_info",
            json={"jsonrpc": "2.0", "method": "call", "params": {}, "id": 1},
            cookies={"session_id": session_id},
            timeout=_TIMEOUT,
        )
        if resp.status_code == 200:
            info = resp.json().get("result") or {}
            uid = info.get("uid") if isinstance(info, dict) else None
            return uid or None
    except Exception as e:
        logger.debug("get_session_info probe failed: %s", e)
    return None


def authenticate(
    url: str,
    db: str,
    username: str,
    password: str,
    trusted_device_key: Optional[str] = None,
) -> WebAuthResult:
    """Password step of an interactive Odoo login.

    ``trusted_device_key`` is Odoo's auth_totp ``td_id`` cookie value from a
    previous "remember this device" TOTP verification; presenting it lets a
    2FA account authenticate fully in one step (~90 days validity).

    Outcomes:
    - SUCCESS: fully authenticated; ``session_id`` and ``user_id`` set.
    - TOTP_REQUIRED: password accepted, Odoo wants the 6-digit code;
      ``pre_session_id`` must be passed to :func:`complete_totp_login`.
    - INVALID: wrong email/password.
    - ERROR: Odoo unreachable or unexpected response.
    """
    base = _base_url(url)
    try:
        cookies = {"td_id": trusted_device_key} if trusted_device_key else {}
        response = requests.post(
            f"{base}/web/session/authenticate",
            json={
                "jsonrpc": "2.0",
                "method": "call",
                "params": {"db": db, "login": username, "password": password},
                "id": 1,
            },
            cookies=cookies,
            timeout=_TIMEOUT,
        )
        if response.status_code != 200:
            logger.debug("web authenticate HTTP %s for %s", response.status_code, username)
            return WebAuthResult(ERROR, f"Odoo responded with status {response.status_code}.")

        result = response.json()
        if "error" in result:
            # Odoo raises (rather than returning an empty result) for bad
            # credentials on some versions; treat any RPC error as invalid.
            msg = (result.get("error") or {}).get("message", "Authentication failed")
            logger.debug("web authenticate RPC error for %s: %s", username, msg)
            return WebAuthResult(INVALID, "Invalid email or password")
        if not result.get("result"):
            return WebAuthResult(INVALID, "Invalid email or password")

        session_id = response.cookies.get("session_id")
        if not session_id:
            set_cookie = response.headers.get("Set-Cookie", "")
            if "session_id=" in set_cookie:
                session_id = set_cookie.split("session_id=")[1].split(";")[0]
        if not session_id:
            logger.debug("web authenticate: no session_id issued for %s", username)
            return WebAuthResult(ERROR, "Odoo issued no session. Please try again.")

        payload = result["result"]
        user_id = payload.get("uid") if isinstance(payload, dict) else None
        if not user_id:
            # Password accepted but no uid: the signature of a 2FA account —
            # Odoo parks the session pre-auth pending the TOTP code. Probe
            # session_info once in case the session is actually complete
            # (trusted device honored), then hand back the pre-auth session.
            user_id = _fetch_session_uid(base, session_id)
        if not user_id:
            logger.debug("web authenticate: 2FA pending for %s", username)
            return WebAuthResult(
                TOTP_REQUIRED,
                "Enter the verification code from your authenticator app.",
                pre_session_id=session_id,
            )

        return WebAuthResult(SUCCESS, "Authentication successful", session_id=session_id, user_id=int(user_id))

    except requests.exceptions.Timeout:
        return WebAuthResult(ERROR, "Connection to Odoo timed out. Please try again.")
    except requests.exceptions.ConnectionError:
        return WebAuthResult(ERROR, "Unable to reach Odoo. Please try again later.")
    except Exception as e:
        logger.warning("web authenticate unexpected error: %s", e)
        return WebAuthResult(ERROR, "An error occurred during authentication.")


def complete_totp_login(url: str, pre_session_id: str, code: str) -> WebAuthResult:
    """Submit the TOTP code for a pre-auth session (second login step).

    Drives Odoo's /web/login/totp form: fetch it for the CSRF token, post
    the code with remember=1 (so Odoo issues a trusted-device key reused for
    silent re-authentication), then decide success SEMANTICALLY: different
    Odoo versions answer with different statuses/redirects, and the ground
    truth is whether a session now has a uid. Odoo may rotate the session id
    on finalize, so the rotated id is probed first, then the original.
    """
    base = _base_url(url)
    try:
        code = re.sub(r"\s+", "", str(code or ""))
        if not code:
            return WebAuthResult(INVALID, "Verification code is required.")
        totp_url = f"{base}/web/login/totp"
        cookies = {"session_id": pre_session_id}

        # 1. Fetch the TOTP form for the CSRF token.
        page = requests.get(totp_url, cookies=cookies, timeout=_TIMEOUT, allow_redirects=False)
        if page.status_code in (301, 302, 303):
            # Pre-auth session no longer at the challenge — either expired,
            # or a previous attempt already finalized it without us noticing.
            logger.debug(
                "TOTP form GET redirected (status=%s location=%r)",
                page.status_code, page.headers.get("Location", ""),
            )
            user_id = _fetch_session_uid(base, pre_session_id)
            if user_id:
                return WebAuthResult(
                    SUCCESS, "Authentication successful",
                    session_id=pre_session_id, user_id=int(user_id),
                )
            return WebAuthResult(EXPIRED, "Your login attempt expired. Please enter your password again.")

        match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page.text or "")
        if not match:
            match = re.search(r'value="([^"]+)"[^>]*name="csrf_token"', page.text or "")
        if not match:
            logger.warning("TOTP: csrf_token not found on /web/login/totp page")
            return WebAuthResult(ERROR, "Could not start the verification step. Please try again.")

        # 2. Submit the code; remember=1 requests a trusted-device key. The
        #    session cookie Odoo may set on this response is the rotated,
        #    finalized session.
        resp = requests.post(
            totp_url,
            data={
                "totp_token": code,
                "csrf_token": match.group(1),
                "remember": "1",
                "redirect": "/web",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            cookies=cookies,
            timeout=_TIMEOUT,
            allow_redirects=False,
        )
        rotated_sid = resp.cookies.get("session_id")
        td_key = resp.cookies.get("td_id")
        logger.debug(
            "TOTP verify response status=%s location=%r rotated_sid=%s td=%s",
            resp.status_code, resp.headers.get("Location", ""),
            "yes" if rotated_sid else "no", "yes" if td_key else "no",
        )

        # 3. Probe for an authenticated session.
        for candidate_sid in filter(None, [rotated_sid, pre_session_id]):
            user_id = _fetch_session_uid(base, candidate_sid)
            if user_id:
                return WebAuthResult(
                    SUCCESS, "Authentication successful",
                    session_id=candidate_sid, user_id=int(user_id),
                    trusted_device_key=td_key,
                )

        # No authenticated session anywhere — the code really was wrong.
        return WebAuthResult(INVALID, "Invalid verification code. Please try again.")

    except requests.exceptions.Timeout:
        return WebAuthResult(ERROR, "Connection to Odoo timed out. Please try again.")
    except Exception as e:
        logger.warning("TOTP verification unexpected error: %s", e)
        return WebAuthResult(ERROR, "An error occurred during verification.")
