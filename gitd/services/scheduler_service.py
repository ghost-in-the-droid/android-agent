"""
Scheduler service — background daemon that ticks every 30 seconds.

Ported from _deprecated/server_flask.py scheduler engine.
Uses SQLAlchemy sessions instead of raw sqlite3.

Public API:
    start()  — launch the daemon thread
    stop()   — set the stop flag (thread exits on next iteration)
"""

import logging
import os
import signal
import subprocess
import threading
import time
from datetime import datetime

from sqlalchemy import text

from gitd.models.base import SessionLocal
from gitd.services._job_helpers import (
    _enqueue_job,
    _parse_job_summary,
    archive_to_runs,
    finish_job,
)

try:
    from gitd.services.content_pipeline import _content_plan_tick
except ImportError:
    _content_plan_tick = None  # Premium feature
from gitd.services.job_engine import (
    _is_job_due,
    _kill_scheduled_job,
    _phone_procs,
    _process_phone_queue,
)

logger = logging.getLogger(__name__)

# ── Module-level state ──────────────────────────────────────────────────────
_scheduler_lock = threading.Lock()
_stop_flag = threading.Event()
_thread: threading.Thread | None = None


# ── WiFi reconnect watchdog ────────────────────────────────────────────────

_wifi_last_check = 0.0


def _wifi_reconnect_tick(db):
    """Every ~60s, check WiFi devices and reconnect any that dropped."""
    global _wifi_last_check
    now = time.time()
    if now - _wifi_last_check < 60:
        return
    _wifi_last_check = now

    try:
        from gitd.models.phone import Phone

        wifi_phones = (
            db.query(Phone)
            .filter(
                Phone.connection_type.in_(["wifi", "wireless_debug"]),
                Phone.wifi_ip.isnot(None),
            )
            .all()
        )
        if not wifi_phones:
            return

        # Get currently connected devices
        result = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=5)
        connected = result.stdout

        for phone in wifi_phones:
            wifi_serial = f"{phone.wifi_ip}:{phone.wifi_port or 5555}"
            if wifi_serial in connected:
                continue
            # Device dropped — try reconnect
            logger.info("WiFi reconnect: %s (%s)", phone.serial, wifi_serial)
            try:
                r = subprocess.run(["adb", "connect", wifi_serial], capture_output=True, text=True, timeout=5)
                if "connected" in r.stdout.lower():
                    logger.info("WiFi reconnected: %s", wifi_serial)
                else:
                    logger.warning("WiFi reconnect failed: %s — %s", wifi_serial, r.stdout.strip())
            except Exception as e:
                logger.warning("WiFi reconnect error: %s — %s", wifi_serial, e)
    except Exception:
        pass


# ── Main tick ───────────────────────────────────────────────────────────────


