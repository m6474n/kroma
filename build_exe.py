"""Build script for packaging Kroma into a standalone Windows executable."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent


def build(onefile: bool = False):
    print("=" * 60)
    print("  KROMA - Standalone Windows Executable Builder")
    print("=" * 60)
    print(f"  Root directory: {ROOT_DIR}")
    print(f"  Packaging mode: {'--onefile (Single EXE)' if onefile else '--onedir (Directory bundle)'}")
    print("=" * 60)

    # Validate essential source directories
    for req_dir in [ROOT_DIR / "templates", ROOT_DIR / "static", ROOT_DIR / "data" / "extensions" / "kroma_vpn"]:
        if not req_dir.exists():
            print(f"[ERROR] Required resource path missing: {req_dir}")
            sys.exit(1)

    dist_dir = ROOT_DIR / "dist"
    build_dir = ROOT_DIR / "build"

    sep = ";" if sys.platform == "win32" else ":"

    args = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--name",
        "Kroma",
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
        # Hidden imports
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
        "modules.browser.chromium",
        "--hidden-import",
        "modules.browser.profile_manager",
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

    print("\nRunning PyInstaller...")
    res = subprocess.run(args, cwd=str(ROOT_DIR))
    if res.returncode != 0:
        print(f"\n[ERROR] PyInstaller failed with exit code {res.returncode}")
        sys.exit(res.returncode)

    # Post-build setup
    if sys.platform == "darwin" and (dist_dir / "Kroma.app").exists():
        output_target = dist_dir / "Kroma.app"
        zip_path = dist_dir / "Kroma-macOS.zip"
        shutil.make_archive(str(dist_dir / "Kroma-macOS"), "zip", root_dir=str(dist_dir), base_dir="Kroma.app")
        print("\n" + "=" * 60)
        print("  BUILD COMPLETE (macOS)!")
        print(f"  * App Bundle:        {output_target}")
        print(f"  * Client Zip File:   {zip_path}")
        print("=" * 60)
        return

    exe_name = "Kroma.exe" if sys.platform == "win32" else "Kroma"
    output_exe = (dist_dir / exe_name) if onefile else (dist_dir / "Kroma" / exe_name)
    output_folder = output_exe.parent

    # Seed data directory alongside the executable so user has ready-to-use profiles & extensions
    target_data_dir = output_folder / "data"
    target_data_dir.mkdir(parents=True, exist_ok=True)
    (target_data_dir / "profiles").mkdir(parents=True, exist_ok=True)
    (target_data_dir / "extensions").mkdir(parents=True, exist_ok=True)

    src_vpn = ROOT_DIR / "data" / "extensions" / "kroma_vpn"
    dst_vpn = target_data_dir / "extensions" / "kroma_vpn"
    if src_vpn.exists() and not dst_vpn.exists():
        shutil.copytree(src_vpn, dst_vpn, dirs_exist_ok=True)

    # Copy .env.example if present as a template for user configuration
    if (ROOT_DIR / ".env.example").exists():
        shutil.copy(ROOT_DIR / ".env.example", output_folder / ".env.example")

    print("\n" + "=" * 60)
    print("  BUILD COMPLETE!")
    print(f"  * Output Executable: {output_exe}")
    print(f"  * Working Data Dir:  {target_data_dir}")
    print("=" * 60)
    print(f"\nYou can run: {output_exe}\n")


if __name__ == "__main__":
    is_onefile = "--onefile" in sys.argv
    build(onefile=is_onefile)

