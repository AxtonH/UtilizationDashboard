"""Application factory for the creatives utilization dashboard."""
from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from flask import Flask


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

    return app


def register_blueprints(app: Flask) -> None:
    """Register all Flask blueprints for modular routing."""
    from .routes.creatives import creatives_bp

    app.register_blueprint(creatives_bp)
