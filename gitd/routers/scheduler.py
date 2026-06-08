"""Scheduler routes: CRUD for scheduled jobs, queue, history, timeline."""

import json
import os
import re
import signal
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from gitd.models.base import get_db

router = APIRouter(tags=["scheduler"])


def _sched_next_run(sched: dict, db: Session) -> str | None:
    """Compute the next scheduled run time as HH:MM string."""
    if sched["schedule_type"] == "daily":
        try:
            times = json.loads(sched.get("daily_times") or "[]")
        except Exception:
            return None
        now = datetime.now()
        now_time = now.strftime("%H:%M")
        today_str = now.strftime("%Y-%m-%d")
        for t in sorted(times):
            if t > now_time:
                already = db.execute(
                    text("SELECT COUNT(*) FROM job_runs WHERE scheduled_job_id = :sid AND started_at >= :ts"),
                    {"sid": sched["id"], "ts": f"{today_str} {t}"},
                ).scalar()
                if already == 0:
                    return t
        return (sorted(times)[0] + " +1d") if times else None
    elif sched["schedule_type"] == "interval":
        interval = sched.get("interval_minutes") or 60
        last = db.execute(
            text("SELECT MAX(finished_at) FROM job_runs WHERE scheduled_job_id = :sid"),
            {"sid": sched["id"]},
        ).scalar()
        if not last:
            return "now"
        try:
            nxt = datetime.fromisoformat(last) + timedelta(minutes=interval)
            return nxt.strftime("%H:%M")
        except Exception:
            return "?"
    return None


def _parse_live_stats(job: dict) -> str:
    """Parse a running job's log file for live progress stats."""
    log_path = job.get("log_file") or f"/tmp/sched_job_{job['id']}.log"
    try:
        with open(log_path, "r", errors="replace") as f:
            lines = f.readlines()
    except Exception:
        return ""
    jt = job.get("job_type", "")
    if jt == "crawl":
        new_count = sum(1 for line in lines if "Saved:" in line or "Saved " in line)
        current_tag = ""
        tags_done = 0
        tags_total = 0
        for line in lines:
            if "[runner]" in line and "starting" in line:
                m = re.search(r"\d+/(\d+)\s+(#\S+)", line)
                if m:
                    tags_total = int(m.group(1))
                    current_tag = m.group(2)
            if "[runner]" in line and "done:" in line:
                tags_done += 1
        parts = []
        if tags_total > 0:
            parts.append(f"tag {tags_done + 1}/{tags_total}")
        if current_tag:
            parts.append(current_tag)
        parts.append(f"{new_count} new")
        return " | ".join(parts)
    return ""


