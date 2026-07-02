# Modularization Plan

Goal: break the five oversized files into focused modules (~≤500 lines each) with zero behavior change. Every phase is independently shippable, verified, and committed, so we can stop or roll back at any point.

## Progress (updated 02/07/2026)

- **Phase 0 — DONE** (commit 5ce2ecb): creative_market extracted to services, dead formatters deleted, `scripts/smoke_test.py` added. creatives.py 3313 → 3037 lines.
- **Phase 3 — DONE** (commit b3155ae): dashboard.js → `static/js/dashboard/main.js` as ES module (`type="module"`); utils.js, groups.js, collapsible.js extracted. Added `scripts/browser_check.ps1` (headless-Edge console/marker verification — use after every JS change).
- **Phase 4 — MOSTLY DONE** (commits 9977e07, c6ea55a, 6eb9def + 4d): compute.js (877 lines), client-data.js (622), api.js (193), cards.js (505). main.js now 3,190 lines (was 5,991). **Remaining 4e/4f (optional):** the update*/render* collaborator layer (~1,500 lines, widest DOM-handle coupling — needs per-renderer dep analysis) and creative-filter pills (cluster around syncCreativeFilterPanelsFromPayload/getSelected*). Same recipe: analysis agent → verbatim move with content-anchored script asserts → free-identifier scan → browser_check.ps1 → commit.
- **Phase 1 — sub-step (a) DONE** (commit 106fb88): routes/creatives.py (3,037 lines) → `routes/creatives/` package, 12 modules, single Blueprint in blueprint.py, endpoint names unchanged (verified against url_map). Every def moved verbatim via AST-driven generator; top-level AND function-body relative imports bumped one level. **Remaining 1(b):** consolidate the ~90%-duplicated compute pipeline shared by `dashboard()` and `creatives_api()` in pages.py into one builder (separate commit; semantic-adjacent change).
- **Phase 2 — DONE** (commit 26c7ebb): sales_service.py (2,890 lines) → `services/sales/` with 7 mixins + facade; `services/sales_service.py` is a re-export shim so no call sites changed. Verified with a differential test (old class loaded from git HEAD vs new facade, byte-identical outputs). The private-method-promotion for refresh endpoints was deliberately skipped (behavior-preserving priority) — still open.
- **Phases 5, 6 — NOT STARTED.** Phase 5 (sales-dashboard.js) is next per the agreed order; use the exact Phase 3/4 recipe (baseline browser_check on the sales tab too, module conversion, analysis agent per cluster, verbatim moves, free-identifier scan). Note sales-dashboard.js depends on window.SalesFilters from sales-filters.js and five CustomEvents — that contract must survive.

Verification per JS step: `node --check`, free-identifier scan (scratchpad scan_free_ids.js pattern), `powershell -File scripts/browser_check.ps1` (needs Flask on :5057), `python scripts/smoke_test.py`.

## The bloated files

| File | Lines | What's inside |
|---|---|---|
| `backend/static/js/dashboard.js` | 5,991 | One 6k-line `DOMContentLoaded` closure: state, formatters, 5 chart/gauge systems, client filters, creative cards, group management, tab switching, fetch layer |
| `backend/static/js/sales-dashboard.js` | 4,157 | Same shape: sales KPIs, 4 charts, 3 tables, filters, auth gating, fetch layer |
| `backend/app/routes/creatives.py` | 3,313 | 22 route handlers + service wiring + view-period math + enrichment + stats + formatters, all in one blueprint file |
| `backend/app/services/sales_service.py` | 2,890 | One class, 14 distinct clusters (invoiced, orders, subscriptions, external hours, Odoo fetch/caching, parsing) |
| `backend/templates/creatives/dashboard.html` | 1,826 | Every dashboard section + settings/email modals + an inline script in one template |
| `backend/static/js/settings.js` | 870 | Borderline; split only if touched for other reasons |

## Key facts discovered (constraints the plan must respect)

