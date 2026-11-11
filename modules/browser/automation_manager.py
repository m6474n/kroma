"""Background runner for browser profile automations."""
import json
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
    """Runs a single profile: launches, counts down its independent timer, and closes."""
    from urllib.parse import quote
    import config

    iteration = 0
    try:
        while not stop_event.is_set():
            iteration += 1
            with _lock:
                if auto_id in _live_state and pid in _live_state[auto_id]["profiles"]:
                    _live_state[auto_id]["profiles"][pid]["status"] = "Running"
                    _live_state[auto_id]["profiles"][pid]["time_remaining"] = duration
                    _live_state[auto_id]["profiles"][pid]["current_iteration"] = iteration

            # Determine launch URL: if vpn_delay > 0, open visual gateway countdown first
            if vpn_delay > 0:
                prep_url = f"http://{config.HOST}:{config.PORT}/vpn_prep?target={quote(url)}&wait={vpn_delay}"
                add_log(auto_id, auto_name, f"Launching '{pname}' ({vpn_delay}s Urban VPN window)...", "info")
                ok, launch_msg = prm.launch(pid, url=prep_url)
            else:
                add_log(auto_id, auto_name, f"Launching '{pname}' ({duration}s timer)...", "info")
                ok, launch_msg = prm.launch(pid, url=url)

            if not ok:
                add_log(auto_id, auto_name, f"Could not launch '{pname}': {launch_msg}", "error")
                with _lock:
                    if auto_id in _live_state and pid in _live_state[auto_id]["profiles"]:
                        _live_state[auto_id]["profiles"][pid]["status"] = "Error"
                time.sleep(2)
                continue

            # Wait for VPN activation window before countdown starts
            if vpn_delay > 0:
                for sec in range(vpn_delay):
                    if stop_event.is_set():
                        break
                    with _lock:
                        if auto_id in _live_state and pid in _live_state[auto_id]["profiles"]:
                            _live_state[auto_id]["profiles"][pid]["status"] = f"VPN Prep ({vpn_delay - sec}s)"
                    time.sleep(1)

                if stop_event.is_set():
                    break
                with _lock:
                    if auto_id in _live_state and pid in _live_state[auto_id]["profiles"]:
                        _live_state[auto_id]["profiles"][pid]["status"] = "Running"
                add_log(auto_id, auto_name, f"'{pname}' Urban VPN window complete. Running {duration}s on target URL.", "info")
            else:
                add_log(auto_id, auto_name, f"'{pname}' is active on target URL.", "info")

            # Countdown individual profile timer
            start_wait = time.time()
            while True:
                elapsed = int(time.time() - start_wait)
                rem = max(0, duration - elapsed)
                with _lock:
                    if auto_id in _live_state and pid in _live_state[auto_id]["profiles"]:
                        _live_state[auto_id]["profiles"][pid]["time_remaining"] = rem

                if elapsed >= duration or stop_event.is_set():
                    break
                time.sleep(1)

            # Close this profile independently when its timer expires
            prm.close(pid)
            prof_iters[pid] = prof_iters.get(pid, 0) + 1

            with _lock:
                if auto_id in _live_state and pid in _live_state[auto_id]["profiles"]:
                    _live_state[auto_id]["profiles"][pid]["status"] = "Closed"
                    _live_state[auto_id]["profiles"][pid]["time_remaining"] = 0
                    _live_state[auto_id]["profiles"][pid]["iterations"] = prof_iters[pid]

            with db() as conn:
                conn.execute("UPDATE automations SET profile_iterations=? WHERE id=?",
                             (json.dumps(prof_iters), auto_id))

            add_log(auto_id, auto_name, f"'{pname}' timer expired. Closed cleanly (Iteration {prof_iters[pid]}).", "success")

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
                prm.close(pid)
            except Exception:
                pass
    _set_status(auto_id, "Stopped")
    return True, "Automation stopped."
