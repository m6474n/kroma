"""Firebase Admin SDK client using kroma-admin.json for full Super Admin operations."""
from pathlib import Path
from datetime import datetime, timezone

import config
from modules.auth.plans import get_plan

_admin_app = None
_db_client = None


def _get_admin_key_path() -> Path | None:
    for candidate in (
        Path(config.BASE_DIR) / "kroma-admin.json",
        Path(__file__).resolve().parents[2] / "kroma-admin.json",
        Path(config.DATA_DIR) / "kroma-admin.json",
    ):
        if candidate.exists():
            return candidate
    return None


def _ensure_init():
    global _admin_app, _db_client
    if _db_client is not None:
        return True, _db_client
    key_path = _get_admin_key_path()
    if not key_path:
        return False, "kroma-admin.json not found."
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore as fb_firestore

        if not firebase_admin._apps:
            cred = credentials.Certificate(str(key_path))
            _admin_app = firebase_admin.initialize_app(cred)
        else:
            _admin_app = firebase_admin.get_app()
        _db_client = fb_firestore.client()
        return True, _db_client
    except Exception as exc:
        return False, f"Firebase Admin init error: {exc}"


def list_all_users() -> tuple[bool, list[dict] | str]:
    ok, db_or_err = _ensure_init()
    if not ok:
        return False, db_or_err
    try:
        users = []
        for doc in db_or_err.collection("users").stream():
            d = doc.to_dict() or {}
            d.setdefault("uid", doc.id)
            users.append(d)
        return True, users
    except Exception as exc:
        return False, f"Failed to list users: {exc}"


def create_user(
    email: str,
    password: str,
    username: str,
    tier: str = "starter",
    status: str = "active",
    role: str = "client",
) -> tuple[bool, str]:
    ok, db_or_err = _ensure_init()
    if not ok:
        return False, db_or_err
    try:
        from firebase_admin import auth as fb_auth

        user_rec = fb_auth.create_user(
            email=email,
            password=password,
            display_name=username or email.split("@")[0],
        )
        plan = get_plan(tier)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        doc_data = {
            "uid": user_rec.uid,
            "email": email,
            "username": username or email.split("@")[0],
            "password": password,
            "role": role,
            "membership_status": status,
            "subscription_tier": tier,
            "max_profiles": plan["max_profiles"],
            "max_automations": plan["max_automations"],
            "max_concurrent_profiles": plan["max_concurrent_profiles"],
            "subscription_expires_at": "2099-12-31T23:59:59Z",
            "created_at": now,
            "updated_at": now,
        }
        db_or_err.collection("users").document(user_rec.uid).set(doc_data)
        return True, f"Created user '{email}'."
    except Exception as exc:
        return False, f"Failed to create user: {exc}"


def update_user(uid: str, fields: dict) -> tuple[bool, str]:
    ok, db_or_err = _ensure_init()
    if not ok:
        return False, db_or_err
    try:
        db_or_err.collection("users").document(uid).set(fields, merge=True)
        return True, "User updated."
    except Exception as exc:
        return False, f"Failed to update user: {exc}"


def delete_user(uid: str) -> tuple[bool, str]:
    ok, db_or_err = _ensure_init()
    if not ok:
        return False, db_or_err
    try:
        from firebase_admin import auth as fb_auth

        try:
            fb_auth.delete_user(uid)
        except Exception:
            pass
        db_or_err.collection("users").document(uid).delete()
        return True, "User deleted."
    except Exception as exc:
        return False, f"Failed to delete user: {exc}"
