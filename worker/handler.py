import subprocess
import os
import json
import time
import signal
import platform
import shutil

from prompts.DNA import get_worker_prompt

IS_WINDOWS = platform.system() == "Windows"

# On Windows, find the full path to claude so we don't need shell=True
CLAUDE_CMD = "claude"
if IS_WINDOWS:
    _claude_path = shutil.which("claude") or shutil.which("claude.cmd")
    if _claude_path:
        CLAUDE_CMD = _claude_path

OUTPUTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs")

ACTIVE_FILE = os.path.join(OUTPUTS_DIR, "_active_workers.json")
BROWSER_QUEUE_FILE = os.path.join(OUTPUTS_DIR, "_browser_queue.json")
ARCHIVE_META_FILE = os.path.join(OUTPUTS_DIR, "_archive_meta.json")

WORKER_DIR = os.path.dirname(os.path.abspath(__file__))
BROWSER_WORKER_MODEL = "sonnet"

# silicon-browser profile name (read from env.py, default 'silicon')
try:
    from env import BROWSER_PROFILE as _BROWSER_PROFILE
except ImportError:
    _BROWSER_PROFILE = "silicon"
SILICON_BROWSER_PROFILE = _BROWSER_PROFILE


# --- State persistence ---

def _load_active():
    if os.path.exists(ACTIVE_FILE):
        try:
            with open(ACTIVE_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, ValueError):
            return {}
    return {}


def _save_active(active):
    os.makedirs(OUTPUTS_DIR, exist_ok=True)
    with open(ACTIVE_FILE, "w") as f:
        json.dump(active, f, indent=2)


def _load_browser_queue():
    if os.path.exists(BROWSER_QUEUE_FILE):
        try:
            with open(BROWSER_QUEUE_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, ValueError):
            return []
    return []


def _save_browser_queue(queue):
    os.makedirs(OUTPUTS_DIR, exist_ok=True)
    with open(BROWSER_QUEUE_FILE, "w") as f:
        json.dump(queue, f, indent=2)


def _load_archive_meta():
    if os.path.exists(ARCHIVE_META_FILE):
        try:
            with open(ARCHIVE_META_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, ValueError):
            return {}
    return {}


def _save_archive_meta(meta):
    os.makedirs(OUTPUTS_DIR, exist_ok=True)
    with open(ARCHIVE_META_FILE, "w") as f:
        json.dump(meta, f, indent=2)


def _output_path(worker_id):
    return os.path.join(OUTPUTS_DIR, f"{worker_id}.txt")


# --- Internal helpers ---

def _is_profiled_browser_active():
    """Check if a profiled (non-incognito) browser worker is currently running."""
    active = _load_active()
    for info in active.values():
        if info.get("worker_type") == "browser" and not info.get("incognito", False):
            return True
    return False


def _get_silicon_browser_socket_dir():
    """Return the silicon-browser socket directory (mirrors daemon.js getSocketDir logic)."""
    override = os.environ.get("SILICON_BROWSER_SOCKET_DIR")
    if override:
        return override
    xdg = os.environ.get("XDG_RUNTIME_DIR")
    if xdg:
        return os.path.join(xdg, "silicon-browser")
    home = os.path.expanduser("~")
    if home:
        return os.path.join(home, ".silicon-browser")
    return os.path.join("/tmp", "silicon-browser")


def _kill_incognito_daemon_by_pid(worker_id):
    """Kill an incognito daemon directly via its PID file (fallback when 'close' fails)."""
    socket_dir = _get_silicon_browser_socket_dir()
    pid_file = os.path.join(socket_dir, f"incognito-{worker_id}.pid")
    if not os.path.exists(pid_file):
        return
    try:
        with open(pid_file) as f:
            pid = int(f.read().strip())
        os.kill(pid, signal.SIGTERM)
    except Exception:
        pass
    # Clean up stale files regardless
    for ext in (".pid", ".sock", ".stream"):
        try:
            fpath = os.path.join(socket_dir, f"incognito-{worker_id}{ext}")
            if os.path.exists(fpath):
                os.unlink(fpath)
        except Exception:
            pass


def _cleanup_silicon_browser_session(worker_id, worker_info):
    """Close the silicon-browser daemon session after an incognito browser worker finishes."""
    if worker_info.get("worker_type") != "browser":
        return
    if worker_info.get("incognito", False):
        try:
            result = subprocess.run(
                ["silicon-browser", "--session", f"incognito-{worker_id}", "close"],
                capture_output=True, timeout=10,
            )
            if result.returncode != 0:
                _kill_incognito_daemon_by_pid(worker_id)
        except Exception:
            _kill_incognito_daemon_by_pid(worker_id)