def _coerce_config(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _scheduler_platform_error(record: dict) -> dict | None:
    phone = record.get("phone_serial")
    job_type = record.get("job_type", "")
    if not phone or not job_type:
        return None

    config = _coerce_config(record.get("config_json"))
    from gitd.services.job_engine import _job_platform_preflight, _skill_platform_preflight
    from gitd.skills.platforms import platform_for_device_ref

    message = _job_platform_preflight(phone, job_type)
    if not message:
        message = _skill_platform_preflight(phone, job_type, config)
    if not message:
        return None

    detail = {
        "error": "unsupported_platform",
        "platform": platform_for_device_ref(phone),
        "job_type": job_type,
        "message": message,
    }
    skill = config.get("skill")
    if skill:
        detail["skill"] = skill
    return detail


def _raise_scheduler_platform_error(record: dict):
    detail = _scheduler_platform_error(record)
    if detail:
        raise HTTPException(status_code=400, detail=detail)


# ── Schedules CRUD ──────────────────────────────────────────────────────────


@router.get("/api/schedules", summary="List Scheduled Jobs")
def schedules_list(db: Session = Depends(get_db)):
    """Return all scheduled jobs with their last run and next run time."""
    scheds = db.execute(text("SELECT * FROM scheduled_jobs ORDER BY id")).mappings().all()
    result = []
    for s in scheds:
        s = dict(s)
        last_run = (
            db.execute(
                text("SELECT * FROM job_runs WHERE scheduled_job_id = :sid ORDER BY created_at DESC LIMIT 1"),
                {"sid": s["id"]},
            )
            .mappings()
            .first()
        )
        s["last_run"] = dict(last_run) if last_run else None
        s["next_run"] = _sched_next_run(s, db) if s.get("is_enabled") else None
        result.append(s)
    return result


@router.post("/api/schedules", summary="Create Scheduled Job")
def schedules_create(data: dict = Body({}), db: Session = Depends(get_db)):
    """Create a new scheduled job with name, type, and schedule config."""
    required = ["name", "job_type", "schedule_type"]
    for r in required:
        if not data.get(r):
            raise HTTPException(status_code=400, detail=f"{r} required")
    _raise_scheduler_platform_error(data)
    from gitd.services.db_helpers import create_scheduled_job

    sid = create_scheduled_job(db, **data)
    return {"ok": True, "id": sid}


@router.put("/api/schedules/{sid}", summary="Update Scheduled Job")
def schedules_update(sid: int, data: dict = Body({}), db: Session = Depends(get_db)):
    """Update an existing scheduled job's configuration."""
    from gitd.services.db_helpers import update_scheduled_job

    existing = (
        db.execute(text("SELECT * FROM scheduled_jobs WHERE id = :sid"), {"sid": sid})
        .mappings()
        .first()
    )
    if not existing:
        raise HTTPException(status_code=404, detail="not found")
    merged = dict(existing)
    merged.update(data)
    _raise_scheduler_platform_error(merged)

    update_scheduled_job(db, sid, **data)
    return {"ok": True}


@router.delete("/api/schedules/{sid}", summary="Delete Scheduled Job")
def schedules_delete(sid: int, db: Session = Depends(get_db)):
    """Delete a scheduled job by ID."""
    db.execute(text("DELETE FROM scheduled_jobs WHERE id = :sid"), {"sid": sid})
    db.commit()
    return {"ok": True}


@router.post("/api/schedules/{sid}/toggle", summary="Toggle Scheduled Job On/Off")
def schedules_toggle(sid: int, db: Session = Depends(get_db)):
    """Toggle a scheduled job between enabled and disabled."""
    row = db.execute(
        text("SELECT is_enabled FROM scheduled_jobs WHERE id = :sid"),
        {"sid": sid},
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="not found")
    new_val = 0 if row[0] else 1
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.execute(
        text("UPDATE scheduled_jobs SET is_enabled = :val, updated_at = :now WHERE id = :sid"),
        {"val": new_val, "now": now, "sid": sid},
    )
    db.commit()
    return {"ok": True, "is_enabled": new_val}


@router.post("/api/schedules/{sid}/run-now", summary="Run Scheduled Job Now")
def schedules_run_now(sid: int, db: Session = Depends(get_db)):
    """Immediately enqueue a scheduled job for execution."""
    sched = (
        db.execute(
            text("SELECT * FROM scheduled_jobs WHERE id = :sid"),
            {"sid": sid},
        )
        .mappings()
        .first()
    )
    if not sched:
        raise HTTPException(status_code=404, detail="not found")
    sched = dict(sched)
    _raise_scheduler_platform_error(sched)
    from gitd.services.db_helpers import enqueue_job

    qid = enqueue_job(
        db,
        scheduled_job_id=sched["id"],
        phone_serial=sched.get("phone_serial"),
        job_type=sched["job_type"],
        priority=sched.get("priority", 2),
        config_json=sched.get("config_json", "{}"),
        max_duration_s=sched.get("max_duration_s", 3600),
        trigger="manual",
    )
    return {"ok": True, "queue_id": qid}


# ── Scheduler status & queue ────────────────────────────────────────────────


@router.get("/api/scheduler/status", summary="Get Scheduler Status Per Phone")
def scheduler_status(db: Session = Depends(get_db)):
    """Return running/pending job status grouped by phone serial."""
    phones: dict = {}
    db_running = db.execute(text("SELECT * FROM job_queue WHERE status = 'running'")).mappings().all()
    for row in db_running:
        row = dict(row)
        key = row.get("phone_serial") or "__none__"
        phones[key] = {"running": True, "job": row, "pid": row.get("pid")}
    pending = db.execute(
        text("SELECT phone_serial, COUNT(*) as cnt FROM job_queue WHERE status='pending' GROUP BY phone_serial")
    ).fetchall()
    for row in pending:
        key = row[0] or "__none__"
        if key not in phones:
            phones[key] = {"running": False, "job": None, "pid": None}
        phones[key]["pending"] = row[1]
    return phones


@router.get("/api/scheduler/queue", summary="Get Scheduler Job Queue")
def scheduler_queue(db: Session = Depends(get_db)):
    """Return the scheduler job queue with live stats for running jobs."""
    rows = db.execute(text("SELECT * FROM job_queue ORDER BY enqueued_at DESC LIMIT 200")).mappings().all()
    result = []
    for r in rows:
        r = dict(r)
        if r.get("scheduled_job_id"):
            s = db.execute(
                text("SELECT name FROM scheduled_jobs WHERE id = :sid"),
                {"sid": r["scheduled_job_id"]},
            ).first()
            r["schedule_name"] = s[0] if s else None
        if r.get("status") == "running":
            r["live_stats"] = _parse_live_stats(r)
        result.append(r)
    return result


@router.get("/api/scheduler/queue/{qid}/logs", summary="Get Queued Job Logs")
def scheduler_queue_logs(qid: int, since: int = 0, db: Session = Depends(get_db)):
    """Return log lines for a queued job since a given offset."""
    row = db.execute(
        text("SELECT log_file FROM job_queue WHERE id = :qid"),
        {"qid": qid},
    ).first()
    log_path = row[0] if row and row[0] else None
    if not log_path:
        log_path = f"/tmp/sched_job_{qid}.log"
    p = Path(log_path)
    if not p.exists():
        return {"lines": [], "total": 0}
    with open(p, "r", errors="replace") as f:
        all_lines = f.readlines()
    return {
        "lines": [line.rstrip("\n") for line in all_lines[since:]],
        "total": len(all_lines),
    }


@router.post("/api/scheduler/queue/{qid}/kill", summary="Kill Queued Job")
def scheduler_queue_kill(qid: int, db: Session = Depends(get_db)):
    """Kill a running or cancel a pending queued job."""
    row = (
        db.execute(
            text("SELECT * FROM job_queue WHERE id = :qid"),
            {"qid": qid},
        )
        .mappings()
        .first()
    )
    if not row:
        return {"ok": False, "error": "Job not found or not killable"}
    row = dict(row)
    if row.get("status") == "running" and row.get("pid"):
        try:
            os.kill(row["pid"], signal.SIGTERM)
        except ProcessLookupError:
            pass
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db.execute(
            text("UPDATE job_queue SET status='killed', error_msg='Killed by user', finished_at=:now WHERE id=:qid"),
            {"now": now, "qid": qid},
        )
        db.commit()
        return {"ok": True}
    elif row.get("status") == "pending":
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db.execute(
            text("UPDATE job_queue SET status='killed', error_msg='Cancelled by user', finished_at=:now WHERE id=:qid"),
            {"now": now, "qid": qid},
        )
        db.commit()
        return {"ok": True}
    return {"ok": False, "error": "Job not found or not killable"}


@router.post("/api/scheduler/runs/{run_id}/restart", summary="Restart Scheduler Run")
def scheduler_run_restart(run_id: int, db: Session = Depends(get_db)):
    """Kill (if active) and re-enqueue a job."""
    row = (
        db.execute(
            text("SELECT * FROM job_runs WHERE id = :rid"),
            {"rid": run_id},
        )
        .mappings()
        .first()
    )
    if not row:
        row = (
            db.execute(
                text("SELECT * FROM job_queue WHERE id = :rid"),
                {"rid": run_id},
            )
            .mappings()
            .first()
        )
    if not row:
        raise HTTPException(status_code=404, detail="Run not found")
    row = dict(row)
    _raise_scheduler_platform_error(row)
    from gitd.services.db_helpers import enqueue_job

    new_id = enqueue_job(
        db,
        job_type=row["job_type"],
        phone_serial=row.get("phone_serial"),
        config_json=row.get("config_json"),
        priority=row.get("priority", 2),
        scheduled_job_id=row.get("scheduled_job_id"),
        trigger="manual",
    )
    return {"ok": True, "new_job_id": new_id}


# ── History & timeline ──────────────────────────────────────────────────────


@router.get("/api/scheduler/history", summary="Get Scheduler Run History")
def scheduler_history(db: Session = Depends(get_db)):
    """Return recent job run history with schedule names."""
    rows = db.execute(text("SELECT * FROM job_runs ORDER BY created_at DESC LIMIT 100")).mappings().all()
    result = []
    for r in rows:
        r = dict(r)
        if r.get("scheduled_job_id"):
            s = db.execute(
                text("SELECT name FROM scheduled_jobs WHERE id = :sid"),
                {"sid": r["scheduled_job_id"]},
            ).first()
            r["schedule_name"] = s[0] if s else None
        result.append(r)
    return result


@router.get("/api/scheduler/history/{run_id}/logs", summary="Get Run History Logs")
def scheduler_history_logs(run_id: int, since: int = 0, db: Session = Depends(get_db)):
    """Return log lines for a historical job run."""
    row = db.execute(
        text("SELECT log_file FROM job_runs WHERE id = :rid"),
        {"rid": run_id},
    ).first()
    log_path = row[0] if row and row[0] else None
    if not log_path or not Path(log_path).exists():
        return {"lines": [], "total": 0}
    with open(log_path, "r", errors="replace") as f:
        all_lines = f.readlines()
    return {
        "lines": [line.rstrip("\n") for line in all_lines[since:]],
        "total": len(all_lines),
    }


@router.get("/api/scheduler/history/{run_id}/result", summary="Get Run Structured Result")
def scheduler_history_result(run_id: int, db: Session = Depends(get_db)):
    """Return the newest structured Data JSON emitted by a completed scheduler run."""
    from gitd.services._job_helpers import _parse_job_result_data, _summarize_job_result_data

    row = (
        db.execute(
            text("SELECT id, log_file FROM job_runs WHERE id = :rid"),
            {"rid": run_id},
        )
        .mappings()
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Run not found")
    log_path = row.get("log_file")
    if not log_path or not Path(log_path).exists():
        return {"ok": False, "result": None, "summary": "", "error": "log file not found"}
    result = _parse_job_result_data(run_id, log_path=log_path)
    return {
        "ok": result is not None,
        "result": result,
        "summary": _summarize_job_result_data(result),
        "error": "" if result is not None else "structured result not found",
    }


@router.get("/api/scheduler/timeline", summary="Get Scheduler Timeline")
def scheduler_timeline(db: Session = Depends(get_db)):
    """Return 24h timeline data — past runs + future scheduled times per phone."""
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")

    runs = (
        db.execute(
            text("SELECT * FROM job_runs WHERE started_at >= :today ORDER BY started_at"),
            {"today": today_str},
        )
        .mappings()
        .all()
    )
    past = []
    for r in runs:
        r = dict(r)
        if r.get("scheduled_job_id"):
            s = db.execute(
                text("SELECT name, phone_serial FROM scheduled_jobs WHERE id = :sid"),
                {"sid": r["scheduled_job_id"]},
            ).first()
            if s:
                r["schedule_name"] = s[0]
        past.append(r)

    future = []
    scheds = db.execute(text("SELECT * FROM scheduled_jobs WHERE is_enabled = 1")).mappings().all()
    for s in scheds:
        s = dict(s)
        if s["schedule_type"] == "daily":
            try:
                times = json.loads(s.get("daily_times") or "[]")
            except Exception:
                continue
            now_time = now.strftime("%H:%M")
            for t in times:
                future.append(
                    {
                        "scheduled_job_id": s["id"],
                        "schedule_name": s["name"],
                        "phone_serial": s.get("phone_serial"),
                        "job_type": s["job_type"],
                        "time": t,
                        "is_past": t <= now_time,
                    }
                )

    # Content plan items (premium feature — table may not exist)
    content_plan_items = []
    try:
        cp_rows = (
            db.execute(
                text(
                    "SELECT id, scheduled_date, scheduled_time, style_id, phone_serial, status, caption, source_account "
                    "FROM content_plan WHERE scheduled_date >= :today AND status NOT IN ('posted','failed','skipped') "
                    "ORDER BY scheduled_date, scheduled_time"
                ),
                {"today": today_str},
            )
            .mappings()
            .all()
        )
        for cp in cp_rows:
            cp = dict(cp)
            content_plan_items.append(
                {
                    "plan_id": cp["id"],
                    "schedule_name": f"CP: {cp.get('style_id', '?')}",
                    "phone_serial": cp.get("phone_serial"),
                    "job_type": "content_plan",
                    "time": cp.get("scheduled_time"),
                    "date": cp.get("scheduled_date"),
                    "status": cp.get("status"),
                    "caption": (cp.get("caption") or "")[:50],
                    "account": cp.get("source_account") or "",
                }
            )
    except Exception:
        pass

    return {"past": past, "future": future, "content_plan": content_plan_items}


# ── Account health endpoints ────────────────────────────────────────────────

@router.get("/api/scheduler/account-health", summary="Account Health for All Devices")
def account_health_all():
    """Probe every connected device for its TikTok account state."""
    from gitd.services.account_health import all_devices_health
    return all_devices_health()


@router.get("/api/scheduler/account-health/{device}", summary="Account Health for One Device")
def account_health_one(device: str, fresh: bool = False):
    """Probe a single device. Pass ?fresh=true to bypass the 60s cache."""
    from gitd.services.account_health import device_account_health
    return device_account_health(device, fresh=fresh)


@router.post("/api/scheduler/account-switch/{device}", summary="Switch Active TikTok Account")
def account_switch(device: str, data: dict = Body(...)):
    """Switch the active TikTok account on `device` to body.handle."""
    handle = (data.get("handle") or "").strip()
    if not handle:
        raise HTTPException(status_code=400, detail="handle required")
    from gitd.services.account_health import switch_active_account
    return switch_active_account(device, handle)


@router.post("/api/scheduler/account-sync/{device}", summary="Sync DB tiktok_accounts with Device State")
def account_sync(device: str):
    """Update tiktok_accounts DB rows to match what's actually logged in on `device`."""
    from gitd.services.account_health import sync_tiktok_accounts_table
    return sync_tiktok_accounts_table(device)
