"""Central configuration for Kroma."""
import os
import shutil
import sys
import tempfile
from pathlib import Path

IS_FROZEN = getattr(sys, "frozen", False)
if IS_FROZEN:
    EXE_DIR = Path(sys.executable).resolve().parent
    BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", EXE_DIR))
    if sys.platform == "darwin":
        # macOS standard app data directory (read-write safe)
        BASE_DIR = Path(os.path.expanduser("~/Library/Application Support/Kroma"))
    else:
        BASE_DIR = EXE_DIR
else:
    BASE_DIR = Path(__file__).resolve().parent
    BUNDLE_DIR = BASE_DIR


def _load_env_file():
    """Load key=value pairs from .env if present next to app/exe or inside bundle."""
    for candidate in (BASE_DIR / ".env", BUNDLE_DIR / ".env"):
        if candidate.exists():
            try:
                for line in candidate.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
            except OSError:
                pass
            break


_load_env_file()

try:
    import kroma_build_flags as _bf
except ImportError:
    _bf = None

if _bf is not None:
    if getattr(_bf, "FIREBASE_WEB_API_KEY", ""):
        os.environ.setdefault("FIREBASE_WEB_API_KEY", _bf.FIREBASE_WEB_API_KEY)
    if getattr(_bf, "FIREBASE_PROJECT_ID", ""):
        os.environ.setdefault("FIREBASE_PROJECT_ID", _bf.FIREBASE_PROJECT_ID)

IS_VERCEL = os.environ.get("VERCEL") == "1"
_cli_debug = "--debug" in sys.argv
if _cli_debug:
    RELEASE_MODE = False
    ALLOW_SETUP = True
elif _bf is not None:
    RELEASE_MODE = bool(getattr(_bf, "RELEASE_MODE", True))
    ALLOW_SETUP = bool(getattr(_bf, "ALLOW_SETUP", False))
else:
    RELEASE_MODE = os.environ.get("RELEASE_MODE", "1" if IS_FROZEN else "0") == "1"
    ALLOW_SETUP = not RELEASE_MODE and os.environ.get("ALLOW_SETUP", "1") == "1"
_default_data = Path(tempfile.gettempdir()) / "kroma_data" if IS_VERCEL else BASE_DIR / "data"
DATA_DIR = Path(os.environ.get("KROMA_DATA", os.environ.get("PROFILEHUB_DATA", _default_data)))
DB_PATH = DATA_DIR / "kroma.db" if not (DATA_DIR / "profilehub.db").exists() else DATA_DIR / "profilehub.db"
DEFAULT_PROFILES_DIR = DATA_DIR / "profiles"
EXTENSIONS_DIR = DATA_DIR / "extensions"
URBAN_VPN_DIR = EXTENSIONS_DIR / "urban_vpn"
KROMA_VPN_DIR = EXTENSIONS_DIR / "kroma_vpn"
BROWSEC_VPN_DIR = EXTENSIONS_DIR / "browsec_vpn"
TOUCH_VPN_DIR = EXTENSIONS_DIR / "touch_vpn"
CLIENT_SECRET_PATH = Path(os.environ.get("GOOGLE_CLIENT_SECRET", DATA_DIR / "client_secret.json"))
FERNET_KEY_PATH = DATA_DIR / "secret.key"
FLASK_SECRET_PATH = DATA_DIR / "flask_secret"

# Local only by default. Do not change to 0.0.0.0 unless you know what you are doing.
HOST = "127.0.0.1"
PORT = int(os.environ.get("PORT", 5000))

# Basic identity scopes only: no access to Gmail, Drive, YouTube etc.
SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]

USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
TOKEN_URI = "https://oauth2.googleapis.com/token"


def ensure_dirs():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DEFAULT_PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    EXTENSIONS_DIR.mkdir(parents=True, exist_ok=True)
    URBAN_VPN_DIR.mkdir(parents=True, exist_ok=True)
    KROMA_VPN_DIR.mkdir(parents=True, exist_ok=True)

    # Seed bundled extension files into writable DATA_DIR if missing
    bundled_kroma = BUNDLE_DIR / "data" / "extensions" / "kroma_vpn"
    if bundled_kroma.resolve() != KROMA_VPN_DIR.resolve() and bundled_kroma.exists() and not (KROMA_VPN_DIR / "manifest.json").exists():
        try:
            shutil.copytree(bundled_kroma, KROMA_VPN_DIR, dirs_exist_ok=True)
        except Exception:
            pass

    bundled_urban = BUNDLE_DIR / "data" / "extensions" / "urban_vpn"
    if bundled_urban.resolve() != URBAN_VPN_DIR.resolve() and bundled_urban.exists() and not (URBAN_VPN_DIR / "manifest.json").exists():
        try:
            shutil.copytree(bundled_urban, URBAN_VPN_DIR, dirs_exist_ok=True)
        except Exception:
            pass
