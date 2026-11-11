"""Real-time Firebase membership status stream & enforcement manager."""
import threading
import time

from modules.auth import firebase_auth, firestore

_lock = threading.Lock()
_sessions: dict[str, dict] = {}
_CHECK_TTL_SECONDS = 5.0


def register_session(
    uid: str,
    id_token: str | None = None,
    refresh_token: str | None = None,
    expires_in: int = 3600,
    profile: dict | None = None,
):
    """Register or update an authenticated Firebase user session for live monitoring."""
    if not uid or not id_token:
        return
    now = time.time()
    prof = profile if isinstance(profile, dict) else {}
    status = (prof.get("membership_status") or prof.get("subscription_status") or "active").lower()
    tier = prof.get("subscription_tier", "pro")
    with _lock:
        _sessions[uid] = {
            "id_token": id_token,
            "refresh_token": refresh_token or "",
            "expires_at": now + int(expires_in or 3600),
            "last_checked": now,
            "status": status,
            "tier": tier,
            "locked": status not in ("active", "trial"),
            "profile": prof,
        }


def unregister_session(uid: str | None):
    if not uid:
        return
    with _lock:
        _sessions.pop(uid, None)


def _refresh_token_if_needed(uid: str, entry: dict, force_refresh: bool = False) -> str | None:
    now = time.time()
    if not force_refresh and now < entry.get("expires_at", 0) - 120:
        return entry.get("id_token")

    rtok = entry.get("refresh_token")
    if not rtok:
        return entry.get("id_token")

    ok, res = firebase_auth.refresh_id_token(rtok)
    if ok and isinstance(res, dict) and res.get("id_token"):
        new_tok = res["id_token"]
        new_rtok = res.get("refresh_token") or rtok
        exp = int(res.get("expires_in") or 3600)
        with _lock:
            if uid in _sessions:
                _sessions[uid]["id_token"] = new_tok
                _sessions[uid]["refresh_token"] = new_rtok
                _sessions[uid]["expires_at"] = time.time() + exp
        return new_tok
    return entry.get("id_token")


def _trigger_lock(uid: str, status: str):
    """Immediately revoke local access and halt running browser automations."""
    with _lock:
        if uid in _sessions:
            _sessions[uid]["locked"] = True
            _sessions[uid]["status"] = status
    try:
        from modules.browser import automation_manager as atm
        atm.stop_all_automations()
    except Exception:
        pass


def check_live_status(uid: str | None, force: bool = False) -> tuple[bool, str, dict | None]:
    """Check current membership status from Firestore (cached up to 5s unless force=True).

    Returns (is_allowed, status_string, profile_dict).
    """
    if not uid:
        return True, "active", None

    with _lock:
        entry = _sessions.get(uid)
        if not entry:
            # Local-only fallback session (not Firebase-tracked)
            return True, "active", None
        if entry.get("locked"):
            return False, entry.get("status", "expired"), entry.get("profile")
        if not force and (time.time() - entry.get("last_checked", 0) < _CHECK_TTL_SECONDS):
            return True, entry.get("status", "active"), entry.get("profile")
        entry_copy = dict(entry)

    token = _refresh_token_if_needed(uid, entry_copy)
    ok_prof, prof = firestore.get_user_profile(uid, id_token=token)

    # Retry once with fresh token if auth failed (e.g. clock skew / early token expiry)
    if not ok_prof and "permission" in str(prof).lower() and entry_copy.get("refresh_token"):
        token = _refresh_token_if_needed(uid, entry_copy, force_refresh=True)
        ok_prof, prof = firestore.get_user_profile(uid, id_token=token)

    now = time.time()
    if ok_prof and isinstance(prof, dict):
        mem_status = (prof.get("membership_status") or prof.get("subscription_status") or "active").lower()
        tier = prof.get("subscription_tier", "pro")
        with _lock:
            if uid in _sessions:
                _sessions[uid]["last_checked"] = now
                _sessions[uid]["status"] = mem_status
                _sessions[uid]["tier"] = tier
                _sessions[uid]["profile"] = prof

        if mem_status not in ("active", "trial"):
            _trigger_lock(uid, mem_status)
            return False, mem_status, prof

        return True, mem_status, prof

    # If user profile document was explicitly deleted from Firestore
    if not ok_prof and "not found" in str(prof).lower():
        _trigger_lock(uid, "revoked")
        return False, "revoked", None

    # Transient network failure: update timestamp to avoid hammering, keep current state
    with _lock:
        if uid in _sessions:
            _sessions[uid]["last_checked"] = now
    return not entry_copy.get("locked", False), entry_copy.get("status", "active"), entry_copy.get("profile")
