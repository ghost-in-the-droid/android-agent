"""Cross-platform phone screen recording helpers."""
from __future__ import annotations

import re
import signal
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from gitd.bots.common.device import get_device, is_ios_ref

RECORDINGS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "phone_recordings"
RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)

_active: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


def safe_recording_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "device"


def _new_filename(device: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{safe_recording_name(device)}_{stamp}.mp4"


def _platform(device: str) -> str:
    return "ios" if is_ios_ref(device) else "android"


def _recording_path(filename: str, recordings_dir: Path | str | None = None) -> Path:
    name = Path(filename).name
    if name != filename:
        raise ValueError("invalid recording filename")
    root = Path(recordings_dir) if recordings_dir is not None else RECORDINGS_DIR
    root.mkdir(parents=True, exist_ok=True)
    return root / name


def start_recording(device: str, filename: str = "", recordings_dir: Path | str | None = None) -> dict:
    """Start recording a device screen.

    iOS records WDA MJPEG through ffmpeg. Android records on-device with
    `screenrecord`, then pulls the MP4 when stopped.
    """
    if not device:
        return {"ok": False, "error": "device required"}
    with _lock:
        existing = _active.get(device)
        if existing and existing["proc"].poll() is None:
            return {
                "ok": False,
                "error": "recording already running",
                "device": device,
                "platform": existing["platform"],
                "filename": existing["filename"],
            }

        name = safe_recording_name(filename) if filename else _new_filename(device)
        if not name.endswith(".mp4"):
            name += ".mp4"
        local_path = _recording_path(name, recordings_dir=recordings_dir)
        platform = _platform(device)

        if platform == "ios":
            mjpeg_url = get_device(device).mjpeg_url
            cmd = [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-f",
                "mjpeg",
                "-i",
                mjpeg_url,
                "-an",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(local_path),
            ]
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            entry = {
                "device": device,
                "platform": platform,
                "mode": "wda-mjpeg",
                "filename": name,
                "local_path": str(local_path),
                "device_path": "",
                "mjpeg_url": mjpeg_url,
                "proc": proc,
                "started_at": time.time(),
            }
        else:
            device_path = f"/sdcard/ghost_recording_{safe_recording_name(device)}_{int(time.time())}.mp4"
            proc = subprocess.Popen(
                ["adb", "-s", device, "shell", "screenrecord", device_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            entry = {
                "device": device,
                "platform": platform,
                "mode": "adb-screenrecord",
                "filename": name,
                "local_path": str(local_path),
                "device_path": device_path,
                "mjpeg_url": "",
                "proc": proc,
                "started_at": time.time(),
            }
        _active[device] = entry
        return _entry_status(entry)


def _stop_process(entry: dict[str, Any]) -> None:
    proc = entry["proc"]
    if entry["platform"] == "ios":
        proc.terminate()
    else:
        proc.send_signal(signal.SIGINT)
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass


def stop_recording(device: str) -> dict:
    if not device:
        return {"ok": False, "error": "device required"}
    with _lock:
        entry = _active.get(device)
        if not entry:
            return {"ok": False, "device": device, "platform": _platform(device), "error": "recording not running"}
        _stop_process(entry)
        local_path = Path(entry["local_path"])
        if entry["platform"] == "android":
            try:
                subprocess.run(
                    ["adb", "-s", device, "pull", entry["device_path"], str(local_path)],
                    timeout=30,
                    check=True,
                    capture_output=True,
                )
                subprocess.run(
                    ["adb", "-s", device, "shell", "rm", entry["device_path"]],
                    timeout=5,
                    capture_output=True,
                )
            except (subprocess.SubprocessError, OSError) as e:
                _active.pop(device, None)
                return {
                    **_entry_status(entry, running=False),
                    "ok": False,
                    "error": f"failed to pull recording: {e}",
                }
        _active.pop(device, None)
        saved = local_path.exists() and local_path.stat().st_size > 0
        return {
            **_entry_status(entry, running=False),
            "ok": bool(saved),
            "saved": bool(saved),
            "size_bytes": local_path.stat().st_size if saved else 0,
            "url": f"/api/phone/recording/{entry['filename']}" if saved else "",
            "error": "" if saved else "recording file was not created",
        }


def _entry_status(entry: dict[str, Any], running: bool | None = None) -> dict:
    proc = entry["proc"]
    if running is None:
        running = proc.poll() is None
    return {
        "ok": True,
        "device": entry["device"],
        "platform": entry["platform"],
        "mode": entry["mode"],
        "running": running,
        "filename": entry["filename"],
        "path": entry["local_path"],
        "started_at": entry["started_at"],
        "duration_s": round(max(0, time.time() - entry["started_at"]), 2),
        "mjpeg_url": entry.get("mjpeg_url", ""),
    }


def recording_status(device: str) -> dict:
    with _lock:
        entry = _active.get(device)
        if not entry:
            return {"ok": True, "device": device, "platform": _platform(device), "running": False}
        return _entry_status(entry)


def list_recordings() -> list[dict]:
    items = []
    for path in sorted(RECORDINGS_DIR.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True):
        stat = path.stat()
        items.append(
            {
                "name": path.name,
                "size_bytes": stat.st_size,
                "size_mb": round(stat.st_size / 1_048_576, 2),
                "date": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                "url": f"/api/phone/recording/{path.name}",
            }
        )
    return items


def recording_file(filename: str) -> Path:
    path = _recording_path(filename)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(filename)
    return path


def delete_recording(filename: str) -> dict:
    path = recording_file(filename)
    path.unlink()
    return {"ok": True, "deleted": path.name}
