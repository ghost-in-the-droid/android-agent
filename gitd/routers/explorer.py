"""App Explorer routes: start/stop exploration, status, runs, screenshots."""

import json
import os
import shutil
import signal
import subprocess as _subprocess
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from gitd.config import settings
from gitd.models.base import get_db

router = APIRouter(prefix="/api/explorer", tags=["explorer"])

_BOT_DEVICE = settings.default_device
_EXPLORER_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "app_explorer"
_EXPLORER_DIR.mkdir(parents=True, exist_ok=True)
_SCRIPT = Path(__file__).resolve().parent.parent / "skills" / "auto_creator.py"
_PROJECT_DIR = Path(__file__).resolve().parent.parent.parent

# Active exploration process
_active_proc: dict = {}  # {"proc": Popen, "pid": int, "package": str, "device": str, "log_file": str}


@router.post("/start", summary="Start App Exploration")
def explorer_start(data: dict = Body({})):
    """Start app exploration immediately as a subprocess (no job queue delay)."""
    global _active_proc
    package = data.get("package", "").strip()
    if not package:
        raise HTTPException(status_code=400, detail="package is required")
    device = data.get("device", _BOT_DEVICE)
    max_depth = int(data.get("max_depth", 3))
    max_states = int(data.get("max_states", 20))
    settle = float(data.get("settle", 1.5))
    output_dir = str(_EXPLORER_DIR / package)

    # Kill any existing exploration
    if _active_proc.get("proc"):
        try:
            _active_proc["proc"].kill()
        except Exception:
            pass
        _active_proc = {}

    # Start directly as subprocess
    log_file = f"/tmp/explorer_{package.replace('.', '_')}.log"
    cmd = [
        "python3", "-u", str(_SCRIPT),
        "--package", package, "--device", device,
        "--max-depth", str(max_depth), "--max-states", str(max_states),
        "--settle", str(settle), "--output", output_dir,
    ]
    log_f = open(log_file, "w")
    proc = _subprocess.Popen(cmd, stdout=log_f, stderr=_subprocess.STDOUT,
                             cwd=str(_PROJECT_DIR))
    _active_proc = {
        "proc": proc, "pid": proc.pid, "package": package,
        "device": device, "log_file": log_file, "output_dir": output_dir,
        "max_states": max_states,
    }
    return {"ok": True, "pid": proc.pid, "output_dir": output_dir}


@router.post("/stop", summary="Stop App Exploration")
def explorer_stop(data: dict = Body({})):
    """Kill a running exploration."""
    global _active_proc
    proc = _active_proc.get("proc")
    if proc and proc.poll() is None:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
    _active_proc = {}
    return {"ok": True}


@router.get("/status", summary="Get Exploration Status")
def explorer_status():
    """Poll exploration progress."""
    proc = _active_proc.get("proc")
    is_running = proc is not None and proc.poll() is None
    if not _active_proc:
        return {"running": False}

    package = _active_proc.get("package", "")
    output_dir = _active_proc.get("output_dir") or str(_EXPLORER_DIR / package)
    result = {
        "running": is_running,
        "pid": _active_proc.get("pid"),
        "package": package,
        "max_states": _active_proc.get("max_states", 20),
        "states_found": 0,
        "transitions": 0,
        "current_depth": 0,
        "log_tail": [],
    }

    # Read progress.json (written by auto_creator.py during exploration)
    progress_path = Path(output_dir) / "progress.json"
    if progress_path.exists():
        try:
            prog = json.loads(progress_path.read_text())
            result["states_found"] = prog.get("states_found", 0)
            result["transitions"] = prog.get("transitions", 0)
            result["current_depth"] = prog.get("current_depth", 0)
            result["log_tail"] = prog.get("log_tail", [])
        except Exception:
            pass

    # Fallback: read log file tail
    if not result["log_tail"]:
        log_file = _active_proc.get("log_file", "")
        if log_file:
            try:
                with open(log_file, "r", errors="replace") as f:
                    lines = f.readlines()
                result["log_tail"] = [line.rstrip() for line in lines[-20:]]
            except Exception:
                pass

    # Clean up if finished
    if not is_running and _active_proc:
        result["running"] = False

    return result


@router.get("/runs", summary="List Exploration Runs")
def explorer_runs():
    """List all previous exploration runs."""
    runs = []
    if _EXPLORER_DIR.is_dir():
        for d in sorted(_EXPLORER_DIR.iterdir()):
            if not d.is_dir():
                continue
            graph_path = d / "state_graph.json"
            if not graph_path.exists():
                continue
            try:
                g = json.loads(graph_path.read_text())
                mtime = datetime.fromtimestamp(graph_path.stat().st_mtime)
                runs.append(
                    {
                        "name": d.name,
                        "package": g.get("package", d.name),
                        "states": g.get("total_states", 0),
                        "transitions": g.get("total_transitions", 0),
                        "max_depth": g.get("max_depth", 0),
                        "device": g.get("device", ""),
                        "date": mtime.strftime("%Y-%m-%d %H:%M"),
                    }
                )
            except Exception:
                runs.append({"name": d.name, "states": 0, "transitions": 0, "date": ""})
    return runs


@router.get("/run/{name:path}", summary="Get Exploration Run Detail")
def explorer_run_detail(name: str):
    """Get full state graph for a run."""
    graph_path = _EXPLORER_DIR / name / "state_graph.json"
    if not graph_path.exists():
        raise HTTPException(status_code=404, detail="Run not found")
    try:
        g = json.loads(graph_path.read_text())
        return g
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/screenshot/{name:path}/{state_id}", summary="Serve Exploration Screenshot")
def explorer_screenshot(name: str, state_id: str):
    """Serve a screenshot image for a state."""
    ss_dir = _EXPLORER_DIR / name / "screenshots"
    fname = f"{state_id}.png"
    fpath = ss_dir / fname
    if not fpath.exists():
        raise HTTPException(status_code=404, detail="Screenshot not found")
    return FileResponse(str(fpath), media_type="image/png")


@router.delete("/delete/{name:path}", summary="Delete Exploration Run")
def explorer_delete(name: str):
    """Delete an exploration run."""
    run_dir = _EXPLORER_DIR / name
    if not run_dir.exists() or not run_dir.is_dir():
        raise HTTPException(status_code=404, detail="Not found")
    shutil.rmtree(run_dir)
    return {"ok": True}
