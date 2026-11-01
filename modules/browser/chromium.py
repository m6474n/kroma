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


def build_command(
    chrome: str,
    profile_dir: str,
    email: str = "",
    url: str | None = None,
    profile_directory_name: str | None = None,
    window_size: str = "800,600",
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
    cmd.append(target_url)
    return cmd
