"""Firebase Authentication handler using Google Identity Toolkit REST API."""
import json
import os
import urllib.error
import urllib.request
from database.db import get_setting, set_setting

SIGN_IN_URL = "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={}"
SIGN_UP_URL = "https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={}"


def get_firebase_api_key() -> str:
    """Return Firebase Web API Key from env or database."""
    return os.environ.get("FIREBASE_WEB_API_KEY", "").strip() or get_setting("firebase_web_api_key", "").strip()


def set_firebase_api_key(key: str):
    set_setting("firebase_web_api_key", key.strip())


def is_firebase_configured() -> bool:
    return bool(get_firebase_api_key())


def _post_identity_api(url: str, payload: dict) -> tuple[bool, dict | str]:
    api_key = get_firebase_api_key()
    if not api_key:
        return False, "Firebase Web API Key is not configured. Please set it in Settings."

    req_url = url.format(api_key)
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        req_url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Kroma-Auth/1.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return True, data
    except urllib.error.HTTPError as exc:
        try:
            err_data = json.loads(exc.read().decode("utf-8"))
            err_msg = err_data.get("error", {}).get("message", "Authentication failed.")
            return False, _human_error(err_msg)
        except Exception:
            return False, f"Firebase HTTP error ({exc.code})."
    except Exception as exc:
        return False, f"Network error connecting to Firebase: {exc}"


def _human_error(code: str) -> str:
    # Common Firebase Auth error mappings
    code_clean = code.split(":")[0].strip()
    mapping = {
        "EMAIL_NOT_FOUND": "No account found with this email.",
        "INVALID_PASSWORD": "Incorrect password. Please try again.",
        "INVALID_LOGIN_CREDENTIALS": "Invalid email or password.",
        "USER_DISABLED": "This user account has been disabled.",
        "EMAIL_EXISTS": "An account with this email already exists.",
        "OPERATION_NOT_ALLOWED": "Email/Password sign-in is disabled in your Firebase console.",
        "TOO_MANY_ATTEMPTS_TRY_LATER": "Too many failed attempts. Please try again later.",
        "WEAK_PASSWORD": "Password is too weak. Must be at least 6 characters.",
        "INVALID_EMAIL": "Please enter a valid email address.",
        "API_KEY_SERVICE_BLOCKED": "Firebase API key is invalid or blocked.",
        "API_KEY_INVALID": "Firebase Web API key is invalid.",
    }
    return mapping.get(code_clean, f"Firebase error: {code}")


def sign_in_with_email_password(email: str, password: str) -> tuple[bool, dict | str]:
    """Authenticate with Firebase using email and password."""
    payload = {
        "email": email.strip(),
        "password": password,
        "returnSecureToken": True,
    }
    return _post_identity_api(SIGN_IN_URL, payload)


def sign_up_with_email_password(email: str, password: str) -> tuple[bool, dict | str]:
    """Register a new user in Firebase using email and password."""
    payload = {
        "email": email.strip(),
        "password": password,
        "returnSecureToken": True,
    }
    return _post_identity_api(SIGN_UP_URL, payload)

