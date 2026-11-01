"""Kroma entry point.  Run:  python app.py"""
import secrets

from flask import Flask

import config
from database.models import init_db


def create_app() -> Flask:
    config.ensure_dirs()
    init_db()

    app = Flask(__name__)
    if not config.FLASK_SECRET_PATH.exists():
        config.FLASK_SECRET_PATH.write_text(secrets.token_hex(32))
    app.secret_key = config.FLASK_SECRET_PATH.read_text()
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")

    from modules.dashboard.routes import bp
    app.register_blueprint(bp)

    @app.template_filter("dt")
    def _dt(value):
        return (value or "").replace("T", " ").replace("Z", "")[:16]

    return app


app = create_app()

if __name__ == "__main__":
    print(f"\n  Kroma running at http://localhost:{config.PORT}\n")
    app.run(host=config.HOST, port=config.PORT, debug=False)
