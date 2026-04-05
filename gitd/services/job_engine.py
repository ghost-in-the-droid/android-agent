"""
Job engine — subprocess management for scheduled jobs.

Owns _phone_procs (running-process registry) and all functions that
build, launch, kill, and schedule subprocess-based jobs.
"""

import json
import logging
import os
import subprocess
from datetime import datetime, timedelta

from sqlalchemy import text

from gitd.services._job_helpers import (
    _BOT_DEVICE,
    _SCRIPT_DIR,
    _now,
    _parse_job_summary,
    archive_to_runs,
    finish_job,
)

logger = logging.getLogger(__name__)

# ── Module-level state ──────────────────────────────────────────────────────
_phone_procs: dict = {}  # phone_serial|None -> {'proc': Popen, 'job_id': int, 'log_f': file, 'log_path': str}
_PREEMPT_GRACE_S = 90


# ── Manual bot process checks ──────────────────────────────────────────────


def _is_phone_busy_manual(phone: str | None) -> bool:
    """Check if a manual bot process is using this phone.

    In the FastAPI server, manual bot processes are not tracked here,
    so this always returns False.  If manual bot tracking is added later,
    update this function.
    """
    return False


# ── Command builder ─────────────────────────────────────────────────────────


def _build_scheduled_cmd(job_type: str, config: dict, phone: str | None) -> list | None:
    """Build the subprocess command for a scheduled job type."""
    script_dir = _SCRIPT_DIR
    if job_type == "crawl":
        tab = config.get("tab", "top")
        passes = config.get("passes", 5)
        label = config.get("label")
        if label:
            n_hashtags = config.get("n_hashtags", 1)
            cmd = [
                "python3", "-u",
                str(script_dir / "bots" / "tiktok" / "crawl_runner.py"),
                "--label", str(label),
                "--n-hashtags", str(n_hashtags),
                "--tab", str(tab),
                "--passes", str(passes),
            ]
            if phone:
                cmd += ["--device", phone]
            limit = config.get("limit")
            if limit:
                cmd += ["--limit", str(int(limit))]
            if config.get("sort_by"):
                cmd += ["--sort-by", config["sort_by"]]
            if config.get("date_filter"):
                cmd += ["--date-filter", config["date_filter"]]
            if config.get("no_enrich"):
                cmd += ["--no-enrich"]
            if config.get("labels"):
                cmd += ["--labels", config["labels"]]
            if config.get("account"):
                cmd += ["--account", config["account"]]
            return cmd
        else:
            query = config.get("query", "#cats")
            cmd = [
                "python3", "-u",
                str(script_dir / "bots" / "tiktok" / "scraper.py"),
                query,
                "--tab", str(tab),
                "--passes", str(passes),
            ]
            if phone:
                cmd += ["--device", phone]
            limit = config.get("limit")
            if limit:
                cmd += ["--limit", str(int(limit))]
            if config.get("account"):
                cmd += ["--account", config["account"]]
            return cmd
    elif job_type == "outreach":
        sid = config.get("strategy_id", 1)
        delay = config.get("delay", 60)
        limit = config.get("limit", 20)
        cmd = [
            "python3", "-u",
            str(script_dir / "bots" / "tiktok" / "outreach.py"),
            "--strategy-id", str(sid),
            "--delay", str(delay),
            "--limit", str(limit),
        ]
        if phone:
            cmd += ["--device", phone]
        if config.get("min_followers"):
            cmd += ["--min-followers", str(int(config["min_followers"]))]
        if config.get("max_followers"):
            cmd += ["--max-followers", str(int(config["max_followers"]))]
        if config.get("query"):
            cmd += ["--query", config["query"]]
        if config.get("labels"):
            cmd += ["--labels", config["labels"]]
        if config.get("account"):
            cmd += ["--account", config["account"]]
        return cmd
    elif job_type == "post":
        video = config.get("video", "")
        action = config.get("action", "draft")
        cmd = ["python3", "-u", str(script_dir / "bots" / "tiktok" / "upload.py")]
        if video:
            cmd.append(video)
        else:
            cmd.append("--auto")
        cmd += ["--action", action]
        if phone:
            cmd += ["--device", phone]
        if config.get("hashtags"):
            cmd += ["--hashtags", config["hashtags"]]
        if config.get("caption"):
            cmd += ["--caption", config["caption"]]
        if config.get("post_id"):
            cmd += ["--post-id", str(int(config["post_id"]))]
        if config.get("inject_tts") and config.get("caption", "").strip():
            cmd += ["--inject-tts"]
        if config.get("account"):
            cmd += ["--account", config["account"]]
        return cmd
    elif job_type == "publish_draft":
        cmd = ["python3", "-u", str(script_dir / "bots" / "tiktok" / "upload.py")]
        if phone:
            cmd += ["--device", phone]
        if config.get("draft_tag"):
            cmd += ["--draft-tag", config["draft_tag"]]
        else:
            grid_index = int(config.get("grid_index", 0))
            cmd += ["--publish-draft", str(grid_index)]
        if config.get("post_id"):
            cmd += ["--post-id", str(int(config["post_id"]))]
        if config.get("account"):
            cmd += ["--account", config["account"]]
        return cmd
    elif job_type in ("content_gen", "content_plan"):
        days = config.get("days", 1)
        ppd = config.get("posts_per_day", 3)
        agent_script = _SCRIPT_DIR / "agent" / "agent_core.py"
        cmd = [
            "python3", "-u", str(agent_script),
            "--days", str(days),
            "--posts-per-day", str(ppd),
        ]
        if config.get("model"):
            cmd += ["--model", config["model"]]
        if phone:
            cmd += ["--phone", phone]
        if config.get("account"):
            cmd += ["--account", config["account"]]
        if config.get("video_model"):
            cmd += ["--video-model", config["video_model"]]
        if config.get("platform"):
            cmd += ["--platform", config["platform"]]
        return cmd
    elif job_type == "inbox_scan":
        cmd = ["python3", "-u", str(script_dir / "bots" / "tiktok" / "inbox_scanner.py")]
        if phone:
            cmd += ["--device", phone]
        max_scrolls = config.get("max_scrolls", 80)
        cmd += ["--max-scrolls", str(max_scrolls)]
        if config.get("account"):
            cmd += ["--account", config["account"]]
        return cmd
    elif job_type == "perf_scan":
        cmd = ["python3", "-u", str(script_dir / "bots" / "tiktok" / "perf_scanner.py")]
        if phone:
            cmd += ["--device", phone]
        num_posts = config.get("num_posts", 10)
        cmd += ["--num-posts", str(num_posts)]
        if config.get("skip_viewers"):
            cmd += ["--skip-viewers"]
        if config.get("skip_engagement"):
            cmd += ["--skip-engagement"]
        if config.get("account"):
            cmd += ["--account", config["account"]]
        return cmd
    elif job_type == "engage":
        cmd = ["python3", "-u", str(script_dir / "bots" / "tiktok" / "engage.py")]
        if phone:
            cmd += ["--device", phone]
        if config.get("duration"):
            cmd += ["--duration", str(int(config["duration"]))]
        if config.get("like_pct"):
            cmd += ["--like-pct", str(int(config["like_pct"]))]
        if config.get("comment_pct"):
            cmd += ["--comment-pct", str(int(config["comment_pct"]))]
        if config.get("favorite_pct"):
            cmd += ["--favorite-pct", str(int(config["favorite_pct"]))]
        if config.get("min_watch"):
            cmd += ["--min-watch", str(config["min_watch"])]
        if config.get("max_watch"):
            cmd += ["--max-watch", str(config["max_watch"])]
        return cmd
    elif job_type == "app_explore":
        script = script_dir / "skills" / "auto_creator.py"
        package = config.get("package", "")
        cmd = ["python3", "-u", str(script), "--package", package]
        if phone:
            cmd += ["--device", phone]
        if config.get("max_depth"):
            cmd += ["--max-depth", str(int(config["max_depth"]))]
        if config.get("max_states"):
            cmd += ["--max-states", str(int(config["max_states"]))]
        if config.get("settle"):
            cmd += ["--settle", str(config["settle"])]
        if config.get("output"):
            cmd += ["--output", config["output"]]
        return cmd
    elif job_type in ("skill_workflow", "skill_action"):
        skill_name = config.get("skill", "tiktok")
        target = config.get("workflow") or config.get("action", "")
        params = config.get("params", {})
        run_type = "workflow" if job_type == "skill_workflow" else "action"
        runner = script_dir / "skills" / "_run_skill.py"
        cmd = [
            "python3", "-u", str(runner),
            "--skill", skill_name,
            f"--{run_type}", target,
            "--device", phone or _BOT_DEVICE,
            "--params", json.dumps(params),
        ]
        return cmd
    return None


