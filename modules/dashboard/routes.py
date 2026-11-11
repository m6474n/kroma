"""Dashboard, accounts, profiles, settings and OAuth routes."""
import secrets
import shutil
from functools import wraps

from flask import (Blueprint, abort, flash, jsonify, redirect, render_template, request,
                   session, url_for)

import config
from config import CLIENT_SECRET_PATH, SCOPES
from database.db import get_setting, set_setting
from modules.browser import chromium, profile_manager as prm, process_manager as pm
from modules.google_auth import account_manager as am, oauth, token_manager as tm

bp = Blueprint("dashboard", __name__)


# ------------------------------------------------------------------ CSRF
def csrf_token() -> str:
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


@bp.before_app_request
def _security_guard():
    # 1. CSRF Protection for POST requests
    if request.method == "POST":
        sent = request.form.get("csrf_token") or request.headers.get("X-CSRFToken") or ""
        expected = session.get("csrf", "")
        if not sent or not expected or not secrets.compare_digest(sent, expected):
            abort(400, "Invalid or missing CSRF token. Reload the page and try again.")

    # 2. Strict Authentication Guard (prevents unauthorized access to all routes)
    from modules.auth import user_auth
    endpoint = request.endpoint or ""

    # Allow static assets unconditionally
    if endpoint == "static":
        return None

    # First-time initial setup
    if not user_auth.has_users():
        if not config.ALLOW_SETUP:
            # Release build: setup disabled, force login
            if endpoint not in ("dashboard.login", "dashboard.vpn_prep"):
                return redirect(url_for("dashboard.login"))
            return None
        elif endpoint != "dashboard.setup":
            return redirect(url_for("dashboard.setup"))
        return None

    # Login, setup, and vpn preparation interstitial routing
    if endpoint in ("dashboard.login", "dashboard.setup", "dashboard.vpn_prep"):
        return None

    # All other routes require an authenticated session
    if not session.get("user"):
        return redirect(url_for("dashboard.login"))


