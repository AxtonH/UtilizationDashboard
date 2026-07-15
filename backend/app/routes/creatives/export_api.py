"""Excel export endpoint for creative time cards.

The frontend assembles the payload from data it already holds (dashboard
state + the bulk daily-hours response), so this endpoint only formats the
workbook — no Odoo queries per export.
"""
from __future__ import annotations

import re

from flask import current_app, jsonify, request, send_file

from ...services.timecard_export_service import build_timecards_workbook
from .blueprint import creatives_bp

_MAX_CREATIVES = 300


@creatives_bp.route("/api/creatives/export-xlsx", methods=["POST"])
def export_creative_timecards():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"success": False, "error": "Invalid payload"}), 400

    creatives = payload.get("creatives")
    if not isinstance(creatives, list) or not creatives:
        return jsonify({"success": False, "error": "No creatives selected"}), 400
    if len(creatives) > _MAX_CREATIVES:
        return jsonify({"success": False, "error": f"Too many creatives (max {_MAX_CREATIVES})"}), 400

    try:
        stream = build_timecards_workbook(payload)
    except Exception:
        current_app.logger.error("Failed to build time card export", exc_info=True)
        return jsonify({"success": False, "error": "Failed to build the export"}), 500

    month_key = re.sub(r"[^0-9A-Za-z-]", "", str(payload.get("selected_month") or "export"))
    return send_file(
        stream,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"creative-timecards-{month_key or 'export'}.xlsx",
    )
