"""CRUD for connected Google accounts."""
import uuid

from database.db import db, now_iso
from modules.google_auth import token_manager as tm

_LIST_SQL = """
SELECT a.*,
  (SELECT id FROM browser_profiles WHERE account_id=a.id ORDER BY created_at LIMIT 1) AS profile_id,
  (SELECT profile_name FROM browser_profiles WHERE account_id=a.id ORDER BY created_at LIMIT 1) AS profile_name,
  (SELECT COUNT(*) FROM browser_profiles WHERE account_id=a.id) AS profile_count
FROM google_accounts a
"""


def upsert_account(creds, info: dict) -> tuple[str, bool]:
    """Save/update an account from OAuth result. Returns (account_id, created)."""
    google_id = info["sub"]
    now = now_iso()
    scopes = " ".join(creds.scopes or [])
    with db() as conn:
        existing = conn.execute(
            "SELECT id, refresh_token_encrypted FROM google_accounts WHERE google_id=?", (google_id,)
        ).fetchone()
        if existing:
            # Google only returns a refresh token on consent; keep the old one if absent.
            refresh_enc = tm.encrypt(creds.refresh_token) or existing["refresh_token_encrypted"]
            conn.execute(
                """UPDATE google_accounts SET email=?, display_name=?, avatar_url=?,
                   access_token_encrypted=?, refresh_token_encrypted=?, token_expiry=?,
                   granted_scopes=?, connection_status='Connected', updated_at=? WHERE id=?""",
                (info.get("email"), info.get("name"), info.get("picture"),
                 tm.encrypt(creds.token), refresh_enc, tm.expiry_ts(creds), scopes, now, existing["id"]),
            )
            return existing["id"], False
        account_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO google_accounts(id, google_id, email, display_name, avatar_url,
               access_token_encrypted, refresh_token_encrypted, token_expiry, granted_scopes,
               connection_status, created_at, updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,'Connected',?,?)""",
            (account_id, google_id, info.get("email"), info.get("name"), info.get("picture"),
             tm.encrypt(creds.token), tm.encrypt(creds.refresh_token), tm.expiry_ts(creds),
             scopes, now, now),
        )
        return account_id, True


def _decorate(rows):
    out = []
    for r in rows:
        d = dict(r)
        d["token_status"] = tm.token_status(r)
        out.append(d)
    return out


def list_accounts(q: str = "", status: str = ""):
    sql, params, where = _LIST_SQL, [], []
    if q:
        where.append("(a.email LIKE ? OR a.display_name LIKE ?)")
        params += [f"%{q}%", f"%{q}%"]
    if status in ("Connected", "Disconnected"):
        where.append("a.connection_status=?")
        params.append(status)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY a.created_at DESC"
    with db() as conn:
        rows = conn.execute(sql, params).fetchall()
    accounts = _decorate(rows)
    if status in ("Valid", "Expired", "Revoked"):
        accounts = [a for a in accounts if a["token_status"] == status]
    return accounts


def get_account(account_id: str):
    with db() as conn:
        row = conn.execute(_LIST_SQL + " WHERE a.id=?", (account_id,)).fetchone()
    return _decorate([row])[0] if row else None


def disconnect(account_id: str) -> tuple[bool, str]:
    """Revoke at Google, wipe stored tokens, mark Disconnected (profiles are kept)."""
    _, msg = tm.revoke(account_id)
    with db() as conn:
        conn.execute(
            """UPDATE google_accounts SET access_token_encrypted=NULL, refresh_token_encrypted=NULL,
               token_expiry=NULL, connection_status='Disconnected', updated_at=? WHERE id=?""",
            (now_iso(), account_id),
        )
    return True, f"Account disconnected. {msg}"


def delete_account_row(account_id: str):
    """Delete the account row (profile rows cascade). Caller removes profile dirs first."""
    with db() as conn:
        conn.execute("DELETE FROM google_accounts WHERE id=?", (account_id,))
