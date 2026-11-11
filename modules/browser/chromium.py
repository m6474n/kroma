"""Locate Chrome/Chromium and build launch commands."""
import os
import shutil
from urllib.parse import quote

from database.db import get_setting


def _candidates():
    pf = os.environ.get("PROGRAMFILES", r"C:\Program Files")
    pf86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
    local = os.environ.get("LOCALAPPDATA", "")
    rels = [r"Google\Chrome\Application\chrome.exe", r"Chromium\Application\chrome.exe"]
    for base in (pf, pf86, local):
        for rel in rels:
            if base:
                yield os.path.join(base, rel)
    yield "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    yield "/Applications/Chromium.app/Contents/MacOS/Chromium"
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"):
        found = shutil.which(name)
        if found:
            yield found


def find_chrome() -> str | None:
    configured = get_setting("chrome_path")
    if configured and os.path.exists(configured):
        return configured
    for path in _candidates():
        if path and os.path.exists(path):
            return path
    return None


def login_url(email: str) -> str:
    return f"https://accounts.google.com/AccountChooser?Email={quote(email)}"


def default_chrome_user_data_dir() -> str | None:
    local = os.environ.get("LOCALAPPDATA", "")
    p = os.path.join(local, "Google", "Chrome", "User Data")
    return p if os.path.exists(p) else None


