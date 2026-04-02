#!/usr/bin/env python3
"""Glass Agent — sidecar daemon that connects a silicon instance to Glass remote control."""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

POLL_INTERVAL = 15
LOG_CHUNK_MAX = 50_000  # bytes

# ── Config ───────────────────────────────────────────────────


def find_silicon_dir():
    """Find the silicon directory (where this script lives)."""
    return Path(__file__).resolve().parent


def load_config(silicon_dir):
    """Load .glass.json config."""
    config_path = silicon_dir / ".glass.json"
    if not config_path.exists():
        return None
    with open(config_path) as f:
        return json.load(f)


def get_silicon_name(silicon_dir):
    """Get silicon instance name from silicon.json."""
    sj = silicon_dir / "silicon.json"
    if sj.exists():
        try:
            data = json.loads(sj.read_text())
            return data.get("address") or data.get("name") or silicon_dir.name
        except Exception:
            pass
    return silicon_dir.name


# ── HTTP helpers ─────────────────────────────────────────────


def api_request(server_url, path, api_key, method="GET", data=None):
    """Make an HTTP request to Glass. Uses urllib to avoid extra dependencies."""
    import urllib.error
    import urllib.request

    url = server_url.rstrip("/") + path
    headers = {"Authorization": f"Bearer {api_key}"}

    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8"))
        except Exception:
            return {"error": str(e)}
    except Exception as e:
        return {"error": str(e)}


# ── Status detection ─────────────────────────────────────────


def detect_status(silicon_dir):
    """Detect if the silicon process is running."""
    pid_file = silicon_dir / ".silicon.pid"
    stop_file = silicon_dir / ".silicon.stop"

    if not pid_file.exists():
        return "stopped"

    try:
        pid = int(pid_file.read_text().strip())
        os.kill(pid, 0)  # check if alive
        return "running"
    except (ValueError, ProcessLookupError, PermissionError):
        if stop_file.exists():
            return "stopped"
        return "crashed"


# ── Command execution ────────────────────────────────────────


def execute_command(cmd, silicon_name):
    """Execute a remote command using the silicon CLI."""
    action = cmd.get("command", "")
    try:
        if action == "start":
            result = subprocess.run(
                ["silicon", "start", silicon_name],
                capture_output=True, text=True, timeout=30,
            )
            msg = result.stdout.strip() or result.stderr.strip() or "started"
            return "done", msg
        elif action == "stop":
            result = subprocess.run(
                ["silicon", "stop", silicon_name],
                capture_output=True, text=True, timeout=30,
            )
            msg = result.stdout.strip() or result.stderr.strip() or "stopped"
            return "done", msg
        elif action == "restart":
            subprocess.run(
                ["silicon", "stop", silicon_name],
                capture_output=True, text=True, timeout=30,
            )
            time.sleep(1)
            result = subprocess.run(
                ["silicon", "start", silicon_name],
                capture_output=True, text=True, timeout=30,
            )
            msg = result.stdout.strip() or result.stderr.strip() or "restarted"
            return "done", msg
        else:
            return "failed", f"unknown command: {action}"
    except subprocess.TimeoutExpired:
        return "failed", "command timed out"
    except FileNotFoundError:
        return "failed", "silicon CLI not found on PATH"
    except Exception as e:
        return "failed", str(e)


# ── Log streaming ────────────────────────────────────────────


class LogTailer:
    def __init__(self, log_path):
        self.path = log_path
        self.pos = 0
        # Start from end of file
        if self.path.exists():
            self.pos = self.path.stat().st_size

    def read_new(self):
        """Read new lines since last position. Returns string or empty."""
        if not self.path.exists():
            self.pos = 0
            return ""
        size = self.path.stat().st_size
        if size < self.pos:
            # File was truncated/rotated
            self.pos = 0
        if size == self.pos:
            return ""
        try:
            with open(self.path, "rb") as f:
                f.seek(self.pos)
                chunk = f.read(LOG_CHUNK_MAX)
                self.pos = f.tell()
            return chunk.decode("utf-8", errors="replace")
        except Exception:
            return ""


# ── Main loop ────────────────────────────────────────────────


def main():
    silicon_dir = find_silicon_dir()
    config = load_config(silicon_dir)
    if not config:
        print("[glass-agent] No .glass.json found. Exiting.", flush=True)
        sys.exit(1)

    server_url = config.get("server_url", "")
    api_key = config.get("api_key", "")
    if not server_url or not api_key:
        print("[glass-agent] Missing server_url or api_key in .glass.json. Exiting.", flush=True)
        sys.exit(1)

    silicon_name = get_silicon_name(silicon_dir)
    log_tailer = LogTailer(silicon_dir / ".silicon.log")
    agent_pid_file = silicon_dir / ".glass_agent.pid"

    # Write PID
    agent_pid_file.write_text(str(os.getpid()))

    # Clean shutdown
    running = True

    def handle_signal(signum, frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    print(f"[glass-agent] Started for '{silicon_name}' → {server_url}", flush=True)

    while running:
        try:
            # 1. Heartbeat
            status = detect_status(silicon_dir)
            api_request(server_url, "/control/api/heartbeat/", api_key, method="POST", data={
                "status": status,
            })

            # 2. Check for pending commands
            resp = api_request(server_url, "/control/api/commands/pending/", api_key)
            commands = resp.get("commands", []) if isinstance(resp, dict) else []
            for cmd in commands:
                cmd_id = cmd.get("id")
                if not cmd_id:
                    continue
                # ACK
                api_request(server_url, f"/control/api/commands/{cmd_id}/ack/", api_key, method="POST")
                # Execute
                result_status, result_msg = execute_command(cmd, silicon_name)
                # Complete
                api_request(server_url, f"/control/api/commands/{cmd_id}/complete/", api_key, method="POST", data={
                    "status": result_status,
                    "message": result_msg,
                })
                print(f"[glass-agent] {cmd.get('command')} → {result_status}: {result_msg}", flush=True)

            # 3. Stream logs
            new_lines = log_tailer.read_new()
            if new_lines:
                api_request(server_url, "/control/api/logs/", api_key, method="POST", data={
                    "lines": new_lines,
                })

        except Exception as e:
            print(f"[glass-agent] Error: {e}", flush=True)

        # Sleep in small increments so signal handling is responsive
        for _ in range(POLL_INTERVAL):
            if not running:
                break
            time.sleep(1)

    # Cleanup
    try:
        agent_pid_file.unlink(missing_ok=True)
    except Exception:
        pass
    print("[glass-agent] Stopped.", flush=True)


if __name__ == "__main__":
    main()
