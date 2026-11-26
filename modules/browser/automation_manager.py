"""Background runner for browser profile automations."""
import json
import sys
import threading
import time
import uuid

from database.db import db, now_iso
from modules.browser import profile_manager as prm

_active_tasks: dict[str, threading.Event] = {}
_live_state: dict[str, dict] = {}
_logs: list[dict] = []
_lock = threading.Lock()


def add_log(auto_id: str, auto_name: str, message: str, level: str = "info"):
    entry = {
        "time": time.strftime("%H:%M:%S"),
        "auto_id": auto_id,
        "auto_name": auto_name,
        "message": message,
        "level": level,
    }
    with _lock:
        _logs.append(entry)
        if len(_logs) > 100:
            _logs.pop(0)


def get_logs(limit: int = 50) -> list[dict]:
    with _lock:
        return list(_logs[-limit:])


def list_automations() -> list[dict]:
    with db() as conn:
        rows = conn.execute("SELECT * FROM automations ORDER BY created_at DESC").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["profile_ids_list"] = json.loads(d.get("profile_ids") or "[]")
        except Exception:
            d["profile_ids_list"] = []
        try:
            d["profile_iterations_dict"] = json.loads(d.get("profile_iterations") or "{}")
        except Exception:
            d["profile_iterations_dict"] = {}

        with _lock:
            live = _live_state.get(d["id"], {})
            is_active = d["id"] in _active_tasks
            d["status"] = "Running" if is_active else "Stopped"
            prof_live_map = live.get("profiles", {})

        # Populate profile detail list for UI
        pdetails = []
        running_count = 0
        for pid in d["profile_ids_list"]:
            p = prm.get_profile(pid)
            pname = p["profile_name"] if p else pid[:8]
            email = p["email"] if p else ""
            plive = prof_live_map.get(pid, {})
            pstatus = plive.get("status", "Stopped" if not is_active else "Running")
            time_rem = plive.get("time_remaining", 0)
            iters = d["profile_iterations_dict"].get(pid, 0)
            is_running = (is_active and pstatus == "Running")
            if is_running:
                running_count += 1
            pdetails.append({
                "id": pid,
                "name": pname,
                "email": email,
                "status": pstatus,
                "is_running": is_running,
                "time_remaining": time_rem,
                "duration_seconds": d["duration_seconds"],
                "iterations": iters,
            })
        d["profiles_detail"] = pdetails
        d["running_profiles_count"] = running_count
        out.append(d)
    return out