def list_system_chrome_profiles() -> list[dict]:
    """Find all profiles saved in default installed Google Chrome on the system."""
    import json
    data_dir = default_chrome_user_data_dir()
    if not data_dir:
        return []
    local_state_path = os.path.join(data_dir, "Local State")
    if not os.path.exists(local_state_path):
        return []
    try:
        with open(local_state_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        info_cache = data.get("profile", {}).get("info_cache", {})
        profiles = []
        for dir_name, meta in info_cache.items():
            email = meta.get("user_name", "") or ""
            name = meta.get("name", "") or dir_name
            gaia_id = meta.get("gaia_id", "") or ""
            profiles.append({
                "dir_name": dir_name,
                "name": name,
                "email": email,
                "gaia_id": gaia_id,
                "user_data_dir": data_dir,
            })
        return profiles
    except Exception:
        return []


def ensure_kroma_vpn_extension(profile_id: str, proxy_config: dict | None = None) -> tuple[str | None, dict | None]:
    """Prepare a dedicated Kroma Auto-VPN extension instance configured for this profile."""
    from pathlib import Path
    from config import KROMA_VPN_DIR, EXTENSIONS_DIR
    import json
    import shutil
    import hashlib

    if not KROMA_VPN_DIR.exists() or not (KROMA_VPN_DIR / "manifest.json").exists():
        return None, None

    # Load fallback server pool from servers.json
    servers_file = KROMA_VPN_DIR / "servers.json"
    server_pool = []
    if servers_file.exists():
        try:
            server_pool = json.loads(servers_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Pick server from proxy_config or from server_pool deterministically by profile_id
    assigned_server = None
    if proxy_config and proxy_config.get("proxy_host") and proxy_config.get("proxy_port"):
        assigned_server = {
            "type": (proxy_config.get("proxy_type") or "http").lower(),
            "host": str(proxy_config["proxy_host"]).strip(),
            "port": int(proxy_config["proxy_port"]),
            "username": str(proxy_config.get("proxy_user") or "").strip(),
            "password": str(proxy_config.get("proxy_pass") or "").strip(),
            "country": str(proxy_config.get("country") or "Active Proxy").strip(),
        }
    elif server_pool:
        idx = int(hashlib.md5(profile_id.encode()).hexdigest(), 16) % len(server_pool)
        item = server_pool[idx]
        assigned_server = {
            "type": (item.get("type") or "http").lower(),
            "host": str(item["host"]).strip(),
            "port": int(item["port"]),
            "username": "",
            "password": "",
            "country": item.get("country", f"Server #{idx+1}"),
        }

    if not assigned_server:
        return None, None

    prof_ext_dir = EXTENSIONS_DIR / "kroma_vpn_profiles" / profile_id
    prof_ext_dir.mkdir(parents=True, exist_ok=True)

    for fname in ("manifest.json", "background.js", "popup.html", "popup.js"):
        src = KROMA_VPN_DIR / fname
        if src.exists():
            shutil.copy2(src, prof_ext_dir / fname)

    cfg = {
        "enabled": True,
        "server": assigned_server
    }
    (prof_ext_dir / "config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return str(prof_ext_dir.resolve()), assigned_server


def ensure_proxy_auth_extension(profile_id: str, username: str, password: str) -> str:
    """Create a lightweight unpacked extension to handle Chrome proxy authentication silently."""
    from pathlib import Path
    from config import EXTENSIONS_DIR
    import json

    ext_dir = EXTENSIONS_DIR / "proxy_auth" / profile_id
    ext_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "version": "1.0.0",
        "manifest_version": 3,
        "name": f"Proxy Auth {profile_id[:8]}",
        "permissions": ["webRequest", "webRequestAuthProvider"],
        "host_permissions": ["<all_urls>"],
        "background": {
            "service_worker": "background.js"
        }
    }
    (ext_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    bg_code = f"""chrome.webRequest.onAuthRequired.addListener(
    function(details, callback) {{
        callback({{
            authCredentials: {{
                username: {json.dumps(username)},
                password: {json.dumps(password)}
            }}
        }});
    }},
    {{ urls: ["<all_urls>"] }},
    ["asyncBlocking"]
);
"""
    (ext_dir / "background.js").write_text(bg_code, encoding="utf-8")
    return str(ext_dir.resolve())


def get_loaded_extensions() -> list[str]:
    """Return list of unpacked extension directory paths configured to load."""
    from pathlib import Path
    from config import URBAN_VPN_DIR
    from database.db import get_setting

    paths = []
    custom_vpn = get_setting("urban_vpn_path")
    vpn_dir = Path(custom_vpn) if custom_vpn else URBAN_VPN_DIR
    enabled = get_setting("urban_vpn_enabled")
    has_manifest = (vpn_dir / "manifest.json").exists()
    if enabled == "1" and vpn_dir.exists() and has_manifest:
        paths.append(str(vpn_dir.resolve()))

    custom_exts = get_setting("custom_extensions")
    if custom_exts:
        for p in custom_exts.split(";"):
            p_strip = p.strip()
            if p_strip and os.path.exists(p_strip):
                paths.append(str(Path(p_strip).resolve()))
    return paths


def build_command(
    chrome: str,
    profile_dir: str,
    email: str = "",
    url: str | None = None,
    profile_directory_name: str | None = None,
    window_size: str = "800,600",
    proxy_config: dict | None = None,
) -> list[str]:
    target_url = url or (login_url(email) if email else "https://accounts.google.com")
    cmd = [
        chrome,
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        f"--window-size={window_size}",
    ]
    if profile_directory_name:
        cmd.append(f"--profile-directory={profile_directory_name}")

    extensions = get_loaded_extensions()

    # Kroma Auto-VPN Chrome Extension & Native Proxy setup
    prof_id = (proxy_config.get("profile_id") if proxy_config else None) or profile_directory_name or "default"
    vpn_ext_path, active_server = ensure_kroma_vpn_extension(prof_id, proxy_config)
    if vpn_ext_path:
        extensions.append(vpn_ext_path)

    if active_server and active_server.get("host") and active_server.get("port"):
        ptype = active_server.get("type", "http")
        phost = active_server["host"]
        pport = active_server["port"]
        cmd.append(f"--proxy-server={ptype}://{phost}:{pport}")

        puser = active_server.get("username")
        ppass = active_server.get("password")
        if puser and ppass:
            auth_ext = ensure_proxy_auth_extension(prof_id, puser, ppass)
            extensions.append(auth_ext)

    if extensions:
        cmd.append(f"--load-extension={','.join(extensions)}")

    cmd.append(target_url)
    return cmd
