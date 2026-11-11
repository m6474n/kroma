"""Process tracking for launched browser profiles.

Running state is derived live from the OS process list by matching the
--user-data-dir argument, so it stays accurate across app restarts.
"""
import os
import subprocess
import sys
import time

import psutil


_tracked_hwnds: dict[tuple[str, str | None], set[int]] = {}


def norm(path) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


def _cmd_info(cmdline):
    udir = None
    pname = None
    for arg in cmdline or []:
        if arg.startswith("--user-data-dir="):
            udir = norm(arg.split("=", 1)[1].strip('"'))
        elif arg.startswith("--profile-directory="):
            pname = arg.split("=", 1)[1].strip('"')
    return udir, pname


def get_chrome_hwnds() -> set[int]:
    """Get all visible top-level Chrome/Chromium window HWNDs.
    
    Strictly verifies process name is chrome/chromium so other Electron apps
    (VS Code, Discord, Slack, Spotify, etc.) are never matched.
    """
    if sys.platform != "win32":
        return set()
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    hwnds = set()

    def enum_cb(hwnd, lparam):
        if user32.IsWindowVisible(hwnd):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            try:
                p = psutil.Process(pid.value)
                pname = p.name().lower()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                return True
            if any(b in pname for b in ("chrome", "chromium")):
                class_buff = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(hwnd, class_buff, 256)
                if "Chrome_WidgetWin" in class_buff.value:
                    hwnds.add(hwnd)
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
    return hwnds


def running_map() -> dict:
    """{ (norm_user_data_dir, profile_name): [psutil.Process, ...] } for running browsers."""
    result: dict = {}
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            pname = (proc.info.get("name") or "").lower()
            if not any(b in pname for b in ("chrome", "chromium")):
                continue
            cmd = proc.info["cmdline"]
            d, p = _cmd_info(cmd)
        except Exception:
            continue
        if d:
            result.setdefault((d, p), []).append(proc)
    return result


def is_running(profile_dir, profile_directory_name: str | None = None, rmap: dict | None = None) -> bool:
    key = (norm(profile_dir), profile_directory_name)
    if sys.platform == "win32":
        import ctypes
        user32 = ctypes.windll.user32
        tracked = _tracked_hwnds.get(key, set())
        alive_hwnds = {h for h in tracked if user32.IsWindow(h) and user32.IsWindowVisible(h)}
        _tracked_hwnds[key] = alive_hwnds
        if alive_hwnds:
            return True
        if profile_directory_name:
            return False

    rmap = rmap if rmap is not None else running_map()
    ndir = norm(profile_dir)
    if profile_directory_name:
        return (ndir, profile_directory_name) in rmap
    return (ndir, None) in rmap


def launch(command: list[str], profile_dir: str | None = None, profile_directory_name: str | None = None) -> int:
    kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "stdin": subprocess.DEVNULL}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True

    before_hwnds = get_chrome_hwnds() if (sys.platform == "win32" and profile_dir) else set()
    pid = subprocess.Popen(command, **kwargs).pid

    if sys.platform == "win32" and profile_dir:
        key = (norm(profile_dir), profile_directory_name)
        # Check for newly opened Chrome window
        for _ in range(10):
            time.sleep(0.3)
            after_hwnds = get_chrome_hwnds()
            new_hwnds = after_hwnds - before_hwnds
            if new_hwnds:
                _tracked_hwnds.setdefault(key, set()).update(new_hwnds)
                break

    return pid


def close_chrome_windows(target_pids: set[int] | None = None):
    """Send WM_CLOSE only to top-level Chrome windows belonging to target_pids on Windows."""
    if sys.platform != "win32" or not target_pids:
        return
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    WM_CLOSE = 0x0010
    
    def enum_cb(hwnd, lparam):
        if user32.IsWindowVisible(hwnd):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value in target_pids:
                try:
                    p = psutil.Process(pid.value)
                    if not any(b in p.name().lower() for b in ("chrome", "chromium")):
                        return True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    return True
                class_buff = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(hwnd, class_buff, 256)
                if "Chrome_WidgetWin" in class_buff.value:
                    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(WNDENUMPROC(enum_cb), 0)


def close(profile_dir, profile_directory_name: str | None = None, timeout: float = 5.0) -> bool:
    """Ask the browser to quit gracefully (so cookies flush), then force-kill leftovers."""
    ndir = norm(profile_dir)
    key = (ndir, profile_directory_name)

    # 1. Close tracked windows for this specific profile
    if sys.platform == "win32":
        import ctypes
        user32 = ctypes.windll.user32
        WM_CLOSE = 0x0010
        tracked = _tracked_hwnds.pop(key, set())
        for hwnd in tracked:
            if user32.IsWindow(hwnd):
                user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
        if tracked:
            time.sleep(0.5)

    # If this is a system Chrome profile (profile_directory_name is set),
    # closing its window via WM_CLOSE (Win) or AppleScript (macOS) is sufficient.
    # NEVER force-kill the shared Chrome process because that would close personal Chrome!
    if profile_directory_name is not None:
        if sys.platform == "darwin":
            try:
                subprocess.run(
                    ["osascript", "-e", 'tell application "Google Chrome" to close active window'],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2
                )
            except Exception:
                pass
        return True

    # 2. For dedicated isolated ProfileHub profiles, manage their dedicated process:
    rmap = running_map()
    procs = rmap.get((ndir, None)) or []

    if not procs:
        return True

    # Gather PIDs for this isolated profile (including child processes)
    target_pids = set()
    for p in procs:
        try:
            target_pids.add(p.pid)
            for child in p.children(recursive=True):
                target_pids.add(child.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    # Try sending WM_CLOSE only to this profile's Chrome windows first
    if sys.platform == "win32" and target_pids:
        close_chrome_windows(target_pids)
        time.sleep(1)

    mains = [p for p in procs if not any(a.startswith("--type=") for a in (p.info.get("cmdline") or []))]
    for p in mains or procs:
        try:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                p.terminate()
        except psutil.Error:
            pass
    _, alive = psutil.wait_procs(procs, timeout=timeout)
    for p in alive:
        try:
            p.kill()
        except psutil.Error:
            pass
    psutil.wait_procs(alive, timeout=2)
    return True
