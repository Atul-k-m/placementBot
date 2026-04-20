"""
scheduler.py — Shared scheduling helpers used by worker.py.

The web process (main.py) never starts the scheduler.
Only worker.py starts and owns the scheduler instance.
This module exposes sync_user_job() so the web layer can still call it
during local development when running without a separate worker.
"""

import logging
from apscheduler.triggers.cron import CronTrigger
from database import SessionLocal, SQLALCHEMY_DATABASE_URL
from models import User
from bot_core import run_bot

log = logging.getLogger(__name__)


def _get_scheduler():
    """Import the scheduler lazily to avoid circular imports."""
    # Worker owns a BlockingScheduler; we only need a reference here for helpers
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
    return BackgroundScheduler(
        jobstores={"default": SQLAlchemyJobStore(url=SQLALCHEMY_DATABASE_URL)},
        timezone="UTC",
    )


def execute_user_bot(user_id: int):
    """Run the bot for a single user. Called by APScheduler."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user or not user.bot_enabled:
            log.info(f"[Job] User {user_id} not found or bot disabled — skipping.")
            return

        log.info(f"[Job] Running bot for user {user_id} ({user.email})")

        config = {
            "watch_senders":   user.watch_senders,
            "watch_keywords":  user.watch_keywords,
            "gmail_token_json": user.gmail_token_json,
            "twilio_sid":      user.twilio_sid,
            "twilio_token":    user.twilio_token,
            "twilio_from":     user.twilio_from,
            "whatsapp_phone":  user.whatsapp_phone,
            "enable_devpost":  user.enable_devpost,
            "enable_unstop":   user.enable_unstop,
        }
        run_bot(config)
    except Exception as e:
        log.error(f"[Job] Error for user {user_id}: {e}")
    finally:
        db.close()


def sync_user_job(scheduler_instance, user: User):
    """
    Add, reschedule, or remove a single user's cron job.
    Called by worker.py's sync_all_users() and can be called
    directly in local dev (single-process) mode.
    """
    job_id = f"user_bot_{user.id}"

    if not user.bot_enabled:
        if scheduler_instance.get_job(job_id):
            scheduler_instance.remove_job(job_id)
            log.info(f"[Sync] Removed job for user {user.id} (bot disabled)")
        return

    try:
        hour, minute = map(int, user.notification_time.split(":"))
    except Exception:
        hour, minute = 8, 0

    trigger = CronTrigger(hour=hour, minute=minute, timezone="UTC")

    if scheduler_instance.get_job(job_id):
        scheduler_instance.reschedule_job(job_id, trigger=trigger)
        log.info(f"[Sync] Rescheduled job for user {user.id} → {user.notification_time} UTC")
    else:
        scheduler_instance.add_job(
            execute_user_bot,
            trigger=trigger,
            id=job_id,
            args=[user.id],
            replace_existing=True,
        )
        log.info(f"[Sync] Added job for user {user.id} → {user.notification_time} UTC")


def sync_all_users(scheduler_instance):
    """
    Query all enabled users and register/update their jobs.
    Called by worker.py on startup and every 60 seconds after that.
    """
    db = SessionLocal()
    try:
        enabled_users = db.query(User).filter(User.bot_enabled == True).all()  # noqa: E712
        log.info(f"[Sync] {len(enabled_users)} active user(s) found — syncing…")

        active_ids = set()
        for user in enabled_users:
            sync_user_job(scheduler_instance, user)
            active_ids.add(f"user_bot_{user.id}")

        # Clean up jobs for users who have since disabled their bot
        for job in scheduler_instance.get_jobs():
            if job.id.startswith("user_bot_") and job.id not in active_ids:
                scheduler_instance.remove_job(job.id)
                log.info(f"[Sync] Removed stale job {job.id}")

    except Exception as e:
        log.error(f"[Sync] Error during user sync: {e}")
    finally:
        db.close()
