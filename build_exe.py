"""Build script for packaging Kroma into a standalone Windows (.exe) or macOS (.app) executable.

Usage:
    python build_exe.py            -> Release build (/setup disabled, login only)
    python build_exe.py --debug    -> Debug build (/setup enabled for provisioning)
    python build_exe.py --onefile  -> Single-file EXE (Windows/Linux)
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent


def _read_env_vars() -> dict[str, str]:
    vals = {}
    env_file = ROOT_DIR / ".env"
    if not env_file.exists():
        env_file = ROOT_DIR / ".env.example"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip().strip('"').strip("'")
    # Allow OS env vars to override
    for key in ("FIREBASE_WEB_API_KEY", "FIREBASE_PROJECT_ID"):
        if os.environ.get(key):
            vals[key] = os.environ[key]
    return vals


def build(onefile: bool = False, debug: bool = False):
    mode_label = "DEBUG (Setup Enabled)" if debug else "RELEASE (Setup Disabled - Login Only)"
    plat_label = "macOS (.app)" if sys.platform == "darwin" else "Windows (.exe)"
    print("=" * 60)
    print(f"  KROMA - Standalone {plat_label} Builder")
    print("=" * 60)
    print(f"  Root directory: {ROOT_DIR}")
    print(f"  Build Mode:     {mode_label}")
    print(f"  Packaging:      {'--onefile' if onefile else '--onedir / .app'}")
    print("=" * 60)

    # Validate essential source directories
    for req_dir in [ROOT_DIR / "templates", ROOT_DIR / "static", ROOT_DIR / "data" / "extensions" / "kroma_vpn"]:
        if not req_dir.exists():
            print(f"[ERROR] Required resource path missing: {req_dir}")
            sys.exit(1)

    # Bake build flags (RELEASE_MODE / ALLOW_SETUP / Firebase config) into temporary module
    env_vals = _read_env_vars()
    flags_path = ROOT_DIR / "kroma_build_flags.py"
    flags_content = (
        f"# Auto-generated during PyInstaller build\n"
        f"RELEASE_MODE = {not debug}\n"
        f"ALLOW_SETUP = {debug}\n"
        f"FIREBASE_WEB_API_KEY = {env_vals.get('FIREBASE_WEB_API_KEY', '')!r}\n"
        f"FIREBASE_PROJECT_ID = {env_vals.get('FIREBASE_PROJECT_ID', 'kroma-26615')!r}\n"
    )
    flags_path.write_text(flags_content, encoding="utf-8")

    dist_dir = ROOT_DIR / "dist"
    sep = ";" if sys.platform == "win32" else ":"

    app_name = "Kroma-Debug" if debug else "Kroma"

    args = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--name",
        app_name,
    ]

    if sys.platform == "darwin":
        args.append("--windowed")
    elif onefile:
        args.append("--onefile")
    else:
        args.append("--onedir")

    args.extend([
        # Resource bundles
        "--add-data",
        f"{ROOT_DIR / 'templates'}{sep}templates",
        "--add-data",
        f"{ROOT_DIR / 'static'}{sep}static",
        "--add-data",
        f"{ROOT_DIR / 'data' / 'extensions' / 'kroma_vpn'}{sep}data/extensions/kroma_vpn",
        "--add-data",
        f"{ROOT_DIR / 'data' / 'extensions' / 'urban_vpn'}{sep}data/extensions/urban_vpn",
    ])

    client_secret_src = ROOT_DIR / "data" / "client_secret.json"
    if client_secret_src.exists():
        args.extend(["--add-data", f"{client_secret_src}{sep}data"])

    args.extend([
        # Hidden imports
        "--hidden-import",
        "kroma_build_flags",
        "--hidden-import",
        "sqlite3",
        "--hidden-import",
        "cryptography",
        "--hidden-import",
        "cryptography.fernet",
        "--hidden-import",
        "psutil",
        "--hidden-import",
        "requests",
        "--hidden-import",
        "jinja2",
        "--hidden-import",
        "flask",
        "--hidden-import",
        "werkzeug",
        "--hidden-import",
        "google.auth",
        "--hidden-import",
        "google_auth_oauthlib",
        "--hidden-import",
        "modules.auth.firebase_auth",
        "--hidden-import",
        "modules.auth.firestore",
        "--hidden-import",
        "modules.browser.chromium",
        "--hidden-import",
        "modules.browser.playwright_driver",
        "--hidden-import",
        "modules.browser.profile_manager",
        "--hidden-import",
        "playwright",
        "--hidden-import",
        "playwright.sync_api",
        "--collect-all",
        "playwright",
        "--hidden-import",
        "modules.dashboard.routes",
        "--hidden-import",
        "database.models",
        "--hidden-import",
        "config",
        "--hidden-import",
        "app",
        # Main entry script
        str(ROOT_DIR / "main_desktop.py"),
    ])

    try:
        print("\nRunning PyInstaller...")
        res = subprocess.run(args, cwd=str(ROOT_DIR))
        if res.returncode != 0:
            print(f"\n[ERROR] PyInstaller failed with exit code {res.returncode}")
            sys.exit(res.returncode)
    finally:
        # Remove temporary build flags so local dev workspace stays clean
        if flags_path.exists():
            flags_path.unlink()

    # Post-build setup
    if sys.platform == "darwin" and (dist_dir / f"{app_name}.app").exists():
        output_target = dist_dir / f"{app_name}.app"
        zip_name = f"{app_name}-macOS"
        zip_path = dist_dir / f"{zip_name}.zip"
        shutil.make_archive(str(dist_dir / zip_name), "zip", root_dir=str(dist_dir), base_dir=f"{app_name}.app")
        print("\n" + "=" * 60)
        print(f"  BUILD COMPLETE (macOS - {'DEBUG' if debug else 'RELEASE'})!")
        print(f"  * App Bundle:        {output_target}")
        print(f"  * Client Zip File:   {zip_path}")
        print("=" * 60)
        return

    exe_name = f"{app_name}.exe" if sys.platform == "win32" else app_name
    output_exe = (dist_dir / exe_name) if onefile else (dist_dir / app_name / exe_name)
    output_folder = output_exe.parent

    # Seed data directory alongside the executable so user has ready-to-use profiles & extensions
    target_data_dir = output_folder / "data"
    target_data_dir.mkdir(parents=True, exist_ok=True)
    (target_data_dir / "profiles").mkdir(parents=True, exist_ok=True)
    (target_data_dir / "extensions").mkdir(parents=True, exist_ok=True)

    for folder_name in ("kroma_vpn", "urban_vpn"):
        src_ext = ROOT_DIR / "data" / "extensions" / folder_name
        dst_ext = target_data_dir / "extensions" / folder_name
        if src_ext.exists() and not dst_ext.exists():
            shutil.copytree(src_ext, dst_ext, dirs_exist_ok=True)

    if client_secret_src.exists():
        shutil.copy2(client_secret_src, target_data_dir / "client_secret.json")

    print("\n" + "=" * 60)
    print(f"  BUILD COMPLETE ({'DEBUG' if debug else 'RELEASE'})!")
    print(f"  * Output Executable: {output_exe}")
    print(f"  * Working Data Dir:  {target_data_dir}")
    print("=" * 60)
    print(f"\nYou can run: {output_exe}\n")


if __name__ == "__main__":
    is_onefile = "--onefile" in sys.argv
    is_debug = "--debug" in sys.argv
    build(onefile=is_onefile, debug=is_debug)

