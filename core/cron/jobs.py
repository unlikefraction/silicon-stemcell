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

IST to UTC conversion:
    IST = UTC + 5:30
    1:00 PM IST = 7:30 AM UTC
    2:00 PM IST = 8:30 AM UTC
    5:00 PM IST = 11:30 AM UTC
    4:00 AM IST = 10:30 PM UTC (previous day)
    5:00 AM IST = 11:30 PM UTC (previous day)
"""

import time
import os
from datetime import datetime, timezone, timedelta
from core.cron.checkback import get_checkback_jobs


# ============================================
# HELPER: daily trigger at specific UTC hour:minute
# ============================================
def _make_daily_trigger(hour_utc, minute_utc=0):
    """Create a trigger that fires once per day at the given UTC time."""
    def trigger(last_run_info):
        now = datetime.now(timezone.utc)
        target = now.replace(hour=hour_utc, minute=minute_utc, second=0, microsecond=0)
        if now < target:
            return False
        if last_run_info is None:
            return True
        last_run = last_run_info.get("last_run", 0)
        last_run_dt = datetime.fromtimestamp(last_run, tz=timezone.utc)
        return last_run_dt < target
    return trigger


# ============================================
# HELPER: recurring trigger every N minutes
# ============================================
def _make_recurring_trigger(interval_minutes):
    """Create a trigger that fires every N minutes."""
    interval_seconds = interval_minutes * 60
    def trigger(last_run_info):
        if last_run_info is None:
            return True
        last_run = last_run_info.get("last_run", 0)
        return time.time() - last_run >= interval_seconds
    return trigger


# ============================================
# HELPER: get today's date string
# ============================================
def _today_str():
    """Get today's date as YYYY-MM-DD in UTC."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ============================================
