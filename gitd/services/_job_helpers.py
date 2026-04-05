"""
Shared helpers used by job_engine and content_pipeline.

Contains: timestamp helper, log-parsing utilities, DB helpers for
finishing / archiving / enqueuing jobs, and shared path constants.
"""

import logging
import re
from datetime import datetime
from pathlib import Path

from sqlalchemy import text

from gitd.config import settings  # noqa: F401
from gitd.models.base import SessionLocal  # noqa: F401

logger = logging.getLogger(__name__)

# ── Shared constants ────────────────────────────────────────────────────────
_SCRIPT_DIR = Path(__file__).resolve().parent.parent  # gitd/
_VERTICAL_DIR = _SCRIPT_DIR.parent / "data" / "vertical_videos"
_BOT_DEVICE = settings.default_device


def _now() -> str:
    """Local-time timestamp (consistent with schedule times)."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ── Log parsing helpers ────────────────────────────────────────────────────


def _parse_live_stats(job: dict) -> str:
    """Parse a running job's log file for live progress stats."""
    log_path = job.get("log_file") or f"/tmp/sched_job_{job['id']}.log"
    try:
        with open(log_path, "r", errors="replace") as f:
            lines = f.readlines()
    except (FileNotFoundError, OSError):
        return ""
    jt = job.get("job_type", "")
    if jt == "crawl":
        new_count = 0
        current_tag = ""
        tags_done = 0
        tags_total = 0
        for line in lines:
            if "Saved:" in line or "Saved " in line:
                new_count += 1
            if "[runner]" in line and "— starting" in line:
                m = re.search(r"\d+/(\d+)\s+(#\S+)", line)
                if m:
                    tags_total = int(m.group(1))
                    current_tag = m.group(2)
            if "[runner]" in line and "— done:" in line:
                tags_done += 1
        parts = []
        if tags_total > 0:
            parts.append(f"tag {tags_done + 1}/{tags_total}")
        if current_tag:
            parts.append(current_tag)
        parts.append(f"{new_count} new")
        return " \u00b7 ".join(parts)
    elif jt == "outreach":
        sent = sum(1 for ln in lines if "[done]" in ln and "sent" in ln)
        failed = sum(1 for ln in lines if "[error]" in ln)
        current = ""
        for line in reversed(lines):
            if "[pass " in line:
                m = re.search(r"\[pass (\d+/\d+)\]", line)
                if m:
                    current = m.group(1)
                break
        parts = []
        if current:
            parts.append(current)
        if sent:
            parts.append(f"{sent} sent")
        if failed:
            parts.append(f"{failed} err")
        return " \u00b7 ".join(parts) if parts else ""
    return ""


def _parse_partial_crawl(lines: list[str]) -> str:
    """Parse partial crawl progress when job didn't finish (timeout/killed)."""
    total_tags = 0
    done_tags = 0
    total_new = 0
    total_known = 0
    for line in lines:
        m = re.search(r"\[runner\] Label:.*?\|\s*(\d+)\s+hashtag", line)
        if m:
            total_tags = int(m.group(1))
        m = re.search(
            r"\[runner\]\s+(\d+)/(\d+)\s+.*?done:\s*(\d+)\s+new,\s*(\d+)\s+known", line
        )
        if m:
            done_tags = int(m.group(1))
            total_tags = total_tags or int(m.group(2))
            total_new += int(m.group(3))
            total_known += int(m.group(4))
    if done_tags or total_new:
        return f"{done_tags}/{total_tags} tags \u00b7 {total_new} new \u00b7 {total_known} known"
    return ""


def _parse_job_summary(
    jid: int, entry: dict | None = None, log_path: str | None = None
) -> str:
    """Parse [done] summary from a job's log file."""
    log_path = log_path or (entry or {}).get("log_path") or f"/tmp/sched_job_{jid}.log"
    try:
        with open(log_path, "r", errors="replace") as lf:
            all_lines = lf.readlines()
    except (FileNotFoundError, OSError):
        return ""
    summary = ""
    sent_count = 0
    for line in all_lines:
        if "[done]" not in line:
            continue
        txt = line.strip().split("[done]")[-1].strip()
        if "sent," in txt and "failed" in txt:
            summary = txt
            break
        if "message sent" in txt:
            sent_count += 1
    if not summary and sent_count > 0:
        summary = f"{sent_count} sent"
    if not summary:
        for line in reversed(all_lines[-10:]):
            if "[done]" in line:
                summary = line.strip().split("[done]")[-1].strip()
                break
    if not summary:
        summary = _parse_partial_crawl(all_lines)
    return summary


# ── DB helpers (SQLAlchemy text()) ─────────────────────────────────────────


def finish_job(db, job_id: int, status: str,
               exit_code: int | None = None, error_msg: str | None = None):
    """Mark a job_queue row as finished."""
    db.execute(
        text(
            "UPDATE job_queue SET status = :status, finished_at = :finished, "
            "exit_code = :exit_code, error_msg = :error_msg WHERE id = :id"
        ),
        {
            "status": status,
            "finished": _now(),
            "exit_code": exit_code,
            "error_msg": error_msg,
            "id": job_id,
        },
    )
    db.commit()


def archive_to_runs(db, job_id: int):
    """Move a job_queue row into job_runs and delete it from the queue."""
    row = db.execute(
        text("SELECT * FROM job_queue WHERE id = :id"), {"id": job_id}
    ).mappings().first()
    if not row:
        return
    r = dict(row)
    dur = None
    if r.get("started_at") and r.get("finished_at"):
        try:
            s = datetime.fromisoformat(r["started_at"])
            e = datetime.fromisoformat(r["finished_at"])
            dur = int((e - s).total_seconds())
        except Exception:
            pass
    db.execute(
        text(
            "INSERT OR REPLACE INTO job_runs "
            "(id, scheduled_job_id, phone_serial, job_type, priority, "
            "config_json, status, enqueued_at, started_at, finished_at, "
            "duration_s, exit_code, error_msg, log_file, trigger) "
            "VALUES (:id, :scheduled_job_id, :phone_serial, :job_type, :priority, "
            ":config_json, :status, :enqueued_at, :started_at, :finished_at, "
            ":duration_s, :exit_code, :error_msg, :log_file, :trigger)"
        ),
        {
            "id": job_id,
            "scheduled_job_id": r.get("scheduled_job_id"),
            "phone_serial": r.get("phone_serial"),
            "job_type": r["job_type"],
            "priority": r.get("priority"),
            "config_json": r.get("config_json"),
            "status": r.get("status"),
            "enqueued_at": r.get("enqueued_at"),
            "started_at": r.get("started_at"),
            "finished_at": r.get("finished_at"),
            "duration_s": dur,
            "exit_code": r.get("exit_code"),
            "error_msg": r.get("error_msg"),
            "log_file": r.get("log_file"),
            "trigger": r.get("trigger", "scheduled"),
        },
    )
    db.execute(text("DELETE FROM job_queue WHERE id = :id"), {"id": job_id})
    db.commit()


def _enqueue_job(db, **kwargs) -> int:
    """Insert a pending job into job_queue (text-based, for scheduler thread)."""
    from gitd.services.db_helpers import enqueue_job
    return enqueue_job(db, **kwargs)