def _scheduler_tick():
    """One tick of the scheduler -- check all schedules and queues."""
    with _scheduler_lock:
        db = SessionLocal()
        try:
            now = datetime.now()

            # 0. Clean orphaned running jobs (dead PIDs not in _phone_procs)
            for o in db.execute(text("SELECT * FROM job_queue WHERE status = 'running'")).mappings().all():
                o = dict(o)
                phone = o.get("phone_serial")
                if phone in _phone_procs and _phone_procs[phone].get("job_id") == o["id"]:
                    continue
                pid = o.get("pid")
                alive = False
                if pid:
                    try:
                        os.kill(pid, 0)
                        alive = True
                    except (ProcessLookupError, PermissionError, OSError):
                        pass
                if alive:
                    max_dur = o.get("max_duration_s") or 3600
                    if o.get("started_at"):
                        elapsed = (now - datetime.fromisoformat(o["started_at"])).total_seconds()
                        if elapsed > max_dur:
                            logger.warning(
                                "Orphaned job #%d (%s, PID %s) -- killing (elapsed %ds > max %ds)",
                                o["id"],
                                o["job_type"],
                                pid,
                                int(elapsed),
                                max_dur,
                            )
                            try:
                                os.kill(pid, signal.SIGTERM)
                                time.sleep(2)
                                os.kill(pid, 0)
                                os.kill(pid, signal.SIGKILL)
                            except (ProcessLookupError, OSError):
                                pass
                            try:
                                os.waitpid(pid, os.WNOHANG)
                            except (ChildProcessError, OSError):
                                pass
                            log_file = o.get("log_file") or f"/tmp/sched_job_{o['id']}.log"
                            summary = _parse_job_summary(o["id"], log_path=log_file)
                            dur_str = f"{int(elapsed / 60)}m"
                            msg = f"T {dur_str}"
                            if summary:
                                msg += f" \u00b7 {summary}"
                            finish_job(db, o["id"], "timeout", error_msg=msg)
                            archive_to_runs(db, o["id"])
                    continue
                if not alive:
                    logger.info(
                        "Orphaned job #%d (%s, PID %s) -- archiving",
                        o["id"],
                        o["job_type"],
                        pid,
                    )
                    orphan_summary = ""
                    log_file = o.get("log_file") or f"/tmp/sched_job_{o['id']}.log"
                    try:
                        with open(log_file, "r", errors="replace") as lf:
                            all_lines = lf.readlines()
                        for line in reversed(all_lines[-10:]):
                            if "[done]" in line:
                                orphan_summary = line.strip().split("[done]")[-1].strip()
                                break
                    except (FileNotFoundError, OSError):
                        pass
                    try:
                        os.waitpid(pid, os.WNOHANG)
                    except (ChildProcessError, OSError):
                        pass
                    final_status = "completed" if orphan_summary else "failed"
                    final_msg = orphan_summary or "Orphaned (PID dead)"
                    finish_job(db, o["id"], final_status, error_msg=final_msg)
                    archive_to_runs(db, o["id"])

            # 1. Enqueue due scheduled jobs
            scheds = db.execute(text("SELECT * FROM scheduled_jobs WHERE is_enabled = 1")).mappings().all()
            for s in scheds:
                s = dict(s)
                if _is_job_due(s, now, db):
                    _enqueue_job(
                        db,
                        scheduled_job_id=s["id"],
                        phone_serial=s.get("phone_serial"),
                        job_type=s["job_type"],
                        priority=s.get("priority", 2),
                        config_json=s.get("config_json", "{}"),
                        max_duration_s=s.get("max_duration_s", 3600),
                    )

            # 2. Collect all phones with pending/running work
            phones = set()
            for row in db.execute(
                text("SELECT DISTINCT phone_serial FROM job_queue WHERE status IN ('pending','running')")
            ).fetchall():
                phones.add(row[0])
            for p in list(_phone_procs.keys()):
                phones.add(p)

            for phone in phones:
                _process_phone_queue(phone, db, now)

            # 3. Check running jobs for timeout
            for phone, entry in list(_phone_procs.items()):
                if entry["proc"].poll() is not None:
                    continue
                job = (
                    db.execute(
                        text("SELECT * FROM job_queue WHERE id = :id"),
                        {"id": entry["job_id"]},
                    )
                    .mappings()
                    .first()
                )
                if job:
                    job = dict(job)
                    max_dur = job.get("max_duration_s") or 3600
                    if job.get("started_at"):
                        elapsed = (now - datetime.fromisoformat(job["started_at"])).total_seconds()
                        if elapsed > max_dur:
                            summary = _parse_job_summary(entry["job_id"], entry)
                            dur_str = f"{int(elapsed / 60)}m"
                            msg = f"T {dur_str}"
                            if summary:
                                msg += f" \u00b7 {summary}"
                            _kill_scheduled_job(phone, db, "timeout", msg)

            # 4. Detect externally finished processes
            for phone, entry in list(_phone_procs.items()):
                if entry["proc"].poll() is not None:
                    proc = entry["proc"]
                    jid = entry["job_id"]
                    try:
                        entry["log_f"].flush()
                        entry["log_f"].close()
                    except Exception:
                        pass
                    summary = _parse_job_summary(jid, entry)
                    logger.info(
                        "Job #%d finished in step4 (rc=%s), summary=%r",
                        jid,
                        proc.returncode,
                        summary,
                    )
                    finish_job(
                        db,
                        jid,
                        "completed" if proc.returncode == 0 else "failed",
                        exit_code=proc.returncode,
                        error_msg=summary or None,
                    )
                    archive_to_runs(db, jid)
                    del _phone_procs[phone]

            # 5. Content plan pipeline (premium)
            if _content_plan_tick is not None:
                _content_plan_tick(db, now)

            # 6. WiFi device reconnect watchdog
            _wifi_reconnect_tick(db)

        except Exception:
            logger.exception("tick error")
        finally:
            db.close()


# ── Daemon loop ─────────────────────────────────────────────────────────────


def _scheduler_loop():
    """Daemon thread -- ticks every 30s until stop flag is set."""
    while not _stop_flag.is_set():
        _stop_flag.wait(30)
        if _stop_flag.is_set():
            break
        _scheduler_tick()


def start():
    """Start the scheduler daemon thread."""
    global _thread
    if _thread is not None and _thread.is_alive():
        logger.info("Already running")
        return
    _stop_flag.clear()
    _thread = threading.Thread(target=_scheduler_loop, daemon=True, name="scheduler")
    _thread.start()
    logger.info("Started (30s tick)")


def stop():
    """Signal the scheduler daemon to stop."""
    _stop_flag.set()
    logger.info("Stop requested")