@bp.route("/setup", methods=["GET", "POST"])
def setup():
    import uuid
    from database.db import now_iso
    from modules.auth import user_auth, firebase_auth, firestore

    if not config.ALLOW_SETUP or user_auth.has_users():
        flash("Account registration is disabled in this release. Please sign in with your licensed credentials.", "info")
        return redirect(url_for("dashboard.login"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if password != confirm:
            flash("Passwords do not match.", "error")
            return render_template("setup.html", username=username, email=email)

        user_id = str(uuid.uuid4())
        fb_uid = None
        fb_token = None

        # 1. Sync with Firebase Authentication if configured
        if firebase_auth.is_firebase_configured():
            target_email = email or f"{username}@kroma.app"
            ok_fb, res_fb = firebase_auth.sign_up_with_email_password(target_email, password)
            if ok_fb and isinstance(res_fb, dict):
                fb_uid = res_fb.get("localId")
                fb_token = res_fb.get("idToken")
            elif not ok_fb:
                flash(f"Firebase notice: {res_fb}", "warning")

        # 2. Save user profile & subscription to Firebase Cloud Firestore
        effective_uid = fb_uid or user_id
        if firebase_auth.is_firebase_configured():
            profile_doc = {
                "uid": effective_uid,
                "username": username,
                "email": email or f"{username}@kroma.app",
                "subscription_status": "active",
                "subscription_tier": "pro",
                "subscription_expires_at": "2099-12-31T23:59:59Z",
                "max_profiles": 100,
                "role": "admin",
                "created_at": now_iso(),
                "updated_at": now_iso(),
            }
            ok_fs, msg_fs = firestore.save_user_profile(effective_uid, profile_doc, id_token=fb_token)
            if not ok_fs:
                flash(f"Firestore notice: {msg_fs}", "warning")

        # 3. Create local administrator account in SQLite
        ok_local, msg_local = user_auth.create_user(username, password)
        if not ok_local:
            flash(msg_local, "error")
            return render_template("setup.html", username=username, email=email)

        session["user"] = {
            "id": effective_uid,
            "username": username,
            "email": email or f"{username}@kroma.app",
            "subscription": {"subscription_status": "active", "subscription_tier": "pro"},
        }
        flash(f"Account '{username}' initialized and synced with Cloud Firestore.", "success")
        return redirect(url_for("dashboard.index"))

    return render_template("setup.html")


@bp.route("/login", methods=["GET", "POST"])
def login():
    from modules.auth import user_auth, firebase_auth, firestore
    if config.ALLOW_SETUP and not user_auth.has_users():
        return redirect(url_for("dashboard.setup"))

    if session.get("user"):
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        # A. Authenticate via Firebase Authentication first if configured
        if firebase_auth.is_firebase_configured():
            fb_email = username if "@" in username else f"{username}@kroma.app"
            ok_fb, res_fb = firebase_auth.sign_in_with_email_password(fb_email, password)
            if ok_fb and isinstance(res_fb, dict):
                uid = res_fb.get("localId")
                token = res_fb.get("idToken")

                # Verify subscription status in Cloud Firestore
                ok_prof, prof = firestore.get_user_profile(uid, id_token=token)
                if ok_prof and isinstance(prof, dict):
                    sub_status = (prof.get("subscription_status") or "active").lower()
                    if sub_status not in ("active", "trial"):
                        flash(f"Your subscription is currently {sub_status.upper()}. Please contact administrator.", "error")
                        return render_template("login.html", username=username)

                session["user"] = {
                    "id": uid,
                    "username": username,
                    "email": fb_email,
                    "subscription": prof if ok_prof and isinstance(prof, dict) else {"subscription_status": "active", "subscription_tier": "pro"},
                }
                flash(f"Signed in as {username} (Subscription: Active)", "success")
                return redirect(url_for("dashboard.index"))
            elif not user_auth.has_users():
                flash(str(res_fb), "error")
                return render_template("login.html", username=username)

        # B. Fallback to local database credentials
        ok, res = user_auth.authenticate(username, password)
        if ok:
            session["user"] = res
            flash(f"Welcome back, {res['username']}!", "success")
            return redirect(url_for("dashboard.index"))
        else:
            flash(str(res), "error")
            return render_template("login.html", username=username)

    return render_template("login.html")


@bp.post("/logout")
def logout():
    session.pop("user", None)
    flash("You have been signed out.", "info")
    return redirect(url_for("dashboard.login"))


@bp.app_context_processor
def _inject():
    return {"csrf_token": csrf_token}


def _back(default="dashboard.index"):
    return redirect(request.referrer or url_for(default))


def _ids(name="ids"):
    return request.form.getlist(name)


# -------------------------------------------------------------- dashboard
@bp.route("/")
def index():
    from modules.browser import automation_manager as atm
    all_autos = atm.list_automations()
    running_autos = [a for a in all_autos if a["status"] == "Running"]
    logs = atm.get_logs(30)
    return render_template(
        "dashboard.html",
        stats=prm.stats(),
        accounts=am.list_accounts()[:5],
        profiles=prm.list_profiles()[:5],
        running_automations=running_autos,
        recent_logs=logs,
        configured=oauth.client_configured(),
    )


# --------------------------------------------------------------- accounts
@bp.route("/accounts")
def accounts():
    q, status = request.args.get("q", "").strip(), request.args.get("status", "")
    return render_template(
        "accounts.html", accounts=am.list_accounts(q, status), q=q, status=status,
        configured=oauth.client_configured(),
        redirect_uri=url_for("dashboard.oauth_callback", _external=True),
        secret_path=str(CLIENT_SECRET_PATH),
    )


@bp.route("/oauth/start")
def oauth_start():
    if not oauth.client_configured():
        flash(f"Google client file not found at {CLIENT_SECRET_PATH}. See Settings / README.", "error")
        return redirect(url_for("dashboard.accounts"))
    redirect_uri = url_for("dashboard.oauth_callback", _external=True)
    try:
        auth_url, state, verifier = oauth.start(redirect_uri)
    except Exception as exc:
        flash(f"Could not start Google sign-in: {exc}", "error")
        return redirect(url_for("dashboard.accounts"))
    
    # Provision dedicated profile directory so session cookies are created directly inside it
    import uuid
    new_profile_id = str(uuid.uuid4())
    profile_dir = prm.profiles_root() / new_profile_id
    profile_dir.mkdir(parents=True, exist_ok=True)
    
    # Store in settings (cross-browser persistent) + session
    session["oauth_state"], session["oauth_verifier"] = state, verifier
    session["oauth_profile_id"] = new_profile_id
    set_setting(f"pending_profile_{state}", new_profile_id)
    if verifier:
        set_setting(f"pending_verifier_{state}", verifier)
    
    # Launch Chrome window with this profile directly on the Google OAuth login page
    ok, msg = prm.launch_browser(str(profile_dir), url=auth_url)
    if not ok:
        flash(f"Warning: could not launch Chrome automatically ({msg}). Redirecting in current browser.", "error")
        return redirect(auth_url)
    
    flash("Chrome launched with a new dedicated profile. Sign in on the Chrome window to complete setup.", "info")
    return redirect(url_for("dashboard.accounts"))


@bp.route("/oauth/callback")
def oauth_callback():
    state = request.args.get("state", "") or session.pop("oauth_state", None)
    verifier = session.pop("oauth_verifier", None) or get_setting(f"pending_verifier_{state}")
    
    # Retrieve pending profile id associated with this state
    saved_profile_id = session.pop("oauth_profile_id", None) or get_setting(f"pending_profile_{state}")
    
    if request.args.get("error"):
        flash(f"Google authorization was cancelled or denied: {request.args['error']}", "error")
        return redirect(url_for("dashboard.accounts"))
    
    try:
        creds, info = oauth.finish(
            url_for("dashboard.oauth_callback", _external=True), state, verifier, request.url
        )
        account_id, created = am.upsert_account(creds, info)
        # Bind or create profile record and mark as Signed in
        p_id, p_name = prm.create_or_bind_profile(account_id, info.get("email"), pre_profile_id=saved_profile_id)
    except Exception as exc:
        flash(f"Google sign-in failed: {exc}", "error")
        return redirect(url_for("dashboard.accounts"))
    flash(f"{'Connected' if created else 'Reconnected'} {info.get('email')}. Profile '{p_name}' ready & pre-logged in!", "success")
    return redirect(url_for("dashboard.profiles"))


@bp.post("/accounts/<account_id>/disconnect")
def account_disconnect(account_id):
    ok, msg = am.disconnect(account_id)
    flash(msg, "success" if ok else "error")
    return _back("dashboard.accounts")


@bp.post("/accounts/<account_id>/refresh")
def account_refresh(account_id):
    ok, msg = tm.refresh(account_id)
    flash(msg, "success" if ok else "error")
    return _back("dashboard.accounts")


@bp.post("/accounts/<account_id>/delete")
def account_delete(account_id):
    for p in prm.list_profiles():
        if p["account_id"] == account_id:
            prm.delete(p["id"])
    tm.revoke(account_id)
    am.delete_account_row(account_id)
    flash("Account record and its profiles deleted.", "success")
    return _back("dashboard.accounts")


@bp.post("/accounts/generate")
def accounts_generate():
    ids = _ids()
    if not ids:
        flash("Select at least one account first.", "error")
        return _back("dashboard.accounts")
    results = prm.generate(ids, force=request.form.get("force") == "1")
    created = sum(r["status"] == "created" for r in results)
    skipped = [r["email"] for r in results if r["status"] == "skipped"]
    failed = [f"{r['email']}: {r['message']}" for r in results if r["status"] == "failed"]
    if created:
        flash(f"Created {created} profile(s).", "success")
    if skipped:
        flash(f"Skipped (profile already exists): {', '.join(skipped)}", "info")
    for f in failed:
        flash(f"Failed - {f}", "error")
    return redirect(url_for("dashboard.profiles"))


@bp.post("/accounts/bulk/<action>")
def accounts_bulk(action):
    ids = _ids()
    if not ids:
        flash("Select at least one account first.", "error")
        return _back("dashboard.accounts")
    if action == "delete":
        for aid in ids:
            for p in prm.list_profiles():
                if p["account_id"] == aid:
                    prm.delete(p["id"])
            tm.revoke(aid)
            am.delete_account_row(aid)
        flash(f"Deleted {len(ids)} account(s) and associated profiles.", "success")
    elif action == "disconnect":
        for aid in ids:
            am.disconnect(aid)
        flash(f"Disconnected {len(ids)} account(s).", "success")
    else:
        abort(404)
    return redirect(url_for("dashboard.accounts"))


# --------------------------------------------------------------- profiles
@bp.route("/profiles")
def profiles():
    q = request.args.get("q", "").strip()
    return render_template("profiles.html", profiles=prm.list_profiles(q), q=q,
                           chrome=chromium.find_chrome())


@bp.route("/profiles/<profile_id>")
def profile_details(profile_id):
    p = prm.get_profile(profile_id)
    if not p:
        abort(404)
    return render_template("profile_details.html", p=p)


def _single(action):
    @wraps(action)
    def wrapper(profile_id):
        ok, msg = action(profile_id)
        flash(msg, "success" if ok else "error")
        return _back("dashboard.profiles")
    return wrapper


for _name, _fn in (("launch", prm.launch), ("close", prm.close), ("restart", prm.restart)):
    bp.add_url_rule(f"/profiles/<profile_id>/{_name}", f"profile_{_name}",
                    _single(_fn), methods=["POST"])


@bp.post("/profiles/<profile_id>/delete")
def profile_delete(profile_id):
    ok, msg = prm.delete(profile_id)
    flash(msg, "success" if ok else "error")
    return redirect(url_for("dashboard.profiles"))


@bp.post("/profiles/<profile_id>/auth")
def profile_auth(profile_id):
    mode = request.form.get("mode", "detect")
    if mode == "signed_in":
        prm.set_auth_status(profile_id, "Signed in")
        flash("Marked as signed in.", "success")
    elif mode == "pending":
        prm.set_auth_status(profile_id, "Pending")
        flash("Marked as pending.", "success")
    else:
        flash(f"Authentication status: {prm.refresh_auth(profile_id)}", "info")
    return _back("dashboard.profiles")


@bp.post("/profiles/<profile_id>/sync_vpn")
def profile_sync_vpn(profile_id):
    ok, msg = prm.sync_vpn_config(profile_id)
    flash(msg, "success" if ok else "error")
    return _back("dashboard.profiles")


@bp.post("/profiles/<profile_id>/proxy")
def profile_set_proxy(profile_id):
    enabled = request.form.get("proxy_enabled") == "1"
    ptype = request.form.get("proxy_type", "http").strip()
    host = request.form.get("proxy_host", "").strip()
    port = request.form.get("proxy_port", "").strip()
    user = request.form.get("proxy_user", "").strip()
    password = request.form.get("proxy_pass", "").strip()

    prm.update_profile_proxy(
        profile_id,
        enabled=enabled,
        proxy_type=ptype,
        host=host or None,
        port=int(port) if port.isdigit() else None,
        user=user or None,
        password=password or None,
    )
    flash("Proxy settings updated for profile.", "success")
    return _back("dashboard.profiles")


@bp.post("/api/proxy/bulk")
def api_bulk_proxy():
    data = request.get_json(silent=True) or request.form
    profile_ids = data.get("profile_ids")
    if isinstance(profile_ids, str):
        import json
        try:
            profile_ids = json.loads(profile_ids)
        except Exception:
            profile_ids = [p.strip() for p in profile_ids.split(",") if p.strip()]
    if not profile_ids:
        profile_ids = [p["id"] for p in prm.list_profiles()]

    proxy_list_raw = str(data.get("proxy_list", "")).strip()
    ptype = str(data.get("proxy_type", "http")).strip()

    # Mode A: Multi-Proxy List (Assigns 1 unique proxy per profile)
    if proxy_list_raw:
        lines = [l.strip() for l in proxy_list_raw.splitlines() if l.strip()]
        count = 0
        for idx, pid in enumerate(profile_ids):
            if not lines:
                break
            line = lines[idx % len(lines)]
            # Clean protocol prefix if present
            for prefix in ("http://", "https://", "socks5://"):
                if line.lower().startswith(prefix):
                    ptype = prefix.replace("://", "")
                    line = line[len(prefix):]
                    break

            parts = line.split(":")
            host, port, user, pwd = None, None, None, None
            if len(parts) == 4:
                host, port, user, pwd = parts[0], parts[1], parts[2], parts[3]
            elif len(parts) == 2:
                host, port = parts[0], parts[1]
            elif "@" in line:
                # user:pass@host:port
                creds, netloc = line.split("@", 1)
                user, pwd = creds.split(":", 1) if ":" in creds else (creds, None)
                host, port = netloc.split(":", 1) if ":" in netloc else (netloc, "8080")

            if host and port and port.isdigit():
                prm.update_profile_proxy(
                    pid,
                    enabled=True,
                    proxy_type=ptype,
                    host=host,
                    port=int(port),
                    user=user,
                    password=pwd,
                )
                count += 1
        if request.is_json:
            return jsonify({"ok": True, "count": count})
        flash(f"Distributed unique proxies across {count} profile(s).", "success")
        return _back("dashboard.profiles")

    # Mode B: Single Proxy for all profiles
    enabled = str(data.get("proxy_enabled")) in ("1", "true", "True")
    host = str(data.get("proxy_host", "")).strip()
    port_val = str(data.get("proxy_port", "")).strip()
    port = int(port_val) if port_val.isdigit() else None
    user = str(data.get("proxy_user", "")).strip() or None
    password = str(data.get("proxy_pass", "")).strip() or None

    count = prm.bulk_set_proxy(
        profile_ids,
        enabled=enabled,
        proxy_type=ptype,
        host=host or None,
        port=port,
        user=user,
        password=password,
    )
    if request.is_json:
        return jsonify({"ok": True, "count": count})
    flash(f"Proxy configured for {count} profile(s).", "success")
    return _back("dashboard.profiles")


@bp.post("/api/proxy/test")
def api_test_proxy():
    import urllib.request
    import time
    import json

    data = request.get_json(silent=True) or request.form
    ptype = (data.get("proxy_type") or "http").strip().lower()
    host = str(data.get("proxy_host", "")).strip()
    port = str(data.get("proxy_port", "")).strip()
    user = str(data.get("proxy_user", "")).strip()
    password = str(data.get("proxy_pass", "")).strip()

    if not host or not port:
        return jsonify({"ok": False, "error": "Host and Port are required."}), 400

    auth = f"{user}:{password}@" if user and password else ""
    proxy_url = f"{ptype}://{auth}{host}:{port}"

    start = time.time()
    try:
        handler = urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
        opener = urllib.request.build_opener(handler)
        req = urllib.request.Request("http://api.ipify.org?format=json", headers={"User-Agent": "Mozilla/5.0 Kroma/1.0"})
        with opener.open(req, timeout=6) as resp:
            body = resp.read().decode("utf-8")
            latency = int((time.time() - start) * 1000)
            res_json = json.loads(body)
            return jsonify({"ok": True, "ip": res_json.get("ip"), "latency_ms": latency})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 200


@bp.post("/profiles/bulk/<action>")
def profiles_bulk(action):
    ids = _ids()
    fns = {"launch": prm.launch, "close": prm.close, "delete": prm.delete}
    if action not in fns:
        abort(404)
    if not ids:
        flash("Select at least one profile first.", "error")
        return _back("dashboard.profiles")
    ok_count, errors = 0, []
    for pid in ids:
        ok, msg = fns[action](pid)
        if ok:
            ok_count += 1
        else:
            errors.append(msg)
    flash(f"{action.capitalize()}: {ok_count} profile(s) done.", "success")
    for e in errors:
        flash(e, "error")
    return redirect(url_for("dashboard.profiles"))


@bp.post("/profiles/import-system")
def profiles_import_system():
    results = prm.import_from_system_chrome()
    if not results:
        flash("No Chrome profiles found in default user data folder to import.", "info")
        return redirect(url_for("dashboard.profiles"))
    imported = sum(1 for r in results if r["status"] == "imported")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    failed = [f"{r['name']}: {r['message']}" for r in results if r["status"] == "failed"]
    if imported:
        flash(f"Successfully imported {imported} profile(s) from Chrome!", "success")
    if skipped:
        flash(f"{skipped} profile(s) were already imported.", "info")
    for f in failed:
        flash(f"Import failed for {f}", "error")
    return redirect(url_for("dashboard.profiles"))


# ----------------------------------------------------------- automations
@bp.route("/automations")
def automations():
    from modules.browser import automation_manager as atm
    return render_template(
        "automations.html",
        automations=atm.list_automations(),
        profiles=prm.list_profiles(),
        recent_logs=atm.get_logs(30),
    )


@bp.route("/api/automations/status")
def api_automations_status():
    from modules.browser import automation_manager as atm
    return {
        "automations": atm.list_automations(),
        "logs": atm.get_logs(40),
    }


@bp.route("/api/dashboard/live")
def api_dashboard_live():
    from modules.browser import automation_manager as atm
    all_autos = atm.list_automations()
    running_autos = [a for a in all_autos if a["status"] == "Running"]
    return {
        "stats": prm.stats(),
        "running_automations": running_autos,
        "logs": atm.get_logs(40),
    }


@bp.get("/vpn_prep")
def vpn_prep():
    target = request.args.get("target", "https://google.com")
    try:
        wait = int(request.args.get("wait", 15))
    except (ValueError, TypeError):
        wait = 15
    return render_template("vpn_prep.html", target_url=target, wait_seconds=wait)


@bp.post("/automations/create")
def automation_create():
    from modules.browser import automation_manager as atm
    name = request.form.get("name", "").strip()
    url = request.form.get("url", "").strip()
    duration = int(request.form.get("duration_seconds", 30))
    vpn_delay = int(request.form.get("vpn_delay_seconds", 15))
    is_loop = request.form.get("is_loop") == "1"
    repeat_count = int(request.form.get("repeat_count", 1))
    profile_ids = request.form.getlist("profile_ids")
    
    if not profile_ids:
        flash("Please select at least one profile for the automation.", "error")
        return redirect(url_for("dashboard.automations"))
    
    atm.create_automation(name, url, profile_ids, duration, is_loop, repeat_count, vpn_delay_seconds=vpn_delay)
    flash(f"Created automation '{name}'.", "success")
    return redirect(url_for("dashboard.automations"))


@bp.post("/automations/<auto_id>/start")
def automation_start(auto_id):
    from modules.browser import automation_manager as atm
    ok, msg = atm.start_automation(auto_id)
    flash(msg, "success" if ok else "error")
    return redirect(url_for("dashboard.automations"))


@bp.post("/automations/<auto_id>/stop")
def automation_stop(auto_id):
    from modules.browser import automation_manager as atm
    ok, msg = atm.stop_automation(auto_id)
    flash(msg, "success" if ok else "error")
    return redirect(url_for("dashboard.automations"))


@bp.post("/automations/<auto_id>/delete")
def automation_delete(auto_id):
    from modules.browser import automation_manager as atm
    atm.delete_automation(auto_id)
    flash("Automation deleted.", "success")
    return redirect(url_for("dashboard.automations"))


# -------------------------------------------------------------- settings
@bp.route("/settings", methods=["GET", "POST"])
def settings():
    from modules.auth import user_auth, firebase_auth, firestore
    if request.method == "POST":
        set_setting("chrome_path", request.form.get("chrome_path", "").strip())
        set_setting("profiles_dir", request.form.get("profiles_dir", "").strip())

        fb_key = request.form.get("firebase_web_api_key")
        if fb_key is not None:
            firebase_auth.set_firebase_api_key(fb_key.strip())

        fb_proj = request.form.get("firebase_project_id")
        if fb_proj is not None:
            firestore.set_firebase_project_id(fb_proj.strip())

        # Password update
        new_pwd = request.form.get("new_password", "")
        if new_pwd:
            cur_pwd = request.form.get("current_password", "")
            confirm_pwd = request.form.get("confirm_password", "")
            if new_pwd != confirm_pwd:
                flash("New passwords do not match.", "error")
                return redirect(url_for("dashboard.settings"))
            uid = session.get("user", {}).get("id")
            if uid:
                ok, msg = user_auth.update_password(uid, cur_pwd, new_pwd)
                if not ok:
                    flash(msg, "error")
                    return redirect(url_for("dashboard.settings"))
                flash("Admin password updated successfully.", "success")
            else:
                flash("Unable to verify user session.", "error")
                return redirect(url_for("dashboard.settings"))
        else:
            flash("Settings saved.", "success")
        return redirect(url_for("dashboard.settings"))

    return render_template(
        "settings.html",
        chrome_path=get_setting("chrome_path", ""),
        detected=chromium.find_chrome(),
        profiles_dir=get_setting("profiles_dir", ""),
        effective_dir=str(prm.profiles_root()),
        firebase_web_api_key=firebase_auth.get_firebase_api_key(),
        firebase_project_id=firestore.get_firebase_project_id(),
    )


@bp.post("/settings/firebase-sync")
def settings_firebase_sync():
    from database.db import now_iso
    from modules.auth import firebase_auth, firestore

    email = request.form.get("sync_email", "").strip()
    password = request.form.get("sync_password", "")
    tier = request.form.get("sync_tier", "pro").strip() or "pro"

    if not email or not password:
        flash("Email and password are required to create/sync Firebase user.", "error")
        return redirect(url_for("dashboard.settings"))

    if not firebase_auth.is_firebase_configured():
        flash("Firebase Web API Key is not configured.", "error")
        return redirect(url_for("dashboard.settings"))

    ok_fb, res_fb = firebase_auth.sign_up_with_email_password(email, password)
    if not ok_fb and "already exists" in str(res_fb).lower():
        ok_fb, res_fb = firebase_auth.sign_in_with_email_password(email, password)

    if not ok_fb or not isinstance(res_fb, dict):
        flash(f"Firebase Auth failed: {res_fb}", "error")
        return redirect(url_for("dashboard.settings"))

    uid = res_fb.get("localId")
    token = res_fb.get("idToken")

    profile_doc = {
        "uid": uid,
        "username": email.split("@")[0],
        "email": email,
        "subscription_status": "active",
        "subscription_tier": tier,
        "subscription_expires_at": "2099-12-31T23:59:59Z",
        "max_profiles": 100,
        "role": "client",
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    ok_fs, msg_fs = firestore.save_user_profile(uid, profile_doc, id_token=token)
    if not ok_fs:
        flash(f"User created in Firebase Auth (UID: {uid}), but Firestore save failed: {msg_fs}", "warning")
    else:
        flash(f"User '{email}' created & saved to Firebase Auth + Cloud Firestore (UID: {uid})!", "success")

    return redirect(url_for("dashboard.settings"))