# ── Job launch / kill ───────────────────────────────────────────────────────


def _launch_scheduled_job(db, job_row: dict):
    """Launch a queued job subprocess."""
    job_id = job_row["id"]
    phone = job_row.get("phone_serial")
    config = json.loads(job_row.get("config_json") or "{}")
    cmd = _build_scheduled_cmd(job_row["job_type"], config, phone)
    if not cmd:
        finish_job(db, job_id, "failed",
                   error_msg=f"unsupported job_type: {job_row['job_type']}")
        archive_to_runs(db, job_id)
        return

    log_path = f"/tmp/sched_job_{job_id}.log"
    log_f = open(log_path, "w", buffering=1)
    proc = subprocess.Popen(
        cmd,
        stdout=log_f,
        stderr=subprocess.STDOUT,
        cwd=str(_SCRIPT_DIR),
    )
    db.execute(
        text(
            "UPDATE job_queue SET status = :status, started_at = :started, "
            "pid = :pid, log_file = :log_file WHERE id = :id"
        ),
        {
            "status": "running",
            "started": _now(),
            "pid": proc.pid,
            "log_file": log_path,
            "id": job_id,
        },
    )
    db.commit()
    _phone_procs[phone] = {
        "proc": proc,
        "job_id": job_id,
        "log_f": log_f,
        "log_path": log_path,
    }


