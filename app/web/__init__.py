"""Flask app factory."""
from __future__ import annotations

import logging
from typing import Callable, Optional

from flask import Flask

log = logging.getLogger(__name__)

# callback สำหรับปุ่ม "scrape now" — main.py inject เข้ามา (map source → fn)
ScrapeTrigger = Callable[[str], None]


def create_app(scrape_trigger: Optional[ScrapeTrigger] = None) -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config["scrape_trigger"] = scrape_trigger

    from .routes import bp

    app.register_blueprint(bp)
    return app


if __name__ == "__main__":
    from ..config import settings, setup_logging

    setup_logging()
    create_app().run(host="127.0.0.1", port=settings.flask_port, debug=True)