def sweep_orphaned_daemons():
    """Kill any incognito daemons whose worker IDs are no longer in active workers.

    Call this at startup and periodically to prevent daemon accumulation from
    workers that crashed or were killed before cleanup could run.
    Returns a list of worker_ids that were cleaned up.
    """
    socket_dir = _get_silicon_browser_socket_dir()
    if not os.path.exists(socket_dir):
        return []

    active = _load_active()
    active_worker_ids = set(active.keys())
    cleaned = []

    for fname in os.listdir(socket_dir):
        if not fname.startswith("incognito-") or not fname.endswith(".pid"):
            continue
        worker_id = fname[len("incognito-"):-len(".pid")]
        if worker_id not in active_worker_ids:
            _kill_incognito_daemon_by_pid(worker_id)
            cleaned.append(worker_id)

    return cleaned


def _launch_worker_process(worker_id, task, worker_type, carbon_id, incognito=False):
    """Actually launch the claude process for a worker. Returns status string."""
    os.makedirs(OUTPUTS_DIR, exist_ok=True)
    output_path = _output_path(worker_id)

    system_prompt, err = get_worker_prompt(worker_type)
    if err:
        return err

    prompt_flag = "--append-system-prompt" if worker_type == "terminal" else "--system-prompt"

    cmd = [
        CLAUDE_CMD, "-p",
        prompt_flag, system_prompt,
        "--dangerously-skip-permissions",
        "--output-format=stream-json",
        "--verbose",
    ]
    if worker_type == "browser":
        cmd.extend(["--model", BROWSER_WORKER_MODEL])

    cmd.append(task)

    # Set up environment for silicon-browser
    env = os.environ.copy()
    if worker_type == "browser":
        if incognito:
            env["SILICON_BROWSER_SESSION"] = f"incognito-{worker_id}"
        else:
            env["SILICON_BROWSER_SESSION"] = SILICON_BROWSER_PROFILE

    output_file = open(output_path, "w", encoding="utf-8")
    popen_kwargs = dict(
        stdout=output_file,
        stderr=subprocess.PIPE,
        env=env,
    )
    if IS_WINDOWS:
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["preexec_fn"] = os.setsid
    process = subprocess.Popen(cmd, **popen_kwargs)

    active = _load_active()
    active[worker_id] = {
        "pid": process.pid,
        "started": time.time(),
        "task": task,
        "worker_type": worker_type,
        "carbon_id": carbon_id,
        "output_path": output_path,
        "incognito": incognito,
    }
    _save_active(active)

    mode = "incognito" if incognito else "profiled"
    return f"Done. Worker '{worker_id}' ({worker_type}, {mode}) started (pid: {process.pid})"


def _process_browser_queue():
    """If no profiled browser worker is active, start the next one from the queue.
    Returns (result_string_or_None, carbon_id_or_None)."""
    if _is_profiled_browser_active():
        return None, None

    queue = _load_browser_queue()
    if not queue:
        return None, None

    next_job = queue.pop(0)
    _save_browser_queue(queue)

    worker_id = next_job["worker_id"]
    task = next_job["task"]
    carbon_id = next_job.get("carbon_id", "unknown")

    # Check the output file doesn't already exist
    output_path = _output_path(worker_id)
    if os.path.exists(output_path):
        return f"Error: Worker '{worker_id}' output file already exists when dequeuing.", carbon_id

    result = _launch_worker_process(worker_id, task, "browser", carbon_id)
    return f"[Browser Queue] Dequeued and started: {result}", carbon_id


# --- Public API: starting workers ---

def start_browser_worker(worker_id, task, carbon_id, incognito=False):
    """Start a browser worker. Profiled workers queue; incognito workers run immediately."""
    os.makedirs(OUTPUTS_DIR, exist_ok=True)
    output_path = _output_path(worker_id)

    if os.path.exists(output_path):
        return f"Error: Worker '{worker_id}' already has an output file. It may still be active."

    active = _load_active()
    if worker_id in active:
        return f"Error: Worker '{worker_id}' is already active."

    # Incognito workers run immediately in parallel — no queuing
    if incognito:
        return _launch_worker_process(worker_id, task, "browser", carbon_id, incognito=True)

    # --- Profiled worker: queue if another profiled browser is active ---
    queue = _load_browser_queue()
    if any(q["worker_id"] == worker_id for q in queue):
        return f"Error: Worker '{worker_id}' is already in the browser queue."

    if not _is_profiled_browser_active():
        return _launch_worker_process(worker_id, task, "browser", carbon_id, incognito=False)

    # Queue it
    queue.append({
        "worker_id": worker_id,
        "task": task,
        "carbon_id": carbon_id,
        "queued_at": time.time(),
    })
    _save_browser_queue(queue)

    position = len(queue)
    return f"Done. Worker '{worker_id}' (browser) queued at position {position}. Will start when current profiled browser worker finishes."


