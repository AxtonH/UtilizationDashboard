"""Local-only test server with a login-bypass route for headless verification.

Runs the real app plus /___test_login which sets an authenticated session and
redirects to the dashboard, so a headless browser can exercise the
authenticated sales render pipeline. Never deploy this; it binds to 127.0.0.1
and exists purely for local verification.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flask import redirect, session  # noqa: E402

from backend.app import create_app  # noqa: E402

app = create_app()


@app.route("/___test_login")
def ___test_login():
    allowed = (os.getenv("DASHBOARD_ALLOWED_EMAILS") or "").split(",")[0].strip()
    session["dashboard_authenticated"] = True
    session["dashboard_user_email"] = allowed or "test@prezlab.com"
    return redirect("/")


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5058)