def _kill_scheduled_job(phone: str | None, db, status: str = "killed",
                        error_msg: str = ""):
    """Kill a running scheduler-managed job on a phone."""
    entry = _phone_procs.get(phone)
    if not entry:
        return
    proc = entry["proc"]
    job_id = entry["job_id"]
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)
    finish_job(db, job_id, status, exit_code=proc.returncode, error_msg=error_msg)
    archive_to_runs(db, job_id)
    try:
        entry["log_f"].close()
    except Exception:
        pass
    del _phone_procs[phone]


# ── Schedule checks ─────────────────────────────────────────────────────────


def _is_job_due(sched: dict, now: datetime, db) -> bool:
    """Check if a scheduled job should be enqueued right now."""
    existing = db.execute(
        text(
            "SELECT COUNT(*) FROM job_queue "
            "WHERE scheduled_job_id = :sid AND status IN ('pending','running')"
        ),
        {"sid": sched["id"]},
    ).scalar()
    if existing > 0:
        return False

    if sched["schedule_type"] == "interval":
        interval = sched.get("interval_minutes") or 60
        last = db.execute(
            text("SELECT MAX(finished_at) FROM job_runs WHERE scheduled_job_id = :sid"),
            {"sid": sched["id"]},
        ).scalar()
        if not last:
            return True
        try:
            last_dt = datetime.fromisoformat(last)
            return now >= last_dt + timedelta(minutes=interval)
        except Exception:
            return True

    elif sched["schedule_type"] == "daily":
        try:
            times = json.loads(sched.get("daily_times") or "[]")
        except (json.JSONDecodeError, ValueError):
            return False
        today_str = now.strftime("%Y-%m-%d")
        now_time = now.strftime("%H:%M")
        for t in times:
            if t <= now_time:
                t_dt = datetime.strptime(f"{today_str} {t}", "%Y-%m-%d %H:%M")
                if now <= t_dt + timedelta(minutes=30):
                    already = db.execute(
                        text(
                            "SELECT COUNT(*) FROM job_runs "
                            "WHERE scheduled_job_id = :sid AND started_at >= :ts"
                        ),
                        {"sid": sched["id"], "ts": f"{today_str} {t}"},
                    ).scalar()
                    if already == 0:
                        return True
    return False


