"""Kroma entry point.  Run:  python app.py"""
import os
import secrets

from flask import Flask

import config
from database.models import init_db


def create_app() -> Flask:
    config.ensure_dirs()
    init_db()

    template_dir = str(config.BUNDLE_DIR / "templates")
    static_dir = str(config.BUNDLE_DIR / "static")
    app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
    secret_key = os.environ.get("SECRET_KEY")
    if not secret_key:
        if not config.FLASK_SECRET_PATH.exists():
            try:
                config.FLASK_SECRET_PATH.parent.mkdir(parents=True, exist_ok=True)
                config.FLASK_SECRET_PATH.write_text(secrets.token_hex(32))
            except OSError:
                pass
        if config.FLASK_SECRET_PATH.exists():
            try:
                secret_key = config.FLASK_SECRET_PATH.read_text().strip()
            except OSError:
                secret_key = secrets.token_hex(32)
        else:
            secret_key = secrets.token_hex(32)
    app.secret_key = secret_key
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
