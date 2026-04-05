"""Bot routes: queue management, crawl runs, bot history."""

import json
import logging
import subprocess
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Body, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from gitd.config import settings
from gitd.models.base import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["bot"])

# ── Bot / queue state ────────────────────────────────────────────────────────
_bot_proc = None
_bot_log = Path("/tmp/tiktok_bot.log")
_BOT_DEVICE = settings.default_device

_queue: list = []
_job_counter = 0
_queue_lock = threading.Lock()

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent


_PREMIUM_JOB_TYPES = {"outreach", "crawl", "inbox_scan", "perf_scan", "engage", "content_gen", "content_plan"}


def _build_cmd(job: dict, device: str | None = None) -> list:
    job_type = job.get("job_type", "")
    dev = device or job.get("device") or _BOT_DEVICE

    if job_type in _PREMIUM_JOB_TYPES:
        raise ValueError(f"Job type '{job_type}' requires the ghost_premium plugin.")

    if job_type == "post":
        script = _SCRIPTS_DIR / "bots" / "tiktok" / "upload.py"
        video = job.get("video", "")
        cmd = ["python3", "-u", str(script), video, "--action", job.get("action", "draft"), "--device", dev]
        if job.get("hashtags", "").strip():
            cmd += ["--hashtags", job["hashtags"].strip()]
        if job.get("caption", "").strip():
            cmd += ["--caption", job["caption"].strip()]
        if job.get("inject_tts") and job.get("caption", "").strip():
            cmd += ["--inject-tts"]
        if job.get("post_id"):
            cmd += ["--post-id", str(int(job["post_id"]))]
        if job.get("account"):
            cmd += ["--account", job["account"]]
        return cmd
    elif job_type == "publish_draft":
        script = _SCRIPTS_DIR / "bots" / "tiktok" / "upload.py"
        cmd = ["python3", "-u", str(script), "--device", dev]
        if job.get("draft_tag"):
            cmd += ["--draft-tag", job["draft_tag"]]
        else:
            grid_index = int(job.get("grid_index", 0))
            cmd += ["--publish-draft", str(grid_index)]
        if job.get("post_id"):
            cmd += ["--post-id", str(int(job["post_id"]))]
        if job.get("account"):
            cmd += ["--account", job["account"]]
        return cmd

    raise ValueError(f"Unknown job type: '{job_type}'")


def _launch_job(job: dict):
    """Start a job subprocess. Must be called with _queue_lock held."""
    global _bot_proc
    job["status"] = "running"
    job["started_at"] = datetime.now().isoformat()
    is_first = sum(1 for j in _queue if j.get("status") in ("done", "stopped")) == 0
    mode = "w" if is_first else "a"
    log_f = open(_bot_log, mode, buffering=1)
    if not is_first:
        jt = job.get("job_type", "")
        label = f"{jt} * {Path(job.get('video', '')).name or ''} * {job.get('action', '')}"
        log_f.write(f"\n{'=' * 48}\n[queue] Job #{job['id']}: {label}\n{'=' * 48}\n")
        log_f.flush()
    _bot_proc = subprocess.Popen(
        _build_cmd(job),
        stdout=log_f,
        stderr=subprocess.STDOUT,
        cwd=str(_SCRIPTS_DIR),
    )
    job["pid"] = _bot_proc.pid


def _queue_watcher():
    """Background thread: mark completed jobs done, auto-start next pending."""
    global _bot_proc
    while True:
        time.sleep(2)
        with _queue_lock:
            if _bot_proc is None or _bot_proc.poll() is None:
                continue
            rc = _bot_proc.returncode
            for j in _queue:
                if j.get("status") == "running":
                    j["status"] = "stopped" if rc not in (0, None) else "done"
                    j["returncode"] = rc
                    try:
                        from gitd.models import SessionLocal
                        from gitd.services.db_helpers import create_bot_run

                        session = SessionLocal()
                        try:
                            skip_keys = {"id", "status", "pid", "returncode", "started_at", "run_id"}
                            cfg = {k: v for k, v in j.items() if k not in skip_keys}
                            create_bot_run(
                                session,
                                job_type=j["job_type"],
                                device=j.get("device"),
                                config_json=json.dumps(cfg),
                                started_at=j.get("started_at"),
                                finished_at=datetime.now().isoformat(),
                                status=j["status"],
                                exit_code=rc,
                                video_name=Path(j.get("video", "")).name if j.get("video") else None,
                                post_action=j.get("action"),
                            )
                        finally:
                            session.close()
                    except Exception as e:
                        logger.error("bot_runs insert error: %s", e)
            nxt = next((j for j in _queue if j["status"] == "pending"), None)
            if nxt:
                _launch_job(nxt)