def get_automation(auto_id: str) -> dict | None:
    with db() as conn:
        row = conn.execute("SELECT * FROM automations WHERE id=?", (auto_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    try:
        d["profile_ids_list"] = json.loads(d.get("profile_ids") or "[]")
    except Exception:
        d["profile_ids_list"] = []
    try:
        d["profile_iterations_dict"] = json.loads(d.get("profile_iterations") or "{}")
    except Exception:
        d["profile_iterations_dict"] = {}

    with _lock:
        live = _live_state.get(d["id"], {})
        is_active = d["id"] in _active_tasks
        d["status"] = "Running" if is_active else "Stopped"
        prof_live_map = live.get("profiles", {})

    pdetails = []
    running_count = 0
    for pid in d["profile_ids_list"]:
        p = prm.get_profile(pid)
        pname = p["profile_name"] if p else pid[:8]
        email = p["email"] if p else ""
        plive = prof_live_map.get(pid, {})
        pstatus = plive.get("status", "Stopped" if not is_active else "Running")
        time_rem = plive.get("time_remaining", 0)
        iters = d["profile_iterations_dict"].get(pid, 0)
        is_running = (is_active and pstatus == "Running")
        if is_running:
            running_count += 1
        pdetails.append({
            "id": pid,
            "name": pname,
            "email": email,
            "status": pstatus,
            "is_running": is_running,
            "time_remaining": time_rem,
            "duration_seconds": d["duration_seconds"],
            "iterations": iters,
        })
    d["profiles_detail"] = pdetails
    d["running_profiles_count"] = running_count
    return d


def create_automation(
    name: str,
    url: str,
    profile_ids: list[str],
    duration_seconds: int = 30,
    is_loop: bool = False,
    repeat_count: int = 1,
    vpn_delay_seconds: int = 15,
) -> str:
    auto_id = str(uuid.uuid4())
    now = now_iso()
    with db() as conn:
        conn.execute(
            """INSERT INTO automations(id, name, url, profile_ids, duration_seconds, vpn_delay_seconds,
               is_loop, repeat_count, current_iteration, status, profile_iterations, created_at, updated_at)
               VALUES(?,?,?,?,?,?,?,?,0,'Stopped','{}',?,?)""",
            (
                auto_id,
                name or "Untitled Automation",
                url,
                json.dumps(profile_ids),
                max(3, int(duration_seconds)),
                max(0, int(vpn_delay_seconds)),
                1 if is_loop else 0,
                max(1, int(repeat_count)),
                now,
                now,
            ),
        )
    return auto_id


def update_automation(
    auto_id: str,
    name: str,
    url: str,
    profile_ids: list[str],
    duration_seconds: int = 30,
    is_loop: bool = False,
    repeat_count: int = 1,
):
    now = now_iso()
    with db() as conn:
        conn.execute(
            """UPDATE automations
               SET name=?, url=?, profile_ids=?, duration_seconds=?,
                   is_loop=?, repeat_count=?, updated_at=?
               WHERE id=?""",
            (
                name or "Untitled Automation",
                url,
                json.dumps(profile_ids),
                max(3, int(duration_seconds)),
                1 if is_loop else 0,
                max(1, int(repeat_count)),
                now,
                auto_id,
            ),
        )


def delete_automation(auto_id: str):
    stop_automation(auto_id)
    with db() as conn:
        conn.execute("DELETE FROM automations WHERE id=?", (auto_id,))


def _set_status(auto_id: str, status: str, current_iteration: int | None = None):
    now = now_iso()
    with db() as conn:
        if current_iteration is not None:
            conn.execute(
                "UPDATE automations SET status=?, current_iteration=?, updated_at=? WHERE id=?",
                (status, current_iteration, now, auto_id),
            )
        else:
            conn.execute(
                "UPDATE automations SET status=?, updated_at=? WHERE id=?",
                (status, now, auto_id),
            )


def _get_mac_front_window_id() -> str | None:
    """Return the AppleScript window ID of Google Chrome's frontmost window on macOS."""
    if sys.platform != "darwin":
        return None
    import subprocess
    try:
        res = subprocess.run(
            ["osascript", "-e", 'tell application "Google Chrome" to get id of front window'],
            capture_output=True, text=True, timeout=3
        )
        wid = res.stdout.strip()
        return wid if wid.isdigit() else None
    except Exception:
        return None


def _close_tracked_window(auto_id: str, pid: str):
    """Close the exact tracked Chrome window for (auto_id, pid) from the DB."""
    with db() as conn:
        row = conn.execute(
            "SELECT window_id FROM automation_windows WHERE automation_id=? AND profile_id=?",
            (auto_id, pid),
        ).fetchone()
        conn.execute(
            "DELETE FROM automation_windows WHERE automation_id=? AND profile_id=?",
            (auto_id, pid),
        )
    if row and sys.platform == "darwin":
        import subprocess
        wid = row["window_id"]
        script = f'tell application "Google Chrome" to close (first window whose id is {wid})'
        subprocess.run(["osascript", "-e", script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)


def _save_tracked_window(auto_id: str, pid: str, window_id: str):
    """Persist the Chrome window ID for (auto_id, pid) in the DB."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    with db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO automation_windows (automation_id, profile_id, window_id, created_at) VALUES (?, ?, ?, ?)",
            (auto_id, pid, window_id, now),
        )


def _run_profile_task(
    auto_id: str,
    auto_name: str,
    pid: str,
    pname: str,
    url: str,
    duration: int,
    is_loop: bool,
    repeat_count: int,
    stop_event: threading.Event,
    prof_iters: dict,
    vpn_delay: int = 15,
):
    """Runs a single profile using direct Chrome launch + countdown."""
    profile = prm.get_profile(pid)

    def _on_status(st: str):
        with _lock:
            if auto_id in _live_state and pid in _live_state[auto_id]["profiles"]:
                _live_state[auto_id]["profiles"][pid]["status"] = st

    def _on_timer(rem: int):
        with _lock:
            if auto_id in _live_state and pid in _live_state[auto_id]["profiles"]:
                _live_state[auto_id]["profiles"][pid]["time_remaining"] = rem

    def _on_log(msg: str, lvl: str = "info"):
        add_log(auto_id, auto_name, msg, lvl)

    iteration = 0
    try:
        while not stop_event.is_set():
            iteration += 1
            with _lock:
                if auto_id in _live_state and pid in _live_state[auto_id]["profiles"]:
                    _live_state[auto_id]["profiles"][pid]["status"] = "Starting"
                    _live_state[auto_id]["profiles"][pid]["time_remaining"] = duration
                    _live_state[auto_id]["profiles"][pid]["current_iteration"] = iteration

            if not profile:
                add_log(auto_id, auto_name, f"Profile '{pname}' not found.", "error")
                break

            try:
                _close_tracked_window(auto_id, pid)
                prm.close(pid)
                time.sleep(0.5)
            except Exception:
                pass

            _on_status("Launching")
            add_log(auto_id, auto_name, f"Launching Chrome for '{pname}' -> {url}", "info")
            with _lock:
                ok, run_msg = prm.launch(pid, url=url)
                if ok and sys.platform == "darwin":
                    time.sleep(0.8)
                    wid = _get_mac_front_window_id()
                    if wid:
                        _save_tracked_window(auto_id, pid, wid)

            if not ok:
                add_log(auto_id, auto_name, f"Launch error for '{pname}': {run_msg}", "error")
                _on_status("Error")
                time.sleep(2)
                continue

            _on_status("Running")
            for rem in range(duration, 0, -1):
                if stop_event.is_set():
                    break
                _on_timer(rem)
                time.sleep(1)

            try:
                _close_tracked_window(auto_id, pid)
                prm.close(pid)
            except Exception:
                pass

            prof_iters[pid] = prof_iters.get(pid, 0) + 1

            with _lock:
                if auto_id in _live_state and pid in _live_state[auto_id]["profiles"]:
                    _live_state[auto_id]["profiles"][pid]["status"] = "Closed"
                    _live_state[auto_id]["profiles"][pid]["time_remaining"] = 0
                    _live_state[auto_id]["profiles"][pid]["iterations"] = prof_iters[pid]

            with db() as conn:
                conn.execute("UPDATE automations SET profile_iterations=? WHERE id=?",
                             (json.dumps(prof_iters), auto_id))

            add_log(auto_id, auto_name, f"'{pname}' session complete. Closed cleanly (Iteration {prof_iters[pid]}).", "success")

            if stop_event.is_set():
                break

            if not is_loop and iteration >= repeat_count:
                with _lock:
                    if auto_id in _live_state and pid in _live_state[auto_id]["profiles"]:
                        _live_state[auto_id]["profiles"][pid]["status"] = "Done"
                add_log(auto_id, auto_name, f"'{pname}' completed all {repeat_count} repetition(s).", "success")
                break

            # Brief pause before restarting repetition for this profile
            time.sleep(3)

    finally:
        try:
            prm.close(pid)
        except Exception:
            pass
        with _lock:
            if auto_id in _live_state and pid in _live_state[auto_id]["profiles"]:
                _live_state[auto_id]["profiles"][pid]["status"] = "Stopped"
                _live_state[auto_id]["profiles"][pid]["time_remaining"] = 0


def _run_worker(auto_id: str, stop_event: threading.Event):
    auto = get_automation(auto_id)
    if not auto:
        return

    url = auto["url"]
    pids = auto["profile_ids_list"]
    duration = int(auto["duration_seconds"])
    vpn_delay = int(auto.get("vpn_delay_seconds") if auto.get("vpn_delay_seconds") is not None else 15)
    is_loop = bool(auto["is_loop"])
    repeat_count = int(auto["repeat_count"])
    auto_name = auto["name"]

    try:
        prof_iters = json.loads(auto.get("profile_iterations") or "{}")
    except Exception:
        prof_iters = {}
    for pid in pids:
        prof_iters.setdefault(pid, 0)

    prof_names = {}
    for pid in pids:
        p = prm.get_profile(pid)
        prof_names[pid] = p["profile_name"] if p else pid[:8]

    # Initialize live state for all profiles
    profiles_live = {}
    for pid in pids:
        profiles_live[pid] = {
            "name": prof_names[pid],
            "status": "Starting",
            "time_remaining": duration,
            "duration_seconds": duration,
            "iterations": prof_iters.get(pid, 0),
        }

    with _lock:
        _live_state[auto_id] = {
            "status": "Running",
            "duration_seconds": duration,
            "profiles": profiles_live,
        }
    _set_status(auto_id, "Running")
    add_log(auto_id, auto_name, f"Starting all {len(pids)} profiles concurrently ({duration}s timer each)...", "info")

    # Start all profile threads concurrently, staggering launch by 0.6s so Chrome opens smoothly
    threads = []
    for pid in pids:
        if stop_event.is_set():
            break
        t = threading.Thread(
            target=_run_profile_task,
            args=(auto_id, auto_name, pid, prof_names[pid], url, duration, is_loop, repeat_count, stop_event, prof_iters, vpn_delay),
            daemon=True,
        )
        t.start()
        threads.append(t)
        time.sleep(0.6)

    # Wait for all profile threads to complete or stop
    for t in threads:
        t.join()

    # Once all profile tasks exit
    for pid in pids:
        try:
            prm.close(pid)
        except Exception:
            pass
    with _lock:
        _active_tasks.pop(auto_id, None)
        if auto_id in _live_state:
            _live_state[auto_id]["status"] = "Stopped"
    _set_status(auto_id, "Stopped")
    add_log(auto_id, auto_name, "Automation completed / stopped.", "info")


def start_automation(auto_id: str) -> tuple[bool, str]:
    with _lock:
        if auto_id in _active_tasks:
            return True, "Automation is already running."
        stop_event = threading.Event()
        _active_tasks[auto_id] = stop_event
        t = threading.Thread(target=_run_worker, args=(auto_id, stop_event), daemon=True)
        t.start()
    return True, "Automation started."


def stop_automation(auto_id: str) -> tuple[bool, str]:
    with _lock:
        stop_event = _active_tasks.pop(auto_id, None)
    if stop_event:
        stop_event.set()
        auto = get_automation(auto_id)
        if auto:
            for pid in auto.get("profile_ids_list", []):
                try:
                    prm.close(pid)
                except Exception:
                    pass
        _set_status(auto_id, "Stopped")
        add_log(auto_id, auto.get("name", "Automation") if auto else "Automation", "Stop requested by user.", "warn")
        return True, "Automation stopping..."

    # If app restarted while running, recover state and close lingering profiles
    auto = get_automation(auto_id)
    if auto:
        for pid in auto.get("profile_ids_list", []):
            try:
                _close_tracked_window(auto_id, pid)
                prm.close(pid)
            except Exception:
                pass
    _set_status(auto_id, "Stopped")
    return True, "Automation stopped."


def stop_all_automations():
    """Stop every active automation immediately (e.g. when membership expires/locks)."""
    with _lock:
        active_ids = list(_active_tasks.keys())
    for auto_id in active_ids:
        try:
            stop_automation(auto_id)
        except Exception:
            pass


WARMUP_SITES = [
    "https://www.youtube.com",
    "https://www.youtube.com/feed/trending",
    "https://www.youtube.com/shorts",
    "https://www.youtube.com/results?search_query=lofi+hip+hop",
    "https://www.youtube.com/results?search_query=nature+documentary+4k",
]


def start_warmup(profile_ids: list[str]) -> tuple[bool, str]:
    """Run a background warmup pass across selected profiles to build natural cookies/history."""
    import random

    if not profile_ids:
        return False, "No profiles selected for warmup."

    warmup_id = f"warmup-{str(uuid.uuid4())[:8]}"

    def _warmup_worker():
        add_log(warmup_id, "Profile Warmup", f"Starting warmup for {len(profile_ids)} profile(s)...", "info")
        for idx, pid in enumerate(profile_ids):
            prof = prm.get_profile(pid)
            pname = prof["profile_name"] if prof else pid
            sites = random.sample(WARMUP_SITES, k=min(2, len(WARMUP_SITES)))
            for site in sites:
                try:
                    _close_tracked_window(warmup_id, pid)
                    prm.close(pid)
                except Exception:
                    pass
                with _lock:
                    ok, msg = prm.launch(pid, url=site)
                    if ok and sys.platform == "darwin":
                        time.sleep(0.8)
                        wid = _get_mac_front_window_id()
                        if wid:
                            _save_tracked_window(warmup_id, pid, wid)
                if not ok:
                    add_log(warmup_id, "Profile Warmup", f"Warmup launch failed for '{pname}': {msg}", "error")
                    break
                wait_s = random.randint(10, 18)
                add_log(warmup_id, "Profile Warmup", f"Warming '{pname}' on {site} ({wait_s}s)...", "info")
                time.sleep(wait_s)
                try:
                    _close_tracked_window(warmup_id, pid)
                    prm.close(pid)
                except Exception:
                    pass
            if idx < len(profile_ids) - 1:
                time.sleep(random.uniform(1.5, 4.0))
        add_log(warmup_id, "Profile Warmup", "Warmup completed for all selected profiles.", "success")

    threading.Thread(target=_warmup_worker, daemon=True).start()
    return True, f"Warmup started for {len(profile_ids)} profile(s)."