# ── Per-phone queue processing ──────────────────────────────────────────────


def _process_phone_queue(phone: str | None, db, now: datetime):
    """Process the job queue for a single phone."""
    if _is_phone_busy_manual(phone):
        return

    running_entry = _phone_procs.get(phone)
    running_job = None
    if running_entry and running_entry["proc"].poll() is None:
        row = db.execute(
            text("SELECT * FROM job_queue WHERE id = :id"),
            {"id": running_entry["job_id"]},
        ).mappings().first()
        if row:
            running_job = dict(row)

    # Pending job query — handle NULL phone_serial properly
    if phone is None:
        pending_row = db.execute(
            text(
                "SELECT * FROM job_queue WHERE phone_serial IS NULL "
                "AND status = 'pending' ORDER BY priority ASC, enqueued_at ASC LIMIT 1"
            )
        ).mappings().first()
    else:
        pending_row = db.execute(
            text(
                "SELECT * FROM job_queue WHERE phone_serial = :phone "
                "AND status = 'pending' ORDER BY priority ASC, enqueued_at ASC LIMIT 1"
            ),
            {"phone": phone},
        ).mappings().first()

    if not running_job and running_entry:
        # Process finished while we were checking
        proc = running_entry["proc"]
        jid = running_entry["job_id"]
        try:
            running_entry["log_f"].flush()
            running_entry["log_f"].close()
        except Exception:
            pass
        summary = _parse_job_summary(jid, running_entry)
        logger.info(
            "Job #%d finished in queue check (rc=%s), summary=%r",
            jid, proc.returncode, summary,
        )
        finish_job(
            db, jid,
            "completed" if proc.returncode == 0 else "failed",
            exit_code=proc.returncode,
            error_msg=summary or None,
        )
        archive_to_runs(db, jid)
        del _phone_procs[phone]
        running_job = None

    # Check DB for orphaned running jobs on this phone (not in _phone_procs)
    if not running_job:
        if phone is None:
            db_running = db.execute(
                text(
                    "SELECT id, pid FROM job_queue WHERE phone_serial IS NULL "
                    "AND status = 'running' LIMIT 1"
                )
            ).first()
        else:
            db_running = db.execute(
                text(
                    "SELECT id, pid FROM job_queue WHERE phone_serial = :phone "
                    "AND status = 'running' LIMIT 1"
                ),
                {"phone": phone},
            ).first()
        if db_running:
            pid = db_running[1] if db_running else None
            if pid:
                try:
                    os.kill(pid, 0)
                    running_job = True  # block launching
                except (ProcessLookupError, OSError):
                    pass  # PID dead, orphan cleanup will handle it

    pending = dict(pending_row) if pending_row else None

    if pending:
        if not running_job:
            _launch_scheduled_job(db, pending)
        elif isinstance(running_job, dict) and pending["priority"] < running_job.get("priority", 99):
            # Never preempt post/publish_draft jobs
            running_type = running_job.get("job_type", "")
            if running_type in ("post", "publish_draft"):
                pass
            else:
                enq_dt = datetime.fromisoformat(pending["enqueued_at"])
                waited = (now - enq_dt).total_seconds()
                if waited >= _PREEMPT_GRACE_S:
                    _kill_scheduled_job(
                        phone, db, "preempted",
                        f"Preempted by job #{pending['id']}",
                    )
                    _launch_scheduled_job(db, pending)
