"""Central configuration for Kroma."""
import os
import tempfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
IS_VERCEL = os.environ.get("VERCEL") == "1"
_default_data = Path(tempfile.gettempdir()) / "kroma_data" if IS_VERCEL else BASE_DIR / "data"
DATA_DIR = Path(os.environ.get("KROMA_DATA", os.environ.get("PROFILEHUB_DATA", _default_data)))
DB_PATH = DATA_DIR / "kroma.db" if not (DATA_DIR / "profilehub.db").exists() else DATA_DIR / "profilehub.db"
DEFAULT_PROFILES_DIR = DATA_DIR / "profiles"
EXTENSIONS_DIR = DATA_DIR / "extensions"
URBAN_VPN_DIR = EXTENSIONS_DIR / "urban_vpn"
KROMA_VPN_DIR = EXTENSIONS_DIR / "kroma_vpn"
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
