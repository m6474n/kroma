"""Desktop entry point for Kroma executable."""
import os
import sys
import threading
import time
import webbrowser

import config
from app import create_app


def _open_browser(url: str):
    time.sleep(1.2)
    try:
        webbrowser.open(url)
    except Exception:
        pass


def main():
    print("=" * 60)
    print("  KROMA - Multi-Profile Browser Hub & VPN Manager")
    print("=" * 60)
    print(f"  * Working directory: {config.BASE_DIR}")
    print(f"  * Database file:     {config.DB_PATH}")
    print(f"  * Dashboard URL:     http://localhost:{config.PORT}")
    print("=" * 60)
    print("  Starting server and opening dashboard in default browser...\n")

    app = create_app()

    url = f"http://localhost:{config.PORT}"
    threading.Thread(target=_open_browser, args=(url,), daemon=True).start()

    try:
        app.run(host=config.HOST, port=config.PORT, debug=False, threaded=True)
    except (KeyboardInterrupt, SystemExit):
        print("\n  Stopping Kroma...")


if __name__ == "__main__":
    main()