def start_terminal_worker(worker_id, task, carbon_id):
    """Start a terminal worker. Runs in parallel with other terminal workers."""
    os.makedirs(OUTPUTS_DIR, exist_ok=True)
    output_path = _output_path(worker_id)

    if os.path.exists(output_path):
        return f"Error: Worker '{worker_id}' already has an output file. It may still be active."

    active = _load_active()
    if worker_id in active:
        return f"Error: Worker '{worker_id}' is already active."

    return _launch_worker_process(worker_id, task, "terminal", carbon_id)


def start_writer_worker(worker_id, task, carbon_id):
    """Start a writer worker. Runs in parallel with other workers."""
    os.makedirs(OUTPUTS_DIR, exist_ok=True)
    output_path = _output_path(worker_id)

    if os.path.exists(output_path):
        return f"Error: Worker '{worker_id}' already has an output file. It may still be active."

    active = _load_active()
    if worker_id in active:
        return f"Error: Worker '{worker_id}' is already active."

    return _launch_worker_process(worker_id, task, "writer", carbon_id)


def start_worker(worker_id, task, worker_type, carbon_id, incognito=False):
    """Route to the correct worker start function based on type."""
    if not worker_type:
        return "Error: worker_type is required. Available types: browser, terminal, writer"

    worker_type = worker_type.lower()
    if worker_type == "browser":
        return start_browser_worker(worker_id, task, carbon_id, incognito=incognito)
    elif worker_type == "terminal":
        return start_terminal_worker(worker_id, task, carbon_id)
    elif worker_type == "writer":
        return start_writer_worker(worker_id, task, carbon_id)
    else:
        return f"Error: invalid worker_type '{worker_type}'. Available types: browser, terminal, writer"


# --- Public API: querying, stopping, listing ---

def get_worker_status(worker_id, carbon_id):
    """Get the current status and output of a running worker. Only if it belongs to this carbon."""
    # Check if it's in the browser queue
    queue = _load_browser_queue()
    for i, q in enumerate(queue):
        if q["worker_id"] == worker_id:
            if q.get("carbon_id") != carbon_id:
                return f"Error: Worker '{worker_id}' does not belong to you."
            return f"Worker '{worker_id}' status: queued (position {i+1} in browser queue)"

    active = _load_active()
    if worker_id in active and active[worker_id].get("carbon_id") != carbon_id:
        return f"Error: Worker '{worker_id}' does not belong to you."

    output_path = _output_path(worker_id)
    if not os.path.exists(output_path):
        return f"Error: Worker '{worker_id}' not found."

    with open(output_path) as f:
        raw = f.read()

    parsed = _parse_worker_output(raw)

    pid = active.get(worker_id, {}).get("pid")
    worker_type = active.get(worker_id, {}).get("worker_type", "unknown")

    still_running = False
    if pid:
        try:
            os.kill(pid, 0)
            still_running = True
        except (OSError, ProcessLookupError):
            still_running = False

    status = "running" if still_running else "completed"
    return f"Worker '{worker_id}' ({worker_type}) status: {status}\n\nOutput so far:\n{parsed}"