1. **Inverted dependency:** `_get_creative_market_for_month` and `_normalize_market_name` live in `routes/creatives.py` but are imported by `services/alert_service.py` and `services/comparison_service.py` via deferred imports **with silent `None` fallbacks** — if a move breaks the import, market resolution in alerts/comparisons silently turns off. Must be extracted first, to a neutral `services/` module.
2. **`dashboard()` and `creatives_api()` duplicate ~90% of their compute pipeline** (enrichment → threaded stats/aggregates/headcount/overtime/tasks). Consolidate into one shared builder during the split.
3. **Dead code:** the sales/currency/agreement formatters at `creatives.py:3125-3253` have no callers anywhere in `backend/app` (duplicates exist in sales/tasks services). Confirm and delete rather than migrate.
4. **JS has no module system today:** five plain `<script defer>` tags (base.html loads Tailwind Play CDN + Chart.js from CDN). The two dashboard files never call each other directly — all cross-file wiring is `window.*` globals (`SalesFilters`, `monthlyUtilizationData`, `showLoginModalForSales`) and CustomEvents (`salesTabActivated`, `salesFiltersChanged`, `dashboardAuthResolved`, `salesLoginSuccess`, `dashboardLoggedOut`). This contract must survive the split unchanged.
5. **Route endpoint names** (`creatives.dashboard` etc.) must not change → keep a single `creatives_bp` Blueprint object; split the file into a package whose `__init__` imports the submodules.
6. **Refresh endpoints reach into `SalesService` private methods** (`_get_invoices_total`, `_build_invoice_breakdown_with_sign`, …). Promote to public API as part of the split.
7. Threading rules baked into current code (fresh `OdooClient` per worker thread, `_new_sales_service` vs `_get_sales_service`) must be preserved verbatim.

## Mechanism choices

- **Frontend:** native ES modules (`<script type="module">`), no bundler — matches the repo's no-JS-tooling setup (npm only builds Tailwind CSS). Each big file becomes an entry module importing from a folder of modules. Modules are deferred by default; the event/global contract keeps cross-file order irrelevant.
- **Backend routes:** convert `routes/creatives.py` into package `routes/creatives/` sharing one Blueprint (endpoint names unchanged).
- **Backend sales service:** split into `services/sales/` package with `SalesService` composed from mixins — `self.`-based calls keep every call site working unchanged.

## Verification protocol (every phase)

1. `python -m py_compile` / `node --check` on all touched files.
2. Run the offline behavioral test harness (scratchpad `test_perf_changes.py` pattern — fake clients, no network).
3. Endpoint smoke test: `test_client` GETs `/`, `/api/creatives`, `/api/utilization` and asserts status 200 + expected top-level payload keys.
4. For JS phases: load the dashboard in a browser, exercise month switch, filters, each chart, settings modal.
5. One git commit per phase (revertable independently).

---

## Phase 0 — Safety net + decouple (backend, small)

- Add the endpoint smoke-test script to the repo (`backend/tests/smoke_test.py` or a `scripts/` folder) so every later phase has a one-command check.
- Extract `_get_creative_market_for_month` + `_normalize_market_name` → `services/creative_market.py`. Update `alert_service.py` and `comparison_service.py` to import from there directly (removing the silent `None` fallbacks); leave re-export shims in `routes/creatives.py`.
- Verify orphan formatters (`creatives.py:3125-3253`) are dead via grep + smoke test, then delete.
- Deliverable: creatives.py shrinks ~250 lines; the refactor's most dangerous hidden coupling is gone.

## Phase 1 — Split `routes/creatives.py` into a package (backend)

Target layout (one Blueprint, endpoint names unchanged):

```
routes/creatives/
  __init__.py        # creatives_bp + imports submodules (registration side-effects)
  deps.py            # service accessors, g-caching, lifecycle hooks, request prefetch (L241-476)
  view_period.py     # DashboardViewPeriod, MIN_MONTH, _resolve_view_period + date math (L2170-2366)
  filters.py         # market/pool + BU/SBU/pod parsing & filtering (L49-226)
  enrichment.py      # _creatives_with_availability (L2369-2640)
  stats.py           # _creatives_stats/_creatives_aggregates/_pool_stats + hour formatters + empty-state builders
  pages.py           # dashboard() + creatives_api() — consolidated onto ONE shared compute builder
  utilization_api.py # /api/utilization, refresh-monthly, warm-monthly-cache + their parse helpers
  sales_api.py       # /api/sales, refresh-invoiced, refresh-sales-orders, _strategy_and_manual_hours_for_view
  email_api.py       # email-settings GET/POST/test/send-monthly-alert
  admin_api.py       # hour-adjustments, strategy-hours, creative-groups endpoints
```

