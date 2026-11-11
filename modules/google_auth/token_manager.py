"""Token encryption, status, refresh and revocation."""
import calendar
import json
import time

import requests
from cryptography.fernet import Fernet, InvalidToken
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from config import FERNET_KEY_PATH, REVOKE_URL, TOKEN_URI, ensure_dirs, get_client_secret_config
from database.db import db, now_iso


def _fernet() -> Fernet:
    ensure_dirs()
    if not FERNET_KEY_PATH.exists():
        FERNET_KEY_PATH.write_bytes(Fernet.generate_key())
        try:
            FERNET_KEY_PATH.chmod(0o600)
        except OSError:
            pass
    return Fernet(FERNET_KEY_PATH.read_bytes())


def encrypt(value: str | None) -> str | None:
    return _fernet().encrypt(value.encode()).decode() if value else None


def decrypt(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken:
        return None


def expiry_ts(creds) -> int | None:
    """google-auth expiry is naive UTC -> unix timestamp."""
    return calendar.timegm(creds.expiry.utctimetuple()) if creds.expiry else None


def token_status(row) -> str:
    """Valid / Expired / Revoked (derived from stored data)."""
    if row["connection_status"] != "Connected" or not row["refresh_token_encrypted"]:
        return "Revoked"
    expiry = row["token_expiry"]
    if expiry and expiry < time.time():
        return "Expired"
    return "Valid"


def _client_info() -> dict:
    data = get_client_secret_config() or {}
    return data.get("web") or data.get("installed") or {}


def refresh(account_id: str) -> tuple[bool, str]:
    with db() as conn:
        row = conn.execute("SELECT * FROM google_accounts WHERE id=?", (account_id,)).fetchone()
    if not row:
        return False, "Account not found."
    refresh_token = decrypt(row["refresh_token_encrypted"])
    if not refresh_token:
        return False, "No refresh token stored; reconnect the account."
    info = _client_info()
    if not info:
        return False, "Google OAuth client configuration missing."
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri=TOKEN_URI,
        client_id=info.get("client_id"),
        client_secret=info.get("client_secret"),
    )
    try:
        creds.refresh(Request())
    except Exception as exc:  # RefreshError, network errors
        with db() as conn:
            conn.execute(
                "UPDATE google_accounts SET refresh_token_encrypted=NULL, updated_at=? WHERE id=?",
                (now_iso(), account_id),
            )
        return False, f"Refresh failed (token likely revoked): {exc}"
    with db() as conn:
        conn.execute(
            "UPDATE google_accounts SET access_token_encrypted=?, token_expiry=?, updated_at=? WHERE id=?",
            (encrypt(creds.token), expiry_ts(creds), now_iso(), account_id),
        )
    return True, "Token refreshed."


def revoke(account_id: str) -> tuple[bool, str]:
    with db() as conn:
        row = conn.execute("SELECT * FROM google_accounts WHERE id=?", (account_id,)).fetchone()
    if not row:
        return False, "Account not found."
    token = decrypt(row["refresh_token_encrypted"]) or decrypt(row["access_token_encrypted"])
    ok, msg = True, "Token revoked at Google."
    if token:
        try:
            r = requests.post(REVOKE_URL, params={"token": token}, timeout=15)
            if r.status_code != 200:
                ok, msg = False, "Google did not confirm revocation (token may already be invalid)."
        except requests.RequestException as exc:
            ok, msg = False, f"Could not reach Google to revoke: {exc}"
    return ok, msg
