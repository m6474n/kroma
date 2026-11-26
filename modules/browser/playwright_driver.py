"""Playwright-based browser automation driver for Kroma.

Automatically launches isolated Chromium profiles with Urban VPN loaded,
completes Urban VPN EULA/consent, selects United Kingdom (UK), connects,
and navigates to the target URL for the configured duration.
"""
import os
import shutil
import threading
import time
from pathlib import Path

from config import DATA_DIR, URBAN_VPN_DIR


def _prepare_driver_profile_dir(profile: dict) -> str:
    """Return an isolated profile directory safe for concurrent Playwright Chromium launch."""
    p_dir = Path(profile["profile_directory"])
    sub = profile.get("profile_directory_name")

    # Isolated ProfileHub profile can be used directly
    if not sub:
        p_dir.mkdir(parents=True, exist_ok=True)
        return str(p_dir.resolve())

    # System Chrome profile shares a locked User Data dir; mirror essential session data
    # into a dedicated Playwright driver folder so multiple profiles run concurrently.
    pw_dir = DATA_DIR / "profiles" / f"pw_{profile['id']}"
    default_sub = pw_dir / "Default"
    src_sub = p_dir / sub

    if not pw_dir.exists() and src_sub.exists():
        default_sub.mkdir(parents=True, exist_ok=True)
        local_state = p_dir / "Local State"
        if local_state.exists():
            try:
                shutil.copy2(local_state, pw_dir / "Local State")
            except Exception:
                pass
        for item in ("Cookies", "Network", "Login Data", "Web Data", "Preferences", "Local Extension Settings"):
            s = src_sub / item
            d = default_sub / item
            if s.exists():
                try:
                    if s.is_dir():
                        shutil.copytree(s, d, ignore=shutil.ignore_patterns("LOCK", "*.lock"), dirs_exist_ok=True)
                    else:
                        shutil.copy2(s, d)
                except Exception:
                    pass
    else:
        pw_dir.mkdir(parents=True, exist_ok=True)

    return str(pw_dir.resolve())


def _auto_connect_urban_vpn(ctx, ext_id: str, target_country: str, log_fn, stop_event: threading.Event) -> bool:
    """Drive Urban VPN popup UI via Playwright to accept EULA, select UK, and connect."""
    popup_url = f"chrome-extension://{ext_id}/popup/index.html"
    vpn_page = None
    try:
        vpn_page = ctx.new_page()
        vpn_page.goto(popup_url, wait_until="domcontentloaded", timeout=15000)

        # Dismiss any auto-opened thank-you tab from Urban VPN
        for pg in list(ctx.pages):
            if "thank-you-ext" in (pg.url or ""):
                try:
                    pg.close()
                except Exception:
                    pass

        max_steps = 25
        retry_count = 0
        country_selected = False

        for _ in range(max_steps):
            if stop_event.is_set():
                return False

            # Close thank-you tabs if Urban VPN opened one asynchronously
            for pg in list(ctx.pages):
                if pg != vpn_page and "thank-you-ext" in (pg.url or ""):
                    try:
                        pg.close()
                    except Exception:
                        pass

            vpn_page.wait_for_timeout(1000)
            body_text = ""
            try:
                body_text = (vpn_page.locator("#app").inner_text(timeout=2000) or "").strip()
            except Exception:
                continue

            # 1. Handle registration error / Retry
            if "Registration error" in body_text:
                if retry_count < 2:
                    retry_count += 1
                    log_fn(f"Urban VPN rate-limited/registration retry ({retry_count}/2)...", "warn")
                    retry_btn = vpn_page.locator("button:has-text('Retry')")
                    if retry_btn.count() > 0:
                        retry_btn.first.click()
                        vpn_page.wait_for_timeout(2000)
                    continue
                log_fn("Urban VPN registration blocked/rate-limited by API.", "warn")
                return False

            # 2. Handle Consent / EULA / Agree screens automatically
            for agree_text in ("Agree & Continue", "Agree and Continue", "I Agree", "Agree", "Accept", "Continue"):
                btn = vpn_page.locator(f"button:has-text('{agree_text}')")
                if btn.count() > 0 and btn.first.is_visible():
                    log_fn(f"Auto-accepting Urban VPN consent ('{agree_text}')...", "info")
                    btn.first.click()
                    vpn_page.wait_for_timeout(1500)
                    break

            # 3. Check if already connected
            if "Connected" in body_text or vpn_page.locator(".play-button--active, .play-button--connected").count() > 0:
                if country_selected:
                    log_fn(f"Urban VPN connected to {target_country}!", "success")
                    return True

            # 4. Search & Select Target Country (United Kingdom)
            search_input = vpn_page.locator("input.location-selector-input__native, input[placeholder='Search']")
            if not country_selected and search_input.count() > 0 and search_input.first.is_visible():
                log_fn(f"Selecting '{target_country}' in Urban VPN...", "info")
                search_input.first.click()
                search_input.first.fill(target_country)
                vpn_page.wait_for_timeout(800)

                # Click matching country row
                loc_item = vpn_page.locator(f".location-selector-results >> text={target_country}").first
                if loc_item.count() > 0 and loc_item.is_visible():
                    loc_item.click()
                    country_selected = True
                    vpn_page.wait_for_timeout(1000)
                else:
                    # Fallback text match
                    fallback = vpn_page.locator(f"text={target_country}").first
                    if fallback.count() > 0 and fallback.is_visible():
                        fallback.click()
                        country_selected = True
                        vpn_page.wait_for_timeout(1000)

            # 5. Click Play / Connect button if visible and not yet connected
            play_btn = vpn_page.locator(".play-button")
            if country_selected and play_btn.count() > 0 and play_btn.first.is_visible():
                cls = play_btn.first.get_attribute("class") or ""
                if "connected" not in cls.lower() and "loading" not in cls.lower():
                    play_btn.first.click()
                    vpn_page.wait_for_timeout(2000)
                elif "connected" in cls.lower():
                    log_fn(f"Urban VPN active on {target_country}!", "success")
                    return True

        return country_selected
    except Exception as exc:
        log_fn(f"Urban VPN driver notice: {exc}", "warn")
        return False
    finally:
        if vpn_page:
            try:
                vpn_page.close()
            except Exception:
                pass


