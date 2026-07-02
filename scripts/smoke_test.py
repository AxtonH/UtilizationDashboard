"""Endpoint smoke test for the dashboard refactor.

Hits the read-only endpoints through Flask's test client against the real
backends and asserts status codes + expected top-level payload shape. Run
after every refactor phase:

    python scripts/smoke_test.py            # full run (hits Odoo, ~1 min)
    python scripts/smoke_test.py --fast     # skip the slow full-page render
"""
from __future__ import annotations

import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app import create_app  # noqa: E402

FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}{'  ' + detail if not cond else ''}")
    if not cond:
        FAILURES.append(name)


def main() -> int:
    fast = "--fast" in sys.argv
    app = create_app()
    client = app.test_client()
    current_ym = date.today().strftime("%Y-%m")

    # --- /api/creatives: the month-switch endpoint --------------------------
    t0 = time.perf_counter()
    response = client.get(f"/api/creatives?month={current_ym}")
    dt = time.perf_counter() - t0
    check("api/creatives status 200", response.status_code == 200,
          f"(got {response.status_code})")
    payload = response.get_json(silent=True) or {}
    expected_keys = {
        "creatives", "stats", "aggregates", "pool_stats", "headcount",
        "tasks_stats", "overtime_stats", "available_markets", "available_pools",
        "available_business_units", "available_sub_business_units",
        "available_pods", "use_bu_assignment_filters", "selected_month",
        "readable_month", "period_kind", "client_external_hours_all",
        "client_subscription_hours_all", "has_previous_month", "odoo_unavailable",
    }
    missing = expected_keys - set(payload.keys())
    check("api/creatives payload keys", not missing, f"(missing: {sorted(missing)})")
    check("api/creatives has creatives list",
          isinstance(payload.get("creatives"), list) and len(payload["creatives"]) > 0,
          f"(got {type(payload.get('creatives'))})")
    print(f"        ({dt:.1f}s, {len(payload.get('creatives') or [])} creatives)")

    # --- /api/utilization ----------------------------------------------------
    response = client.get(f"/api/utilization?month={current_ym}")
    check("api/utilization status 200", response.status_code == 200,
          f"(got {response.status_code})")
    util = response.get_json(silent=True) or {}
    check("api/utilization payload is dict with content",
          isinstance(util, dict) and len(util) > 0)

    # --- Supabase-backed read endpoints --------------------------------------
    for url in ("/api/creative-hour-adjustments", "/api/strategy-and-external-hours",
                "/api/creative-groups", "/api/email-settings"):
        response = client.get(url)
        check(f"{url} status 200", response.status_code == 200,
              f"(got {response.status_code})")

    # --- auth-gated endpoint must stay gated ----------------------------------
    response = client.get(f"/api/sales?month={current_ym}")
    check("api/sales unauthenticated is 401/403",
          response.status_code in (401, 403), f"(got {response.status_code})")

    # --- full server-rendered page (slow) -------------------------------------
    if not fast:
        t0 = time.perf_counter()
        response = client.get("/")
        dt = time.perf_counter() - t0
        check("GET / status 200", response.status_code == 200,
              f"(got {response.status_code})")
        html = response.data.decode("utf-8", errors="replace")
        for marker in ("data-collapsible-section", "data-settings-modal",
                       "monthly-utilization-data", "dashboard.js"):
            check(f"GET / contains {marker!r}", marker in html)
        print(f"        ({dt:.1f}s, {len(response.data) // 1024}KB)")

    print()
    if FAILURES:
        print(f"RESULT: {len(FAILURES)} FAILURE(S): {FAILURES}")
        return 1
    print("RESULT: ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
