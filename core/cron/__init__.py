import os
import json
import time
import importlib

import core.cron.jobs

HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "history.json")


def _load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE) as f:
            return json.load(f)
    return {}


def _save_history(history):
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)


def check_crons():
    """Check all cron jobs and execute any that are due.
    Returns {carbon_id: context_string}."""
    # Reload jobs module every tick so new/edited crons are picked up live
    importlib.reload(core.cron.jobs)
    jobs = core.cron.jobs.JOBS

    history = _load_history()
    results_by_carbon = {}

    for job in jobs:
        name = job["name"]
        carbon_id = job.get("carbon_id")
        trigger = job.get("trigger")

        # carbon_id is required for crons in multi-user system
        if trigger is None or not carbon_id:
            continue

        try:
            should_run = trigger(history.get(name))
        except Exception:
            should_run = False

        if not should_run:
            continue

        # Execute the job
        try:
            output = job["execute"]()
            if output:
                instructions = job.get("instructions", "")
                result_parts = [f"Cron '{name}'"]
                if instructions:
                    result_parts.append(f"Instructions: {instructions}")
                result_parts.append(f"Output: {output}")

                if carbon_id not in results_by_carbon:
                    results_by_carbon[carbon_id] = []
                results_by_carbon[carbon_id].append("\n".join(result_parts))

            history[name] = {"last_run": time.time()}

            # Run cleanup if present (used by checkbacks to remove themselves)
            cleanup = job.get("_cleanup")
            if cleanup:
                try:
                    cleanup()
                except Exception:
                    pass

        except Exception as e:
            on_error = job.get("on_error")
            if on_error:
                try:
                    on_error(str(e))
                except Exception:
                    pass
            history[name] = {"last_run": time.time(), "error": str(e)}

    _save_history(history)

    # Format into {carbon_id: string}
    result = {}
    for carbon_id, parts in results_by_carbon.items():
        result[carbon_id] = "\n\n".join(parts)

    return result