# 1. RESEARCH - 1:00 PM IST (7:30 AM UTC)
# ============================================
JOBS = [
    {
        "name": "daily_research",
        "carbon_id": "shubham",
        "description": "Daily research phase - trending topics, competitor moves, interesting conversations",
        "trigger": _make_daily_trigger(7, 30),
        "execute": lambda: (
            f"research time. date: {_today_str()}\n"
            "1. spawn browser workers to check trending on twitter, linkedin, reddit in AI/education/tech/startup spaces\n"
            "2. find interesting conversations, hot takes, news to react to\n"
            "3. check what competitors are doing\n"
            "4. write research findings to today's daily log: prompts/memory/projects/daily-logs/{date}.md\n"
            "5. this research feeds into the content writing phase at 2:00 PM IST"
        ),
        "instructions": (
            "Time to research. Spawn browser workers to check what's trending on Twitter, LinkedIn, and Reddit. "
            "Look for AI/education/tech conversations we can jump into. Write findings to today's daily log. "
            "This feeds the content writing phase in 1 hour."
        ),
    },

    # ============================================
    # 2. WRITE POSTS - 2:00 PM IST (8:30 AM UTC)
    # ============================================
    {
        "name": "daily_write_posts",
        "carbon_id": "shubham",
        "description": "Write today's posts based on research",
        "trigger": _make_daily_trigger(8, 30),
        "execute": lambda: (
            f"content writing time. date: {_today_str()}\n"
            "1. read today's research from daily log\n"
            "2. write 3-5 tweets (follow voice guide at prompts/worker/skills/social-voice-guide.md)\n"
            "3. write 1-2 linkedin posts\n"
            "4. write 1-2 reddit posts + identify threads to comment in\n"
            "5. send drafts to shubham for review\n"
            "6. tag each tweet for experiments (EXP-001: length, EXP-002: opinion vs value)\n"
            "7. if no response from shubham in 30 min, assume approved"
        ),
        "instructions": (
            "Time to write posts. Use today's research and the voice guide. "
            "Write tweets, linkedin posts, and reddit content. Send drafts to Shubham for review. "
            "If no response in 30 min, assume approved. Tag tweets for active experiments in lab.md."
        ),
    },

    # ============================================
    # 3. POST EVERYTHING - 5:00 PM IST (11:30 AM UTC)
    # ============================================
    {
        "name": "daily_post_everything",
        "carbon_id": "shubham",
        "description": "Post all approved content across platforms",
        "trigger": _make_daily_trigger(11, 30),
        "execute": lambda: (
            f"posting time. date: {_today_str()}\n"
            "1. post all approved tweets from @45d_silicon\n"
            "2. post linkedin content from company page (linkedin.com/company/45deg)\n"
            "3. post reddit content from u/Last-Plane-5663\n"
            "4. log all posted content with links in today's daily log\n"
            "5. note posting times for EXP-003 (linkedin timing experiment)"
        ),
        "instructions": (
            "Time to post everything. Use browser workers to post on Twitter (@45d_silicon), "
            "LinkedIn (company page), and Reddit (u/Last-Plane-5663). "
            "Log all posted content with links to today's daily log."
        ),
    },

    # ============================================
    # 4. HOURLY COMMENT CHECK - every 60 minutes
    # ============================================
    {
        "name": "hourly_engagement_check",
        "carbon_id": "shubham",
        "description": "Check for comments, replies, DMs across all platforms and respond",
        "trigger": _make_recurring_trigger(60),
        "execute": lambda: (
            "hourly engagement check.\n"
            "1. check twitter notifications - replies, mentions, DMs on @45d_silicon and @45d_ai\n"
            "2. check linkedin notifications on company page\n"
            "3. check reddit replies on u/Last-Plane-5663\n"
            "4. respond to everything worth responding to. be genuine, be helpful, use the voice.\n"
            "5. log any notable interactions in today's daily log"
        ),
        "instructions": (
            "Hourly engagement check. Spawn browser workers to check notifications on all platforms. "
            "Reply to comments, mentions, DMs. Be genuine, follow the voice guide. "
            "Log notable interactions. Also check if there's anything else we should be doing right now."
        ),
    },

    # ============================================
    # 5. EXPLORATION - every 3 hours
    # ============================================
    {
        "name": "exploration_sweep",
        "carbon_id": "shubham",
        "description": "Explore all platforms for new conversations to join. Min 2-3 per platform.",
        "trigger": _make_recurring_trigger(180),
        "execute": lambda: (
            "exploration time.\n"
            "1. twitter: find 3+ interesting tweets/threads in AI/education/tech to reply to. reply with 45d's perspective. be the smartest voice.\n"
            "2. linkedin: find 3+ posts to comment on. add genuine value.\n"
            "3. reddit: find 3+ threads in relevant subreddits to comment in. be helpful first.\n"
            "4. if something is really hot (going viral, major news), create reactive content immediately.\n"
            "5. tag @unlikefraction or @45d_ai on twitter when relevant.\n"
            "6. log all engagements in today's daily log.\n"
            "7. note any comments for EXP-004 (reddit helpful vs promotional)"
        ),
        "instructions": (
            "Exploration sweep. Find new conversations across all 3 platforms. "
            "Minimum 2-3 replies/comments per platform, more if things are hot. "
            "Reply aggressively on Twitter. Tag @unlikefraction or @45d_ai when relevant. "
            "Log everything. If something is trending hard, create reactive content on the spot."
        ),
    },

    # ============================================
    # 6. DAILY REPORT - 4:00 AM IST (10:30 PM UTC)
    # ============================================
    {
        "name": "daily_report",
        "carbon_id": "shubham",
        "description": "End of day report - compile everything into daily log",
        "trigger": _make_daily_trigger(22, 30),
        "execute": lambda: (
            f"daily report time. date: {_today_str()}\n"
            "1. compile everything we did today into prompts/memory/projects/daily-logs/{date}.md\n"
            "2. list all content posted with links\n"
            "3. engagement numbers (impressions, likes, replies, comments)\n"
            "4. notable interactions\n"
            "5. what worked, what didn't\n"
            "6. update experiment data in lab.md\n"
            "7. any insights or learnings to add to memory"
        ),
        "instructions": (
            "End of day. Compile a full report of everything done today. "
            "Check engagement numbers on all posts. Update the daily log with results. "
            "Update experiment data in lab.md. Write learnings to memory if any. "
            "Send a summary to Shubham."
        ),
    },

    # ============================================
    # 7. LAB REVIEW - 5:00 AM IST (11:30 PM UTC)
    # ============================================
    {
        "name": "lab_review",
        "carbon_id": "shubham",
        "description": "Review experiments in lab.md - update data, draw conclusions, start new experiments",
        "trigger": _make_daily_trigger(23, 30),
        "execute": lambda: (
            f"lab review time. date: {_today_str()}\n"
            "1. read prompts/memory/projects/lab.md\n"
            "2. update all active experiments with today's data\n"
            "3. check if any experiment has enough data to draw conclusions\n"
            "4. if conclusion reached: write it up, move to completed, note what we learned\n"
            "5. check if we should start new experiments based on what we've learned\n"
            "6. make sure each experiment documents its scientific rigor\n"
            "7. update plan.md if experiments suggest strategy changes"
        ),
        "instructions": (
            "Lab review time. Read lab.md, update experiments with today's data. "
            "Draw conclusions if enough data. Start new experiments if warranted. "
            "Update plan.md if strategy needs to change based on findings."
        ),
    },
    # ============================================
    # 8. HEARTBEAT - every 15 minutes
    # ============================================
    {
        "name": "heartbeat",
        "carbon_id": "shubham",
        "description": "15-minute heartbeat. Check what's happening, what can we do, stay active.",
        "trigger": _make_recurring_trigger(15),
        "execute": lambda: (
            "heartbeat pulse.\n"
            "check:\n"
            "1. any running workers that need attention?\n"
            "2. any pending tasks in plan.md?\n"
            "3. anything happening on socials right now worth jumping on?\n"
            "4. any cron outputs we haven't acted on?\n"
            "5. can we do something proactive right now? reply to a thread, write a new tweet, engage with someone?\n"
            "6. check memory - anything we said we'd do that we haven't done yet?\n"
            "rule: never be idle. always be doing something."
        ),
        "instructions": (
            "Heartbeat check. You should never be idle. Look at what's pending, what workers are running, "
            "what you can do right now. If nothing's urgent, do an exploration - find a tweet to reply to, "
            "a linkedin post to comment on, something. Stay active. Stay in conversations. "
            "Don't spam shubham with heartbeat updates unless there's something worth sharing."
        ),
    },
]

# Unpack worker checkbacks into JOBS
JOBS.extend(get_checkback_jobs())
