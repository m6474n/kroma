"""Profile provisioning, lifecycle and status."""
import re
import shutil
import sqlite3
import tempfile
import uuid
from pathlib import Path

from config import DEFAULT_PROFILES_DIR
from database.db import db, get_setting, now_iso
from modules.browser import chromium, process_manager as pm


def profiles_root() -> Path:
    root = Path(get_setting("profiles_dir") or DEFAULT_PROFILES_DIR)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _slug(email: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", email.split("@")[0]).strip("-") or "profile"


def _unique_name(conn, base: str) -> str:
    name, n = base, 1
    while conn.execute("SELECT 1 FROM browser_profiles WHERE profile_name=?", (name,)).fetchone():
        n += 1
        name = f"{base}-{n}"
    return name


def _set_job(conn, job_id, status, error=None, profile_id=None, done=False):
    conn.execute(
        "UPDATE profile_jobs SET job_status=?, error_message=?, profile_id=COALESCE(?, profile_id), "
        "completed_at=? WHERE id=?",
        (status, error, profile_id, now_iso() if done else None, job_id),
    )


def create_or_bind_profile(account_id: str, email: str, pre_profile_id: str | None = None) -> tuple[str, str]:
    """Create a new profile or attach a pre-provisioned directory to this account."""
    root = profiles_root()
    profile_id = pre_profile_id or str(uuid.uuid4())
    directory = root / profile_id
    directory.mkdir(parents=True, exist_ok=True)
    with db() as conn:
        existing = conn.execute(
            "SELECT id, profile_name FROM browser_profiles WHERE id=?", (profile_id,)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE browser_profiles SET account_id=?, authentication_status='Signed in', updated_at=? WHERE id=?",
                (account_id, now_iso(), profile_id),
            )
            return existing["id"], existing["profile_name"]
        name = _unique_name(conn, _slug(email))
        now = now_iso()
        conn.execute(
            """INSERT INTO browser_profiles(id, account_id, profile_name, profile_directory,
               browser_status, authentication_status, created_at, updated_at)
               VALUES(?,?,?,?,'Stopped','Signed in',?,?)""",
            (profile_id, account_id, name, str(directory), now, now),
        )
    preinstall_vpn_profile(directory)
    return profile_id, name


def preinstall_vpn_profile(profile_dir: str | Path, profile_directory_name: str | None = None):
    """Ensure official Urban VPN descriptors and pre-activation state exist in profile."""
    p_dir = Path(profile_dir)
    sub = profile_directory_name or "Default"
    vpn_ids = ("eppiocemhmnlbhjplcgkofciiegomcon", "eppiocemhmnlbhjplcgkfeedignghneo")

    # 1. Write External Extensions JSON descriptors
    ext_dir = p_dir / "External Extensions"
    try:
        ext_dir.mkdir(parents=True, exist_ok=True)
        descriptor = '{\n  "external_update_url": "https://clients2.google.com/service/update2/crx"\n}\n'
        for ext_id in vpn_ids:
            desc_file = ext_dir / f"{ext_id}.json"
            if not desc_file.exists():
                desc_file.write_text(descriptor, encoding="utf-8")
    except Exception:
        pass

    # 2. Pre-seed LevelDB / Extension state if another profile has configured it
    try:
        dest_local = p_dir / sub / "Local Extension Settings"
        for ext_id in vpn_ids:
            target_folder = dest_local / ext_id
            if target_folder.exists() and any(target_folder.iterdir()):
                continue

            source_found = None
            for p in list_profiles():
                cand = Path(p["profile_directory"]) / (p.get("profile_directory_name") or "Default") / "Local Extension Settings" / ext_id
                if cand.exists() and any(cand.iterdir()):
                    source_found = cand
                    break

            if source_found:
                target_folder.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(source_found, target_folder, dirs_exist_ok=True)
    except Exception:
        pass
def import_from_system_chrome() -> list[dict]:
    """Link all profiles found in default installed Google Chrome into ProfileHub directly."""
    sys_profiles = chromium.list_system_chrome_profiles()
    if not sys_profiles:
        return []
    data_dir = chromium.default_chrome_user_data_dir()
    if not data_dir:
        return []
    
    results = []
    for sp in sys_profiles:
        dir_name = sp["dir_name"]
        email = sp["email"] or sp["name"] or dir_name
        
        with db() as conn:
            # Check if this account already exists
            acc = None
            if sp["gaia_id"]:
                acc = conn.execute("SELECT id, email FROM google_accounts WHERE google_id=?", (sp["gaia_id"],)).fetchone()
            if not acc and sp["email"]:
                acc = conn.execute("SELECT id, email FROM google_accounts WHERE email=?", (sp["email"],)).fetchone()
            
            now = now_iso()
            if not acc:
                account_id = str(uuid.uuid4())
                google_id = sp["gaia_id"] or f"local-{uuid.uuid4()}"
                conn.execute(
                    """INSERT INTO google_accounts(id, google_id, email, display_name,
                       connection_status, created_at, updated_at)
                       VALUES(?,?,?,?,'Connected',?,?)""",
                    (account_id, google_id, sp["email"] or f"{dir_name}@chrome.local", sp["name"], now, now),
                )
            else:
                account_id = acc["id"]
            
            # Check if profile with this account or profile_directory_name exists
            existing = conn.execute(
                "SELECT id, profile_name FROM browser_profiles WHERE account_id=? OR (profile_directory=? AND profile_directory_name=?)",
                (account_id, data_dir, dir_name),
            ).fetchone()
            if existing:
                # Update existing row to point to native profile_directory_name
                conn.execute(
                    "UPDATE browser_profiles SET profile_directory=?, profile_directory_name=?, authentication_status='Signed in', updated_at=? WHERE id=?",
                    (data_dir, dir_name, now, existing["id"]),
                )
                results.append({"name": sp["name"], "email": sp["email"], "status": "imported", "message": existing["profile_name"]})
                continue
            
            profile_id = str(uuid.uuid4())
            profile_name = _unique_name(conn, _slug(sp["email"] or sp["name"]))
            conn.execute(
                """INSERT INTO browser_profiles(id, account_id, profile_name, profile_directory,
                   profile_directory_name, browser_status, authentication_status, created_at, updated_at)
                   VALUES(?,?,?,?,?,'Stopped','Signed in',?,?)""",
                (profile_id, account_id, profile_name, data_dir, dir_name, now, now),
            )
            preinstall_vpn_profile(data_dir, dir_name)
            results.append({"name": sp["name"], "email": sp["email"], "status": "imported", "message": profile_name})
            
    return results


# ------------------------------------------------------------------ generate
def generate(account_ids: list[str], force: bool = False) -> list[dict]:
    """Provision one profile directory per account. Returns a result row per account."""
    results = []
    root = profiles_root()
    for account_id in account_ids:
        job_id = str(uuid.uuid4())
        with db() as conn:
            acc = conn.execute(
                "SELECT id, email FROM google_accounts WHERE id=?", (account_id,)
            ).fetchone()
            conn.execute(
                "INSERT INTO profile_jobs(id, account_id, job_status, started_at) VALUES(?,?,?,?)",
                (job_id, account_id, "running", now_iso()),
            )
            if not acc:
                _set_job(conn, job_id, "failed", "Account not found", done=True)
                results.append({"email": account_id, "status": "failed", "message": "Account not found"})
                continue
            existing = conn.execute(
                "SELECT id FROM browser_profiles WHERE account_id=?", (account_id,)
            ).fetchone()
            if existing and not force:
                _set_job(conn, job_id, "skipped", "Profile already exists", existing["id"], done=True)
                results.append({"email": acc["email"], "status": "skipped",
                                "message": "Profile already exists"})
                continue
            profile_id = str(uuid.uuid4())
            directory = root / profile_id
            try:
                directory.mkdir(parents=True, exist_ok=False)
                name = _unique_name(conn, _slug(acc["email"]))
                now = now_iso()
                conn.execute(
                    """INSERT INTO browser_profiles(id, account_id, profile_name, profile_directory,
                       browser_status, authentication_status, created_at, updated_at)
                       VALUES(?,?,?,?,'Stopped','Pending',?,?)""",
                    (profile_id, account_id, name, str(directory), now, now),
                )
                preinstall_vpn_profile(directory)
                _set_job(conn, job_id, "completed", None, profile_id, done=True)
                results.append({"email": acc["email"], "status": "created", "message": name})
            except (OSError, sqlite3.Error) as exc:
                shutil.rmtree(directory, ignore_errors=True)
                _set_job(conn, job_id, "failed", str(exc), done=True)
                results.append({"email": acc["email"], "status": "failed", "message": str(exc)})
    return results


# ------------------------------------------------------------------- queries
_PROFILE_SQL = """
SELECT p.*, a.email, a.display_name, a.avatar_url
FROM browser_profiles p JOIN google_accounts a ON a.id = p.account_id
"""


def _with_live_status(rows):
    rmap = pm.running_map()
    out = []
    for r in rows:
        d = dict(r)
        pname = d.get("profile_directory_name")
        d["browser_status"] = "Running" if pm.is_running(d["profile_directory"], pname, rmap) else "Stopped"
        out.append(d)
    return out


def list_profiles(q: str = ""):
    sql, params = _PROFILE_SQL, []
    if q:
        sql += " WHERE p.profile_name LIKE ? OR a.email LIKE ?"
        params = [f"%{q}%", f"%{q}%"]
    sql += " ORDER BY p.created_at DESC"
    with db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return _with_live_status(rows)


def get_profile(profile_id: str):
    with db() as conn:
        row = conn.execute(_PROFILE_SQL + " WHERE p.id=?", (profile_id,)).fetchone()
    return _with_live_status([row])[0] if row else None


def stats() -> dict:
    with db() as conn:
        total_accounts = conn.execute("SELECT COUNT(*) FROM google_accounts").fetchone()[0]
    profiles = list_profiles()
    from modules.google_auth import account_manager as am
    attention = sum(
        1 for a in am.list_accounts()
        if a["connection_status"] != "Connected" or a["token_status"] != "Valid"
    )
    running = sum(1 for p in profiles if p["browser_status"] == "Running")
    return {
        "accounts": total_accounts,
        "profiles": len(profiles),
        "running": running,
        "stopped": len(profiles) - running,
        "attention": attention,
    }


# ----------------------------------------------------------------- lifecycle
def launch_browser(
    profile_dir: str,
    email: str = "",
    url: str | None = None,
    profile_directory_name: str | None = None,
    proxy_config: dict | None = None,
) -> tuple[bool, str]:
    chrome = chromium.find_chrome()
    if not chrome:
        return False, "Chrome/Chromium not found. Set its path in Settings."
    Path(profile_dir).mkdir(parents=True, exist_ok=True)
    try:
        cmd = chromium.build_command(
            chrome,
            profile_dir,
            email=email,
            url=url,
            profile_directory_name=profile_directory_name,
            proxy_config=proxy_config,
        )
        pm.launch(cmd, profile_dir=profile_dir, profile_directory_name=profile_directory_name)
    except OSError as exc:
        return False, f"Could not start browser: {exc}"
    return True, "Launched."


def get_profile_proxy(p: dict) -> dict | None:
    """Resolve effective proxy config for a profile (profile-specific or global default)."""
    if p.get("proxy_enabled") and p.get("proxy_host") and p.get("proxy_port"):
        return {
            "profile_id": p["id"],
            "proxy_type": p.get("proxy_type") or "http",
            "proxy_host": p["proxy_host"],
            "proxy_port": p["proxy_port"],
            "proxy_user": p.get("proxy_user"),
            "proxy_pass": p.get("proxy_pass"),
        }
    def_enabled = get_setting("default_proxy_enabled")
    def_host = get_setting("default_proxy_host")
    def_port = get_setting("default_proxy_port")
    if def_enabled == "1" and def_host and def_port:
        return {
            "profile_id": "global",
            "proxy_type": get_setting("default_proxy_type") or "http",
            "proxy_host": def_host,
            "proxy_port": int(def_port),
            "proxy_user": get_setting("default_proxy_user"),
            "proxy_pass": get_setting("default_proxy_pass"),
        }
    return None


def launch(profile_id: str, url: str | None = None) -> tuple[bool, str]:
    p = get_profile(profile_id)
    if not p:
        return False, "Profile not found."
    if p["browser_status"] == "Running":
        return True, f"{p['profile_name']} is already running."
    target_url = url
    if not target_url:
        target_url = "https://myaccount.google.com" if p["authentication_status"] == "Signed in" else chromium.login_url(p["email"])

    proxy_cfg = get_profile_proxy(p)
    ok, msg = launch_browser(
        p["profile_directory"],
        email=p["email"],
        url=target_url,
        profile_directory_name=p.get("profile_directory_name"),
        proxy_config=proxy_cfg,
    )
    if not ok:
        return False, msg
    _touch(profile_id, "Running")
    return True, f"Launched {p['profile_name']}."


def update_profile_proxy(
    profile_id: str,
    enabled: bool,
    proxy_type: str = "http",
    host: str | None = None,
    port: int | None = None,
    user: str | None = None,
    password: str | None = None,
) -> bool:
    with db() as conn:
        conn.execute(
            """UPDATE browser_profiles
               SET proxy_enabled=?, proxy_type=?, proxy_host=?, proxy_port=?,
                   proxy_user=?, proxy_pass=?, updated_at=?
               WHERE id=?""",
            (
                1 if enabled else 0,
                proxy_type or "http",
                host.strip() if host else None,
                int(port) if port else None,
                user.strip() if user else None,
                password.strip() if password else None,
                now_iso(),
                profile_id,
            ),
        )
    return True


def bulk_set_proxy(
    profile_ids: list[str],
    enabled: bool,
    proxy_type: str = "http",
    host: str | None = None,
    port: int | None = None,
    user: str | None = None,
    password: str | None = None,
) -> int:
    with db() as conn:
        count = 0
        for pid in profile_ids:
            conn.execute(
                """UPDATE browser_profiles
                   SET proxy_enabled=?, proxy_type=?, proxy_host=?, proxy_port=?,
                       proxy_user=?, proxy_pass=?, updated_at=?
                   WHERE id=?""",
                (
                    1 if enabled else 0,
                    proxy_type or "http",
                    host.strip() if host else None,
                    int(port) if port else None,
                    user.strip() if user else None,
                    password.strip() if password else None,
                    now_iso(),
                    pid,
                ),
            )
            count += 1
    return count


def close(profile_id: str) -> tuple[bool, str]:
    p = get_profile(profile_id)
    if not p:
        return False, "Profile not found."
    pm.close(p["profile_directory"], profile_directory_name=p.get("profile_directory_name"))
    _touch(profile_id, "Stopped")
    refresh_auth(profile_id)
    return True, f"Closed {p['profile_name']}."


def restart(profile_id: str) -> tuple[bool, str]:
    ok, msg = close(profile_id)
    return launch(profile_id) if ok else (ok, msg)


def delete(profile_id: str) -> tuple[bool, str]:
    p = get_profile(profile_id)
    if not p:
        return False, "Profile not found."
    pm.close(p["profile_directory"], profile_directory_name=p.get("profile_directory_name"))
    # Only remove folder from disk if it is an isolated ProfileHub profile (not system Chrome User Data)
    if not p.get("profile_directory_name"):
        shutil.rmtree(p["profile_directory"], ignore_errors=True)
    with db() as conn:
        conn.execute("DELETE FROM browser_profiles WHERE id=?", (profile_id,))
    return True, f"Deleted {p['profile_name']}."


def _touch(profile_id: str, browser_status: str):
    with db() as conn:
        conn.execute(
            "UPDATE browser_profiles SET browser_status=?, updated_at=? WHERE id=?",
            (browser_status, now_iso(), profile_id),
        )


# --------------------------------------------------------------- auth status
def set_auth_status(profile_id: str, status: str):
    with db() as conn:
        conn.execute(
            "UPDATE browser_profiles SET authentication_status=?, updated_at=? WHERE id=?",
            (status, now_iso(), profile_id),
        )


def detect_google_session(profile_dir: str) -> bool | None:
    """Best effort: look for Google session cookie *names* (values are encrypted) in the
    profile's cookie DB. Returns True/False, or None if the DB can't be read (e.g. locked)."""
    base = Path(profile_dir) / "Default"
    for rel in ("Network/Cookies", "Cookies"):
        src = base / rel
        if not src.exists():
            continue
        try:
            with tempfile.TemporaryDirectory() as tmp:
                dst = Path(tmp) / "c.db"
                shutil.copy2(src, dst)
                conn = sqlite3.connect(dst)
                try:
                    row = conn.execute(
                        "SELECT 1 FROM cookies WHERE host_key LIKE '%google.com' "
                        "AND name IN ('SID','SAPISID','__Secure-1PSID','__Secure-3PSID') LIMIT 1"
                    ).fetchone()
                finally:
                    conn.close()
            return bool(row)
        except (OSError, sqlite3.Error):
            return None
    return False if base.exists() else None


def refresh_auth(profile_id: str) -> str:
    p = get_profile(profile_id)
    if not p:
        return "Unknown"
    found = detect_google_session(p["profile_directory"])
    status = "Unknown" if found is None else ("Signed in" if found else "Pending")
    if found is None and p["authentication_status"] == "Signed in":
        return p["authentication_status"]  # keep a previous/manual confirmation
    set_auth_status(profile_id, status)
    return status


# ------------------------------------------------------------------ VPN sync
def sync_vpn_config(source_profile_id: str, extension_id: str | None = None) -> tuple[bool, str]:
    """Clone extension settings (login/cookies/state) from source profile to all other profiles."""
    src_profile = get_profile(source_profile_id)
    if not src_profile:
        return False, "Source profile not found."

    candidate_ids = (extension_id,) if extension_id else ("eppiocemhmnlbhjplcgkofciiegomcon", "eppiocemhmnlbhjplcgkfeedignghneo")
    src_root = Path(src_profile["profile_directory"])
    src_sub = src_profile.get("profile_directory_name") or "Default"
    
    src_folder = None
    target_id = candidate_ids[0]
    for cid in candidate_ids:
        folder = src_root / src_sub / "Local Extension Settings" / cid
        if folder.exists() and any(folder.iterdir()):
            src_folder = folder
            target_id = cid
            break

    if not src_folder:
        for cid in candidate_ids:
            matches = list(src_root.glob(f"**/{cid}"))
            if matches:
                src_folder = matches[0]
                target_id = cid
                break

    if not src_folder:
        return False, f"No VPN configuration found in profile '{src_profile['profile_name']}'. Launch it and configure or log in to Urban VPN first."

    all_profs = list_profiles()
    synced = 0
    for p in all_profs:
        if p["id"] == source_profile_id:
            continue
        dst_root = Path(p["profile_directory"])
        dst_sub = p.get("profile_directory_name") or "Default"
        
        # Sync to all known IDs so whichever variant Chrome references has the state
        for out_id in ("eppiocemhmnlbhjplcgkofciiegomcon", "eppiocemhmnlbhjplcgkfeedignghneo"):
            dst_folder = dst_root / dst_sub / "Local Extension Settings" / out_id
            try:
                dst_folder.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(src_folder, dst_folder, dirs_exist_ok=True)

                # Also sync Sync Extension Settings if present
                src_sync = src_folder.parent.parent / "Sync Extension Settings" / target_id
                if src_sync.exists():
                    dst_sync = dst_folder.parent.parent / "Sync Extension Settings" / out_id
                    dst_sync.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(src_sync, dst_sync, dirs_exist_ok=True)

                # Also sync IndexedDB if present
                src_idb = src_root / src_sub / "IndexedDB"
                if src_idb.exists():
                    for idb_match in src_idb.glob(f"*{target_id}*"):
                        dst_idb = dst_root / dst_sub / "IndexedDB" / idb_match.name.replace(target_id, out_id)
                        dst_idb.parent.mkdir(parents=True, exist_ok=True)
                        if idb_match.is_dir():
                            shutil.copytree(idb_match, dst_idb, dirs_exist_ok=True)
                        else:
                            shutil.copy2(idb_match, dst_idb)
            except Exception:
                continue
        synced += 1

    return True, f"Successfully synced Urban VPN configuration from '{src_profile['profile_name']}' to {synced} profile(s)."

    return True, f"Successfully synced Urban VPN configuration from '{src_profile['profile_name']}' to {synced} profile(s)."