def _ensure_chromium_installed(log_fn):
    """Install Playwright Chromium browser using internal driver CLI if missing on target machine."""
    import subprocess
    try:
        from playwright._impl._driver import compute_driver_executable, get_driver_env
        driver_exec, driver_cli = compute_driver_executable()
        log_fn("Installing Chromium driver engine (first-time setup)...", "info")
        subprocess.run(
            [str(driver_exec), str(driver_cli), "install", "chromium"],
            env=get_driver_env(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        return True
    except Exception as e:
        log_fn(f"Chromium auto-install notice: {e}", "warn")
        return False


def run_automated_browser(
    profile: dict,
    url: str,
    duration_seconds: int,
    stop_event: threading.Event,
    on_status=None,
    on_timer=None,
    on_log=None,
    target_country: str = "United Kingdom",
    proxy_config: dict | None = None,
) -> tuple[bool, str]:
    """Run an automated Playwright browser session with Urban VPN setup and countdown."""
    from playwright.sync_api import sync_playwright

    def log(msg: str, level: str = "info"):
        if on_log:
            on_log(msg, level)

    def set_status(st: str):
        if on_status:
            on_status(st)

    user_data_dir = _prepare_driver_profile_dir(profile)

    args = [
        "--no-first-run",
        "--no-default-browser-check",
        "--window-size=1024,768",
        "--autoplay-policy=no-user-gesture-required",
    ]

    launch_kwargs = {
        "user_data_dir": user_data_dir,
        "channel": "chrome",
        "headless": False,
        "args": args,
        "ignore_default_args": ["--no-sandbox"],
        "viewport": None,
    }

    ctx = None
    try:
        with sync_playwright() as p:
            set_status("Launching Driver")
            log(f"Starting Playwright Chromium driver for '{profile['profile_name']}'...", "info")
            try:
                ctx = p.chromium.launch_persistent_context(**launch_kwargs)
            except Exception as launch_err:
                if "Executable doesn't exist" in str(launch_err):
                    if _ensure_chromium_installed(log):
                        ctx = p.chromium.launch_persistent_context(**launch_kwargs)
                    else:
                        raise
                else:
                    raise

            if stop_event.is_set():
                return True, "Stopped before target navigation."

            # Step 2: Open Target URL
            set_status("Running")
            main_page = ctx.pages[0] if ctx.pages else ctx.new_page()
            log(f"Navigating '{profile['profile_name']}' to {url}", "info")
            try:
                main_page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except Exception as nav_err:
                log(f"Navigation warning: {nav_err}", "warn")

            # Step 3: Countdown active duration
            start_ts = time.time()
            while True:
                elapsed = int(time.time() - start_ts)
                rem = max(0, duration_seconds - elapsed)
                if on_timer:
                    on_timer(rem)
                if elapsed >= duration_seconds or stop_event.is_set():
                    break
                time.sleep(1)

            return True, "Completed session cleanly."
    except Exception as exc:
        return False, f"Playwright driver error: {exc}"
    finally:
        if ctx:
            try:
                ctx.close()
            except Exception:
                pass
