"""
worker.py — Standalone APScheduler process for Render.com free tier.

Deploy as a separate 'worker' service in render.yaml.
  - Loads all enabled users from DB on startup and registers their cron jobs.
  - Syncs user settings from DB every 60 seconds (picks up changes without restart).
  - Self-pings the web service every 10 minutes (prevents Render free-tier cold starts).
  - Handles SIGTERM gracefully so Render can restart the worker cleanly.
"""

import os
import signal
import logging

import requests as http_req
from apscheduler.schedulers.background import BlockingScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.triggers.interval import IntervalTrigger

from database import SQLALCHEMY_DATABASE_URL
from scheduler import sync_all_users, execute_user_bot  # noqa: F401 (re-exported for APScheduler)
from opportunity_scraper import update_opportunities_cache

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("worker")

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
WEB_URL = os.environ.get("WEB_URL", "").rstrip("/")

# ---------------------------------------------------------------------------
# Scheduler (BlockingScheduler keeps the process alive forever)
# ---------------------------------------------------------------------------
scheduler = BlockingScheduler(
    jobstores={"default": SQLAlchemyJobStore(url=SQLALCHEMY_DATABASE_URL)},
    timezone="Asia/Kolkata",
)


# ---------------------------------------------------------------------------
# Self-ping — keeps the Render free-tier web service warm
# ---------------------------------------------------------------------------
def self_ping():
    if not WEB_URL:
        return
    try:
        resp = http_req.get(f"{WEB_URL}/health", timeout=10)
        log.info(f"[Ping] {WEB_URL}/health → HTTP {resp.status_code}")
    except Exception as exc:
        log.warning(f"[Ping] Could not reach web service: {exc}")


# ---------------------------------------------------------------------------
# Graceful shutdown on SIGTERM (Render sends this before killing the process)
# ---------------------------------------------------------------------------
def _handle_sigterm(signum, frame):
    log.info("[Worker] SIGTERM received — shutting down cleanly…")
    scheduler.shutdown(wait=False)
    raise SystemExit(0)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _handle_sigterm)

    log.info("=" * 60)
    log.info("  ReminderBot Worker — starting up")
    log.info(f"  DB        : {SQLALCHEMY_DATABASE_URL[:40]}…")
    log.info(f"  WEB_URL   : {WEB_URL or '(not set — self-ping disabled)'}")
    log.info("=" * 60)

    # --- Initial sync: register jobs for all currently-enabled users ---
    sync_all_users(scheduler)

    def _sync_wrapper():
        sync_all_users(scheduler)

    # --- Periodic re-sync every 60 s (picks up settings saved via web UI) ---
    scheduler.add_job(
        _sync_wrapper,
        trigger=IntervalTrigger(seconds=60),
        id="sync_all_users",
        replace_existing=True,
    )
    log.info("[Worker] Periodic user sync registered (every 60 s)")

    # --- Self-ping every 10 minutes ---
    if WEB_URL:
        scheduler.add_job(
            self_ping,
            trigger=IntervalTrigger(minutes=10),
            id="self_ping",
            replace_existing=True,
        )
        log.info("[Worker] Self-ping registered (every 10 min)")

    # --- Opportunities Cache Update every 6 hours ---
    scheduler.add_job(
        update_opportunities_cache,
        trigger=IntervalTrigger(hours=6),
        id="update_opportunities_cache",
        replace_existing=True,
    )
    # Run once on startup so the cache is populated immediately
    scheduler.add_job(
        update_opportunities_cache,
        id="update_opportunities_cache_startup",
        replace_existing=True,
    )
    log.info("[Worker] Opportunities cache periodic update registered (every 6 hours)")

    log.info("[Worker] Scheduler started — waiting for jobs…")
    try:
        scheduler.start()  # Blocks forever
    except (KeyboardInterrupt, SystemExit):
        log.info("[Worker] Stopped cleanly.")
