"""
Cron jobs for Silicon.
Every Cron must be stateless and work as expected even if the system is restarted.
Eg: Remind something in 1 hour should be defined using timestamps from when the request was made. It should be able to run correctly even if the system is restarted multiple times before the hour is up. The trigger function should check the current time against the stored timestamp to determine if it should run.
It should also be timezone agnostic, using UTC timestamps for scheduling and execution.

Each job is a dict with:
    name: str - unique identifier
    carbon_id: str - REQUIRED. The carbon_id this cron belongs to. Output goes to this carbon's manager.
    description: str - what it does
    trigger: callable(last_run_info) -> bool - returns True if job should run
    execute: callable() -> str - runs the job, returns output string
    instructions: str - context for the manager about what to do with the output
    on_error: callable(error_msg) - called if execute raises an exception

Example:
    {
        "name": "daily_summary",
        "carbon_id": "your-carbon-id",
        "description": "Summarize the day's activity",
        "trigger": lambda last: last is None or time.time() - last.get("last_run", 0) > 86400,
        "execute": lambda: "Time to summarize the day",
        "instructions": "Create a summary of today's activity and send it to Carbon",
        "on_error": lambda e: print(f"Summary error: {e}"),
    }
"""

import time
import os
from datetime import datetime, timezone
from core.cron.checkback import get_checkback_jobs


JOBS = []

# Unpack worker checkbacks into JOBS
JOBS.extend(get_checkback_jobs())