def stop_worker(worker_id, carbon_id):
    """Stop a running worker or remove from queue. Only if it belongs to this carbon."""
    # Check if it's in the browser queue first
    queue = _load_browser_queue()
    found_in_queue = False
    for q in queue:
        if q["worker_id"] == worker_id:
            if q.get("carbon_id") != carbon_id:
                return f"Error: Worker '{worker_id}' does not belong to you."
            found_in_queue = True
            break

    if found_in_queue:
        new_queue = [q for q in queue if q["worker_id"] != worker_id]
        _save_browser_queue(new_queue)
        try:
            from core.cron.checkback import remove_checkback
            remove_checkback(worker_id)
        except Exception:
            pass
        return f"Done. Worker '{worker_id}' removed from browser queue."

    active = _load_active()
    if worker_id not in active:
        return f"Error: Worker '{worker_id}' is not active."

    if active[worker_id].get("carbon_id") != carbon_id:
        return f"Error: Worker '{worker_id}' does not belong to you."

    worker_info = active[worker_id]
    pid = worker_info["pid"]
    worker_type = worker_info.get("worker_type", "unknown")

    try:
        if IS_WINDOWS:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                           capture_output=True, timeout=10)
        else:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
    except (OSError, ProcessLookupError):
        pass

    # Clean up silicon-browser session for incognito workers
    _cleanup_silicon_browser_session(worker_id, worker_info)

    del active[worker_id]
    _save_active(active)

    try:
        from core.cron.checkback import remove_checkback
        remove_checkback(worker_id)
    except Exception:
        pass

    output_path = _output_path(worker_id)
    if os.path.exists(output_path):
        timestamp = int(time.time())
        archive_id = f"{worker_id}-{timestamp}"
        archive_path = os.path.join(OUTPUTS_DIR, f"{archive_id}.txt")
        os.rename(output_path, archive_path)

        meta = _load_archive_meta()
        meta[archive_id] = {"carbon_id": carbon_id, "worker_type": worker_type, "task": worker_info.get("task", ""), "archived_at": timestamp}
        _save_archive_meta(meta)

        return f"Done. Worker '{worker_id}' stopped. Output archived as '{archive_id}'"

    # Trigger queue processing in case this was a profiled browser worker
    _process_browser_queue()
    return f"Done. Worker '{worker_id}' stopped."