Sub-steps: (a) mechanical move into package with `__init__` re-exports; (b) dedupe the dashboard/creatives_api pipeline into one builder in `pages.py`. Do (a) and (b) as separate commits.

## Phase 2 — Split `services/sales_service.py` (backend)

```
services/sales/
  __init__.py        # exports SalesService (facade class combining mixins)
  common.py          # module-level constants/helpers, datetime parsing, agreement categorization (clusters 1/3/14)
  master_data.py     # _fetch_projects/_fetch_agreement_types/_fetch_project_tags + instance caches + label accessors (clusters 8/9)
  invoiced.py        # invoice counts/totals/series/breakdowns (clusters 2/5/6)
  orders.py          # sales-order domains/fetch/enrichment/series/dimension totals (clusters 7/10/11)
  subscriptions.py   # get_subscriptions_for_month, get_subscription_statistics (cluster 12)
  external_hours.py  # Strategy& / external hours (cluster 13)
```

Also: promote the six private methods called by refresh endpoints to public names (keep old names as thin aliases for one release). `services/sales_service.py` becomes a one-line re-export for backward compatibility.

## Phase 3 — dashboard.js: foundation + easy extractions (frontend)

- Switch `dashboard.js` script tag to `type="module"`; create `static/js/dashboard/` with `main.js` as entry (the DOMContentLoaded bootstrap + event wiring).
- Extract the leaf/self-contained clusters first, in this order:
  1. `utils.js` — formatters, date helpers, pool-label registry (L175-304, 1230-1259, 3706-3779)
  2. `state.js` — `creativeState` + the module-level mutable vars
  3. `dom.js` — element handles (L2-171)
  4. `groups.js` — creative search + group management (L5513-5917, nearly self-contained)
  5. `collapsible.js` (L1260-1326) and `monthly-utilization-chart.js` (L2309-2504)
- `main.js` still holds the rest; behavior identical. Browser-verify after each extraction.

## Phase 4 — dashboard.js: compute + render layers (frontend)

- `api.js` — `buildApiUrl`, `fetchCreatives`, month payload cache (L5185-5383)
- `client-filters.js` — client market/subscription filters + top-clients + pool summary (L353-1153)
- `creative-filters.js` — BU/market pill filters + selection getters (L3606-3705, 5013-5184)
- `compute.js` — filtered stats/aggregates/headcount/tasks/overtime/pools (L1831-2014, 2754-2850, 3780-4414)
- `render/` — cards, gauges, tables, markets, summaries (L1327-1830, 2015-2308, 2506-2753, 2851-3605, 4507-5012)
- `pipeline.js` — `renderFilteredCreatives` + `applyClientFilters` orchestrators
- End state: `main.js` is wiring only (~200 lines).

## Phase 5 — sales-dashboard.js split (frontend)

Same pattern into `static/js/sales/`: `main.js` (auth gating + event wiring, clusters 25-27), `state.js` (`salesDataCache`, `currentFilterState`, chart instances), `period.js` (quarter/month math, cluster 3), `fetch.js` (`fetchSalesData` + refresh buttons, clusters 22/24), `reapply.js` (cluster 16 + `*ForCurrentFilters` recomputes 6/7/17), `charts.js` (cluster 14), `tables/` (project table, subscriptions table, invoice/order lists: clusters 8-11, 19-20), `ui.js` (overlay/clear/verify, cluster 21). Preserve `window.SalesFilters` consumption and all CustomEvents.

## Phase 6 — Template split + asset cleanup

- Break `dashboard.html` into Jinja partials with `{% include %}`: `_creatives_section.html`, `_company_utilization.html`, `_subscriptions_section.html`, `_sales_tab.html`, `_settings_modal.html`, `_email_modal.html`; move the inline monthly-utilization script into the JS module reading the JSON data island.
- Remove the Tailwind Play CDN from base.html (first confirm `frontend/tailwind.config.js` content globs cover all templates/JS so the built `dist/styles.css` includes every class; rebuild CSS). Pin the Chart.js CDN version.
- Optionally split `settings.js` (870 lines) into email-settings vs hour-adjustments vs groups modules.

## Sequencing and effort

Backend track (0 → 1 → 2) and frontend track (3 → 4 → 5) are independent; 6 comes last. Each phase is roughly one focused working session. Recommended order if done serially: **0, 3, 4, 1, 2, 5, 6** (safety net first, then the file causing the most pain).
