"""
Checkback system for workers.

When a manager starts a worker with checkback_in (minutes), a one-time cron job is created.
When it triggers, it runs the worker's status check and returns the result to the manager.
When the worker completes, the checkback is automatically removed.

Checkbacks are stored in a JSON file and unpacked into cron JOBS.
"""

import os
import json
import time

from worker.handler import get_worker_status

CHECKBACK_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "checkbacks.json")


def _load_checkbacks():
    if os.path.exists(CHECKBACK_FILE):
        with open(CHECKBACK_FILE) as f:
            return json.load(f)
    return {}


def _save_checkbacks(checkbacks):
    with open(CHECKBACK_FILE, "w") as f:
        json.dump(checkbacks, f, indent=2)


def add_checkback(worker_id, carbon_id, checkback_in_minutes):
    """Add a checkback for a worker. checkback_in_minutes from now."""
    checkbacks = _load_checkbacks()
    trigger_at = time.time() + (checkback_in_minutes * 60)
    checkbacks[worker_id] = {
        "carbon_id": carbon_id,
        "trigger_at": trigger_at,
        "checkback_minutes": checkback_in_minutes,
    }
    _save_checkbacks(checkbacks)


def remove_checkback(worker_id):
    """Remove a checkback for a worker (e.g. when the worker finishes)."""
    checkbacks = _load_checkbacks()
    if worker_id in checkbacks:
        del checkbacks[worker_id]
        _save_checkbacks(checkbacks)


def get_checkback_jobs():
    """Convert active checkbacks into cron job dicts that can be unpacked into JOBS."""
    checkbacks = _load_checkbacks()
    jobs = []

    for worker_id, info in checkbacks.items():
        carbon_id = info["carbon_id"]
        trigger_at = info["trigger_at"]

        def make_trigger(t):
            return lambda last: last is None and time.time() >= t

        def make_execute(wid, cid):
            def execute():
                status = get_worker_status(wid, cid)
                return f"Checkback for worker '{wid}':\n{status}"
            return execute

        def make_cleanup(wid):
            def cleanup():
                remove_checkback(wid)
            return cleanup

        jobs.append({
            "name": f"checkback_{worker_id}",
            "carbon_id": carbon_id,
            "description": f"Checkback on worker '{worker_id}'",
            "trigger": make_trigger(trigger_at),
            "execute": make_execute(worker_id, carbon_id),
            "instructions": f"Worker '{worker_id}' checkback triggered. Here's the status. Decide if you need to check again (use the checkback tool) or if the worker is done.",
            "on_error": lambda e: None,
            "_cleanup": make_cleanup(worker_id),
        })

    return jobs