threading.Thread(target=_queue_watcher, daemon=True).start()


# ── Bot status / queue routes ────────────────────────────────────────────────


@router.get("/api/bot/status", summary="Get Bot Status")
def bot_status():
    """Check if the bot is running and how many jobs are pending."""
    with _queue_lock:
        running = _bot_proc is not None and _bot_proc.poll() is None
        pending = sum(1 for j in _queue if j["status"] == "pending")
    return {"running": running, "pending": pending}


@router.get("/api/bot/queue", summary="Get Bot Job Queue")
def bot_queue_get():
    """Return the current list of queued bot jobs."""
    with _queue_lock:
        return {"jobs": list(_queue)}


@router.post("/api/bot/queue/add", summary="Add Job To Bot Queue")
def bot_queue_add(data: dict = Body({})):
    """Add a crawl, outreach, post, or other job to the bot queue."""
    global _job_counter
    job_type = data.get("job_type", "crawl")
    with _queue_lock:
        _job_counter += 1
        job: dict = {
            "id": _job_counter,
            "run_id": uuid.uuid4().hex[:8],
            "status": "pending",
            "job_type": job_type,
            "device": data.get("device") or _BOT_DEVICE,
            "account": data.get("account") or None,
        }
        if job_type in _PREMIUM_JOB_TYPES:
            return {"ok": False, "error": f"Job type '{job_type}' requires the ghost_premium plugin."}
        if job_type == "post":
            job.update(
                {
                    "video": data.get("video", ""),
                    "hashtags": data.get("hashtags", ""),
                    "caption": data.get("caption", ""),
                    "inject_tts": data.get("inject_tts", False),
                    "action": data.get("action", "draft"),
                    "post_id": data.get("post_id"),
                }
            )
        elif job_type == "publish_draft":
            job.update(
                {
                    "grid_index": data.get("grid_index", 0),
                    "draft_tag": data.get("draft_tag"),
                    "post_id": data.get("post_id"),
                }
            )
        else:
            return {"ok": False, "error": f"Unknown job type: '{job_type}'"}
        _queue.append(job)
        running = _bot_proc is not None and _bot_proc.poll() is None
        if not running:
            _launch_job(job)
    return {"ok": True, "job": job}


@router.delete("/api/bot/queue/{job_id}", summary="Remove Job From Queue")
def bot_queue_remove(job_id: int):
    """Remove a pending job from the bot queue."""
    with _queue_lock:
        job = next((j for j in _queue if j["id"] == job_id), None)
        if not job:
            return {"ok": False, "error": "Not found"}
        if job.get("status") == "running":
            return {"ok": False, "error": "Stop the running job first"}
        _queue.remove(job)
    return {"ok": True}


@router.post("/api/bot/queue/clear", summary="Clear Bot Job Queue")
def bot_queue_clear():
    """Remove all non-running jobs from the queue."""
    with _queue_lock:
        _queue[:] = [j for j in _queue if j.get("status") == "running"]
    return {"ok": True}


@router.post("/api/bot/stop", summary="Stop Running Bot")
def bot_stop():
    """Terminate the currently running bot process."""
    global _bot_proc
    with _queue_lock:
        if not _bot_proc or _bot_proc.poll() is not None:
            return {"ok": False, "error": "Not running"}
        _bot_proc.terminate()
        try:
            _bot_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _bot_proc.kill()
        for j in _queue:
            if j.get("status") == "running":
                j["status"] = "stopped"
    return {"ok": True}


@router.get("/api/bot/logs", summary="Get Bot Logs")
def bot_logs(since: int = 0):
    """Return bot process log lines since a given offset."""
    if not _bot_log.exists():
        return {"lines": [], "total": 0, "running": False, "jobs": []}
    with open(_bot_log, "r", errors="replace") as f:
        all_lines = f.readlines()
    with _queue_lock:
        running = _bot_proc is not None and _bot_proc.poll() is None
        rc = _bot_proc.returncode if _bot_proc and not running else None
        jobs = list(_queue)
    return {
        "lines": [line.rstrip("\n") for line in all_lines[since:]],
        "total": len(all_lines),
        "running": running,
        "returncode": rc,
        "jobs": jobs,
    }


# ── Crawl runs + bot history ────────────────────────────────────────────────


@router.get("/api/bot/history", summary="Get Bot Run History")
def bot_history(db: Session = Depends(get_db)):
    """Return bot run history."""
    try:
        rows = db.execute(text("SELECT * FROM bot_runs ORDER BY started_at DESC LIMIT 100")).mappings().all()
        return [dict(r) for r in rows]
    except Exception:
        return []
