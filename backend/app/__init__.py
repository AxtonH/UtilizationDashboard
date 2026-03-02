"""Application factory for the creatives utilization dashboard."""
from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request


BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = BASE_DIR.parent / "templates"
STATIC_DIR = BASE_DIR.parent / "static"


def create_app(config_object: str | None = None) -> Flask:
    """Create and configure the Flask application."""
    load_dotenv()

    app = Flask(
        __name__,
        template_folder=str(TEMPLATE_DIR),
        static_folder=str(STATIC_DIR),
        static_url_path="/static",
    )

    if config_object:
        app.config.from_object(config_object)
    else:
        from .config import Config

        app.config.from_object(Config)
        app.config["ODOO_SETTINGS"] = Config.odoo_settings()

    register_blueprints(app)
    register_error_handlers(app)

    return app


def register_error_handlers(app: Flask) -> None:
    """Register error handlers so API routes always return JSON, not HTML."""

    def wants_json() -> bool:
        return request.path.startswith("/api/")

    @app.errorhandler(404)
    def not_found(e):
        if wants_json():
            return jsonify({"error": "not_found", "message": "The requested resource was not found."}), 404
        if hasattr(e, "get_response"):
            return e.get_response(request.environ)
        return jsonify({"error": "not_found", "message": "Not found"}), 404

    @app.errorhandler(500)
    def internal_error(e):
        if wants_json():
            return jsonify({"error": "server_error", "message": "An unexpected error occurred. Please try again."}), 500
        return (
            e.get_response(request.environ)
            if hasattr(e, "get_response")
            else ("<h1>Internal Server Error</h1>", 500)
        )


def register_blueprints(app: Flask) -> None:
    """Register all Flask blueprints for modular routing."""
    from .routes.auth import auth_bp
    from .routes.creatives import creatives_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(creatives_bp)
