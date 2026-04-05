"""Test runner routes: catalog, start/stop, status, logs, recordings."""

import ast
import logging
import os
import re
import shutil
import signal
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import FileResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["tests"])

_tr_runs: dict = {}  # serial -> {proc, log_f, log_path, sr_proc, ...}
_tr_lock = threading.Lock()
_TESTS_DIR = Path(__file__).parent.parent.parent / "tests"
_TR_RECORDINGS_DIR = Path(__file__).parent.parent.parent / "test_recordings"
_TR_RECORDINGS_DIR.mkdir(exist_ok=True)


def _device_label(serial: str) -> str:
    """Return nickname for a phone serial, falling back to first 5 chars."""
    try:
        from gitd.models import Phone, SessionLocal

        session = SessionLocal()
        try:
            phone = session.get(Phone, serial)
            if phone and phone.nickname:
                return phone.nickname
        finally:
            session.close()
    except Exception:
        pass
    return serial[:5] if serial else ""


def _sr_start(serial: str) -> tuple:
    """Start screen recording on device."""
    subprocess.run(
        ["adb", "-s", serial, "shell", "input", "keyevent", "KEYCODE_WAKEUP"], timeout=5, capture_output=True
    )
    subprocess.run(["adb", "-s", serial, "shell", "input", "keyevent", "KEYCODE_MENU"], timeout=5, capture_output=True)
    time.sleep(0.3)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    device_path = f"/sdcard/test_rec_{ts}.mp4"
    proc = subprocess.Popen(
        ["adb", "-s", serial, "shell", "screenrecord", device_path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return proc, device_path


def _sr_stop_and_pull(serial, sr_proc, device_path, local_name):
    """Stop screen recording and pull MP4 from device."""
    sr_proc.send_signal(signal.SIGINT)
    try:
        sr_proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        sr_proc.kill()
    time.sleep(2)
    local_path = _TR_RECORDINGS_DIR / local_name
    try:
        subprocess.run(
            ["adb", "-s", serial, "pull", device_path, str(local_path)], timeout=30, check=True, capture_output=True
        )
        subprocess.run(["adb", "-s", serial, "shell", "rm", device_path], timeout=5, capture_output=True)
        return local_path
    except (subprocess.SubprocessError, OSError):
        return None


def _tr_finalize(device):
    """Stop recording + pull MP4. Must be called with _tr_lock held."""
    entry = _tr_runs.get(device)
    if not entry or not entry.get("sr_proc"):
        return
    lp = _sr_stop_and_pull(device, entry["sr_proc"], entry["sr_device_path"], entry["sr_local_name"])
    entry["sr_local_path"] = str(lp) if lp else None
    entry["sr_proc"] = None
    try:
        entry["log_f"].close()
    except Exception:
        pass
    saved_log = None
    if lp and entry.get("log_path") and entry["log_path"].exists():
        saved_log = _TR_RECORDINGS_DIR / (Path(entry["sr_local_name"]).stem + ".log")
        shutil.copy2(str(entry["log_path"]), str(saved_log))
    log_src = str(saved_log) if saved_log else str(entry.get("log_path", ""))
    if lp and log_src:
        threading.Thread(target=_tr_gen_overlay, args=(str(lp), log_src), daemon=True).start()


def _tr_gen_overlay(video_path, log_path):
    try:
        from gitd.tools.video_overlay import generate_overlay

        result = generate_overlay(video_path, log_path)
        if result:
            logger.info("Overlay generated: %s", result)
    except Exception as e:
        logger.error("Overlay error: %s", e)


def _tr_watcher():
    """Background thread: auto-finalize recordings when tests finish."""
    wake_counter = 0
    while True:
        time.sleep(2)
        wake_counter += 1
        with _tr_lock:
            for dev, entry in list(_tr_runs.items()):
                if entry["proc"].poll() is not None and entry.get("sr_proc") and not entry.get("sr_local_path"):
                    _tr_finalize(dev)
                elif entry["proc"].poll() is None and entry.get("sr_proc") and wake_counter % 15 == 0:
                    try:
                        subprocess.run(
                            ["adb", "-s", dev, "shell", "input", "keyevent", "KEYCODE_WAKEUP"],
                            timeout=3,
                            capture_output=True,
                        )
                    except (subprocess.SubprocessError, OSError):
                        pass


threading.Thread(target=_tr_watcher, daemon=True).start()


# ── Routes ──────────────────────────────────────────────────────────────────


@router.get("/api/tests", summary="List Test Catalog")
def tests_catalog():
    """Return list of test files and their test function names."""
    catalog = []
    for tf in sorted(_TESTS_DIR.glob("test_*.py")):
        try:
            src = tf.read_text()
            tree = ast.parse(src)
            funcs = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")]
            catalog.append({"file": tf.name, "tests": funcs})
        except Exception:
            catalog.append({"file": tf.name, "tests": []})
    return catalog


@router.post("/api/test-runner/start", summary="Start Test Run")
def tr_start(data: dict = Body({})):
    """Start a test run on a device with optional screen recording."""
    file_ = data.get("file", "").strip()
    test_ = data.get("test", "").strip()
    device = (data.get("device") or "").strip()
    retry = bool(data.get("retry", False))
    if not file_:
        raise HTTPException(status_code=400, detail="file required")
    if not device:
        raise HTTPException(status_code=400, detail="device required")
    with _tr_lock:
        existing = _tr_runs.get(device)
        if existing and existing["proc"].poll() is None:
            raise HTTPException(status_code=400, detail=f"Already running on {device}")

        node = f"tests/{file_}" + (f"::{test_}" if test_ else "")
        test_label = test_ or file_.replace(".py", "")

        try:
            sr_proc, sr_device_path = _sr_start(device)
            time.sleep(0.5)
        except Exception:
            sr_proc, sr_device_path = None, None

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        sr_local_name = f"{device}_{ts}_{test_label}.mp4"

        cmd = ["python3", "-u", "-m", "pytest", "-v", "--tb=short", "-s"]
        if retry:
            cmd += ["--reruns", "2", "--reruns-delay", "5"]
        cmd.append(node)
        env = {**os.environ, "PYTHONUNBUFFERED": "1", "DEVICE": device}
        log_path = Path(f"/tmp/tiktok_tests_{device}.log")
        log_f = open(log_path, "w", buffering=1)
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=str(Path(__file__).parent.parent.parent),
            env=env,
            bufsize=1,
            text=True,
        )

        def _ts_writer(p, lf):
            for line in p.stdout:
                lf.write(f"[{datetime.now().strftime('%H:%M:%S')}] {line}")
                lf.flush()

        threading.Thread(target=_ts_writer, args=(proc, log_f), daemon=True).start()
        _tr_runs[device] = {
            "proc": proc,
            "log_f": log_f,
            "log_path": log_path,
            "sr_proc": sr_proc,
            "sr_device_path": sr_device_path,
            "sr_local_name": sr_local_name,
            "sr_local_path": None,
            "test_node": node,
            "started_at": ts,
        }
    return {"ok": True}


@router.post("/api/test-runner/stop", summary="Stop Test Run")
def tr_stop(data: dict = Body({})):
    """Stop a running test on a device and finalize recording."""
    device = (data.get("device") or "").strip()
    if not device:
        raise HTTPException(status_code=400, detail="device required")
    with _tr_lock:
        entry = _tr_runs.get(device)
        if not entry or entry["proc"].poll() is not None:
            return {"ok": False, "error": "Not running on this device"}
        entry["proc"].terminate()
        try:
            entry["proc"].wait(timeout=5)
        except subprocess.TimeoutExpired:
            entry["proc"].kill()
        _tr_finalize(device)
    return {"ok": True}


@router.get("/api/test-runner/status", summary="Get Test Runner Status")
def tr_status(device: str = ""):
    """Check test run status for one or all devices."""
    device = device.strip()
    with _tr_lock:
        if device:
            entry = _tr_runs.get(device)
            if not entry:
                return {"running": False, "returncode": None, "recording": None}
            running = entry["proc"].poll() is None
            rc = entry["proc"].returncode if not running else None
            rec = entry.get("sr_local_name") if entry.get("sr_local_path") else None
            return {"running": running, "returncode": rc, "recording": rec}
        else:
            result = {}
            for dev, entry in _tr_runs.items():
                running = entry["proc"].poll() is None
                rc = entry["proc"].returncode if not running else None
                rec = entry.get("sr_local_name") if entry.get("sr_local_path") else None
                result[dev] = {
                    "running": running,
                    "returncode": rc,
                    "recording": rec,
                    "test_node": entry.get("test_node", ""),
                }
            return result


@router.get("/api/test-runner/logs", summary="Get Test Runner Logs")
def tr_logs(device: str = "", since: int = 0):
    """Return test runner log lines for a device since a given offset."""
    device = device.strip()
    if not device:
        return {"lines": [], "total": 0, "running": False, "returncode": None}
    with _tr_lock:
        entry = _tr_runs.get(device)
    if not entry:
        return {"lines": [], "total": 0, "running": False, "returncode": None}
    log_path = entry["log_path"]
    if not log_path.exists():
        return {"lines": [], "total": 0, "running": False, "returncode": None}
    with open(log_path, "r", errors="replace") as f:
        all_lines = f.readlines()
    with _tr_lock:
        running = entry["proc"].poll() is None
        rc = entry["proc"].returncode if not running else None
        rec = entry.get("sr_local_name") if entry.get("sr_local_path") else None
    return {
        "lines": [line.rstrip("\n") for line in all_lines[since:]],
        "total": len(all_lines),
        "running": running,
        "returncode": rc,
        "recording": rec,
    }


@router.get("/api/test-runner/recordings", summary="List Test Recordings")
def tr_recordings():
    """List all saved test recordings."""
    recs = []
    for f in sorted(_TR_RECORDINGS_DIR.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True):
        if "_overlay.mp4" in f.name:
            continue
        st = f.stat()
        log_file = _TR_RECORDINGS_DIR / (f.stem + ".log")
        overlay_file = _TR_RECORDINGS_DIR / (f.stem + "_overlay.mp4")
        result = None
        if log_file.exists():
            try:
                tail = log_file.read_text(errors="replace").strip().splitlines()[-3:]
                summary = " ".join(tail)
                pm = re.search(r"(\d+) passed", summary)
                fm = re.search(r"(\d+) failed", summary)
                sm = re.search(r"(\d+) skipped", summary)
                em = re.search(r"(\d+) error", summary)
                result = {
                    "passed": int(pm.group(1)) if pm else 0,
                    "failed": int(fm.group(1)) if fm else 0,
                    "skipped": int(sm.group(1)) if sm else 0,
                    "errors": int(em.group(1)) if em else 0,
                }
            except Exception:
                pass
        serial = f.stem.split("_")[0] if "_" in f.stem else ""
        recs.append(
            {
                "name": f.name,
                "size_mb": round(st.st_size / 1_048_576, 2),
                "date": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                "has_log": log_file.exists(),
                "has_overlay": overlay_file.exists(),
                "result": result,
                "device": _device_label(serial),
            }
        )
    return recs


@router.get("/api/test-runner/recording/{filename:path}", summary="Serve Test Recording File")
def tr_recording_file(filename: str):
    """Serve a test recording MP4."""
    fpath = _TR_RECORDINGS_DIR / filename
    if not fpath.exists() or not fpath.is_file():
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(str(fpath), media_type="video/mp4")


@router.get("/api/test-runner/recording-log/{filename:path}", summary="Serve Recording Log File")
def tr_recording_log(filename: str):
    """Serve the saved log for a recording."""
    stem = filename.replace(".mp4", "")
    log_path = _TR_RECORDINGS_DIR / (stem + ".log")
    if not log_path.exists():
        return {"lines": []}
    lines = log_path.read_text(errors="replace").splitlines()
    return {"lines": lines}


@router.delete("/api/test-runner/recording/{filename:path}", summary="Delete Test Recording")
def tr_recording_delete(filename: str):
    """Delete a test recording and its associated log/overlay files."""
    stem = filename.replace(".mp4", "")
    deleted = []
    for suffix in [".mp4", ".log", "_overlay.mp4"]:
        p = _TR_RECORDINGS_DIR / (stem + suffix)
        if p.exists():
            p.unlink()
            deleted.append(p.name)
    if not deleted:
        raise HTTPException(status_code=404, detail="not found")
    return {"ok": True, "deleted": deleted}
