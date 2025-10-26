"""Convenience runner that launches the dashboard and opens it in a browser."""
from __future__ import annotations

import os
import threading
import time
import webbrowser

from backend.app import create_app


def _open_browser(url: str, delay: float = 1.0) -> None:
    """Open the default browser after a short delay to allow the server to start."""

    def launcher() -> None:
        time.sleep(delay)
        webbrowser.open(url, new=2, autoraise=True)

    threading.Thread(target=launcher, daemon=True).start()


def main() -> None:
    """Create the Flask app, open the browser, and start the development server."""
    app = create_app()
    debug = True
    host = "127.0.0.1"
    port = 5000
    url = f"http://{host}:{port}/"

    # Only open the browser once. Werkzeug sets WERKZEUG_RUN_MAIN="true" for the reloader process.
    is_reloader_process = os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    should_open_browser = not debug or not is_reloader_process
    if should_open_browser:
        _open_browser(url)

    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
