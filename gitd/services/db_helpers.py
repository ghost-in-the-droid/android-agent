"""
SQLAlchemy-based DB helpers — replacements for legacy db.py functions.

All functions take a SQLAlchemy Session instead of a raw sqlite3 connection.
Used by FastAPI routers to avoid importing from gitd.db.
"""

import json
import logging

from sqlalchemy.orm import Session

from gitd.models import (
    BotRun,
    JobQueue,
    ScheduledJob,
    TikTokAccount,
)
from gitd.services._job_helpers import _now  # noqa: F401

logger = logging.getLogger(__name__)

# ── Job queue ─────────────────────────────────────────────────────────────────


def enqueue_job(db: Session, **kwargs) -> int:
    """Insert a job into job_queue, return its id."""
    if "config_json" in kwargs and isinstance(kwargs["config_json"], dict):
        kwargs["config_json"] = json.dumps(kwargs["config_json"])
    kwargs.setdefault("status", "pending")

    job = JobQueue(
        scheduled_job_id=kwargs.get("scheduled_job_id"),
        phone_serial=kwargs.get("phone_serial"),
        job_type=kwargs.get("job_type", ""),
        priority=kwargs.get("priority"),
        config_json=kwargs.get("config_json"),
        max_duration_s=kwargs.get("max_duration_s"),
        status=kwargs.get("status"),
        trigger=kwargs.get("trigger"),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job.id


# ── Scheduled jobs ────────────────────────────────────────────────────────────


def create_scheduled_job(db: Session, **kwargs) -> int:
    """Insert a scheduled job, return its id."""
    if "daily_times" in kwargs and isinstance(kwargs["daily_times"], list):
        kwargs["daily_times"] = json.dumps(kwargs["daily_times"])
    if "config_json" in kwargs and isinstance(kwargs["config_json"], dict):
        kwargs["config_json"] = json.dumps(kwargs["config_json"])

    job = ScheduledJob(
        name=kwargs.get("name", ""),
        job_type=kwargs.get("job_type", ""),
        phone_serial=kwargs.get("phone_serial"),
        priority=kwargs.get("priority"),
        schedule_type=kwargs.get("schedule_type", ""),
        interval_minutes=kwargs.get("interval_minutes"),
        daily_times=kwargs.get("daily_times"),
        config_json=kwargs.get("config_json"),
        max_duration_s=kwargs.get("max_duration_s"),
        is_enabled=kwargs.get("is_enabled"),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job.id


def update_scheduled_job(db: Session, job_id: int, **kwargs):
    """Update allowed fields on a scheduled job."""
    allowed = {
        "name",
        "job_type",
        "phone_serial",
        "priority",
        "schedule_type",
        "interval_minutes",
        "daily_times",
        "config_json",
        "max_duration_s",
        "is_enabled",
    }
    vals = {k: v for k, v in kwargs.items() if k in allowed}
    if "daily_times" in vals and isinstance(vals["daily_times"], list):
        vals["daily_times"] = json.dumps(vals["daily_times"])
    if "config_json" in vals and isinstance(vals["config_json"], dict):
        vals["config_json"] = json.dumps(vals["config_json"])
    if not vals:
        return

    job = db.get(ScheduledJob, job_id)
    if not job:
        return
    for k, v in vals.items():
        setattr(job, k, v)
    job.updated_at = _now()
    db.commit()


# ── Bot runs ──────────────────────────────────────────────────────────────────


def create_bot_run(db: Session, **kwargs) -> int:
    """Insert a bot run record, return its id."""
    run = BotRun(
        job_type=kwargs.get("job_type", ""),
        device=kwargs.get("device"),
        config_json=kwargs.get("config_json"),
        started_at=kwargs.get("started_at"),
        finished_at=kwargs.get("finished_at"),
        status=kwargs.get("status"),
        exit_code=kwargs.get("exit_code"),
        dms_sent=kwargs.get("dms_sent"),
        dms_failed=kwargs.get("dms_failed"),
        video_name=kwargs.get("video_name"),
        post_action=kwargs.get("post_action"),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run.id


# ── Accounts ──────────────────────────────────────────────────────────────────


def get_default_account(db: Session) -> str | None:
    """Return the handle of the default TikTok account, or None."""
    acct = db.query(TikTokAccount.handle).filter(TikTokAccount.is_default == 1).first()
    return acct[0] if acct else None