def list_active(carbon_id):
    """List active and queued workers for a specific carbon."""
    active = _load_active()
    queue = _load_browser_queue()

    # Filter by carbon_id
    my_active = {wid: info for wid, info in active.items() if info.get("carbon_id") == carbon_id}
    my_queue = [q for q in queue if q.get("carbon_id") == carbon_id]

    if not my_active and not my_queue:
        return "No active or queued workers."

    lines = []
    if my_active:
        for wid, info in my_active.items():
            elapsed = time.time() - info["started"]
            minutes = int(elapsed // 60)
            wtype = info.get("worker_type", "unknown")
            lines.append(f"- {wid} ({wtype}, pid: {info['pid']}, running for {minutes}m, task: {info['task'][:80]})")

    if my_queue:
        lines.append("")
        lines.append("Browser queue (your position in global queue):")
        for i, q in enumerate(queue):
            if q.get("carbon_id") == carbon_id:
                lines.append(f"  position {i+1}. {q['worker_id']} (task: {q['task'][:80]})")

    return "Active workers:\n" + "\n".join(lines)


def list_archive(carbon_id):
    """List archived worker outputs for a specific carbon."""
    if not os.path.exists(OUTPUTS_DIR):
        return "No archives."

    meta = _load_archive_meta()
    archives = []

    for archive_id, info in meta.items():
        if info.get("carbon_id") == carbon_id:
            fpath = os.path.join(OUTPUTS_DIR, f"{archive_id}.txt")
            if os.path.exists(fpath):
                archives.append(archive_id)

    if not archives:
        return "No archives."

    return "Your archived workers:\n" + "\n".join(f"- {a}" for a in sorted(archives))


def read_archive(archive_id, carbon_id):
    """Read the complete output of an archived worker. Only if it belongs to this carbon."""
    meta = _load_archive_meta()
    archive_info = meta.get(archive_id)

    if archive_info and archive_info.get("carbon_id") != carbon_id:
        return f"Error: Archive '{archive_id}' does not belong to you."

    archive_path = os.path.join(OUTPUTS_DIR, f"{archive_id}.txt")
    if not os.path.exists(archive_path):
        return f"Error: Archive '{archive_id}' not found."

    with open(archive_path) as f:
        raw = f.read()

    return _parse_worker_output(raw)


# --- Event loop handlers ---

def _has_result_event(output_path):
    """Check if the worker output file contains a result event (meaning it's done)."""
    if not os.path.exists(output_path):
        return False
    try:
        with open(output_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    if event.get("type") == "result":
                        return True
                except (json.JSONDecodeError, ValueError):
                    pass
    except Exception:
        pass
    return False


_sweep_call_counter = 0
_SWEEP_INTERVAL = 10  # run orphan sweep every N check_completed_workers calls


def check_completed_workers():
    """Check for workers that finished. Returns {carbon_id: [completed_info, ...]}."""
    global _sweep_call_counter
    _sweep_call_counter += 1
    if _sweep_call_counter >= _SWEEP_INTERVAL:
        _sweep_call_counter = 0
        sweep_orphaned_daemons()

    active = _load_active()
    completed_by_carbon = {}
    had_browser_completion = False
    meta = _load_archive_meta()
    meta_changed = False

    for worker_id in list(active.keys()):
        output_path = _output_path(worker_id)

        if not _has_result_event(output_path):
            continue

        worker_type = active[worker_id].get("worker_type", "unknown")
        carbon_id = active[worker_id].get("carbon_id", "unknown")

        if worker_type == "browser" and not active[worker_id].get("incognito", False):
            had_browser_completion = True

        # Clean up silicon-browser session for incognito workers
        _cleanup_silicon_browser_session(worker_id, active[worker_id])

        # Worker is done - read and archive
        result_text = ""
        archive_id = worker_id
        if os.path.exists(output_path):
            with open(output_path) as f:
                raw = f.read()
            result_text = _parse_worker_output(raw)

            timestamp = int(time.time())
            archive_id = f"{worker_id}-{timestamp}"
            archive_path = os.path.join(OUTPUTS_DIR, f"{archive_id}.txt")
            os.rename(output_path, archive_path)

            # Store archive metadata
            meta[archive_id] = {
                "carbon_id": carbon_id,
                "worker_type": worker_type,
                "task": active[worker_id].get("task", ""),
                "archived_at": timestamp,
            }
            meta_changed = True

        del active[worker_id]

        # Remove any checkback for this worker since it's done
        try:
            from core.cron.checkback import remove_checkback
            remove_checkback(worker_id)
        except Exception:
            pass

        if carbon_id not in completed_by_carbon:
            completed_by_carbon[carbon_id] = []

        completed_by_carbon[carbon_id].append({
            "worker_id": worker_id,
            "worker_type": worker_type,
            "carbon_id": carbon_id,
            "archive_id": archive_id,
            "result": result_text,
        })

    if completed_by_carbon:
        _save_active(active)
    if meta_changed:
        _save_archive_meta(meta)

    # Always try to start the next queued browser worker
    queue_result, queue_carbon_id = _process_browser_queue()
    if queue_result and queue_carbon_id:
        if queue_carbon_id not in completed_by_carbon:
            completed_by_carbon[queue_carbon_id] = []
        completed_by_carbon[queue_carbon_id].append({
            "worker_id": "[queue]",
            "worker_type": "browser",
            "carbon_id": queue_carbon_id,
            "archive_id": "",
            "result": queue_result,
        })

    return completed_by_carbon


def check_completed_workers_formatted():
    """Event loop handler: returns {carbon_id: context_string}."""
    completed_by_carbon = check_completed_workers()
    if not completed_by_carbon:
        return {}

    result = {}
    for carbon_id, completed in completed_by_carbon.items():
        parts = []
        for c in completed:
            if c["worker_id"] == "[queue]":
                parts.append(c["result"])
            else:
                parts.append(
                    f"Worker '{c['worker_id']}' ({c['worker_type']}) completed:\n"
                    f"Result: {c['result']}\n"
                    f"Complete worker output archived with id: {c['archive_id']}"
                )
        result[carbon_id] = "\n\n".join(parts)
    return result


def clean_old_archives(archive_for_seconds):
    """Remove archived worker outputs older than archive_for_seconds."""
    if not os.path.exists(OUTPUTS_DIR):
        return {}

    now = time.time()
    meta = _load_archive_meta()
    meta_changed = False

    for fname in os.listdir(OUTPUTS_DIR):
        if fname.startswith("_") or fname == ".gitkeep":
            continue
        fpath = os.path.join(OUTPUTS_DIR, fname)
        if os.path.isfile(fpath):
            age = now - os.path.getmtime(fpath)
            if age > archive_for_seconds:
                os.remove(fpath)
                base = fname.replace(".txt", "")
                if base in meta:
                    del meta[base]
                    meta_changed = True

    if meta_changed:
        _save_archive_meta(meta)

    return {}


# --- Output parsing ---

def _parse_worker_output(raw):
    """Parse stream-json output from a claude worker process.
    Extracts the final result or the latest assistant text."""
    if not raw.strip():
        return "No output yet."

    lines = raw.strip().split("\n")
    events = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except (json.JSONDecodeError, ValueError):
            pass

    if not events:
        return "No parseable output yet."

    # Check for a result event (means worker finished)
    result_event = None
    for e in events:
        if e.get("type") == "result":
            result_event = e

    if result_event and result_event.get("result"):
        return result_event["result"]

    # Otherwise collect assistant text blocks
    texts = []
    seen = set()
    for e in events:
        if e.get("type") == "assistant" and e.get("message", {}).get("content"):
            for block in e["message"]["content"]:
                if block.get("type") == "text":
                    txt = block.get("text", "").strip()
                    if txt and txt not in seen:
                        seen.add(txt)
                        texts.append(txt)

    if texts:
        return texts[-1]

    return "Worker running, no text output yet."
