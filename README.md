# Creatives Dashboard

A modular Flask + Tailwind CSS dashboard that surfaces creatives filtered from Odoo (`hr.employee`) with chunked data retrieval to handle large datasets, monthly availability calculations, and time-off adjustments.

## Prerequisites

- Python 3.11+ (recommended)
- Node.js 18+ (for Tailwind build tooling)

## Getting Started

1. **Create your virtual environment and install Python dependencies**

   ```bash
   python -m venv .venv
   .\.venv\Scripts\activate  # Windows
   pip install -r backend/requirements.txt
   ```

2. **Install frontend tooling and build Tailwind assets**

   ```bash
   cd frontend
   npm install
   npm run build:css
   ```

   Use `npm run dev:css` during local development to watch for template/JS changes. The compiled CSS is emitted to `backend/static/dist/styles.css`.

3. **Configure environment variables**

   Create a `.env` file with the required values:

   ```env
   ODOO_URL=<your-odoo-url>
   ODOO_DB=<your-odoo-db>
   ODOO_USERNAME=<your-odoo-username>
   ODOO_PASSWORD=<your-odoo-password>
   # Optional:
   # ODOO_CHUNK_SIZE=200
   # ODOO_TIMEOUT_SECONDS=10
  # CLIENT_SERIES_MONTH_WINDOW=6  # Optional cap on client dashboard monthly series
   # SECRET_KEY=change-me
   ```

4. **Run the Flask app**

   ```bash
   # Option A: via Flask CLI
   flask --app backend.wsgi run --reload

   # Option B: convenience runner (opens browser automatically)
   python run.py
   ```

   The dashboard is served at http://127.0.0.1:5000/.

## Deploying to GitHub

1. Initialize git and set the remote (the repository is currently empty: https://github.com/AxtonH/UtilizationDashboard):

   ```bash
   git init
   git remote add origin https://github.com/AxtonH/UtilizationDashboard.git
   ```

2. Ensure artifacts are built and tracked (CSS is already in `backend/static/dist/styles.css`):

   ```bash
   cd frontend && npm ci && npm run build:css && cd ..
   ```

3. Commit and push:

   ```bash
   git add .
   git commit -m "Initial import: Flask creatives dashboard"
   git branch -M main
   git push -u origin main
   ```

4. Keep your `.env` local and never commit it. Configure secrets on your deployment target as needed.

## Architecture Overview

- `backend/app/` - Flask application factory, configuration, integration and service layers.
  - `integrations/odoo_client.py` provides chunk-aware access to Odoo via XML-RPC.
  - `services/employee_service.py` encapsulates creative filtering by department and tag.
  - `services/availability_service.py` computes monthly base hours, time off, and availability per creative.
  - `services/planning_service.py` aggregates planning slots into monthly planned hours per creative.
  - `routes/creatives.py` exposes both HTML and JSON endpoints using the service layer.
- `backend/templates/` - Jinja templates (base layout + creatives dashboard).
- `backend/static/js/dashboard.js` - Client-side refresh logic that consumes the JSON endpoint.
- `frontend/src/styles.css` - Tailwind source compiled into `backend/static/dist/styles.css`.

## Notes & Next Steps

- The service layer isolates Odoo-specific logic so adding new dashboard widgets is straightforward.
- Chunk size defaults to 200; adjust via `ODOO_CHUNK_SIZE` for different throughput needs.
- The client dashboard timeseries now covers every month up to the selected month; set `CLIENT_SERIES_MONTH_WINDOW` to cap the window if Odoo API calls begin to slow down.
- Consider adding caching or persistence if the creatives list grows beyond what real-time pulls can handle.
- Add authentication/authorization before exposing this dashboard publicly.
- Public holidays are derived from company-wide resource calendar leaves; ensure each entity maintains accurate entries for precise availability.
- Planned hours rely on `planning.slot` records with consistent resource naming; mismatches between resource labels and employee names will be skipped.
