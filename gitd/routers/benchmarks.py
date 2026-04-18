"""Benchmark API — run task suites through the agent, track results."""

import json
import logging
import threading
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from starlette.responses import StreamingResponse

from gitd.benchmarks.runner import get_run, list_runs, run_benchmark, stop_run, subscribe, unsubscribe

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/benchmarks", tags=["benchmarks"])


# ── Request/Response models ──────────────────────────────────────────────


class RunRequest(BaseModel):
    suite: str = "ghost_bench"
    tasks: Optional[list[str]] = None  # None = all tasks in the suite
    provider: str = "ollama"
    model: str = "gemma3:4b"
    device: str = "emulator-5554"


class RunResponse(BaseModel):
    ok: bool
    run_id: str
    message: str


# ── Suites ───────────────────────────────────────────────────────────────


SUITES = {
    "ghost_bench": {
        "name": "Ghost Bench",
        "description": "Built-in lightweight benchmark — settings toggles, app navigation",
        "module": "gitd.benchmarks.ghost_bench.tasks",
    },
}


@router.get("/suites", summary="List Benchmark Suites")
def api_list_suites():
    return [{"id": k, "name": v["name"], "description": v["description"]} for k, v in SUITES.items()]


# ── Tasks ────────────────────────────────────────────────────────────────


def _get_suite_tasks(suite: str):
    """Import and return tasks for a suite."""
    if suite not in SUITES:
        raise HTTPException(status_code=404, detail=f"Unknown suite: {suite}")
    import importlib

    mod = importlib.import_module(SUITES[suite]["module"])
    return mod.load_tasks, mod.get_task, mod.list_task_ids


@router.get("/tasks", summary="List Tasks in a Suite")
def api_list_tasks(suite: str = "ghost_bench", category: Optional[str] = None):
    load_tasks, _, _ = _get_suite_tasks(suite)
    tasks = load_tasks(category)
    return [
        {
            "id": t.id,
            "goal": t.goal,
            "app": t.app,
            "category": t.category,
            "complexity": t.complexity,
            "max_steps": t.max_steps,
        }
        for t in tasks
    ]


# ── Runs ─────────────────────────────────────────────────────────────────


@router.post("/runs", summary="Start Benchmark Run", response_model=RunResponse)
def api_start_run(req: RunRequest):
    load_tasks, get_task, list_task_ids = _get_suite_tasks(req.suite)

    if req.tasks:
        tasks = [get_task(tid) for tid in req.tasks]
        tasks = [t for t in tasks if t is not None]
        if not tasks:
            raise HTTPException(status_code=400, detail="No valid task IDs provided")
    else:
        tasks = load_tasks()

    run_id = str(uuid.uuid4())[:8]

    def _run():
        run_benchmark(
            tasks,
            req.model,
            req.device,
            provider=req.provider,
            suite=req.suite,
            run_id=run_id,
        )

    threading.Thread(target=_run, daemon=True).start()
    log.info("Started benchmark %s: %d tasks, %s/%s on %s", run_id, len(tasks), req.provider, req.model, req.device)

    return RunResponse(
        ok=True,
        run_id=run_id,
        message=f"Started {len(tasks)} tasks with {req.provider}/{req.model}",
    )


@router.get("/runs", summary="List Benchmark Runs")
def api_list_runs():
    return list_runs()


@router.get("/runs/{run_id}", summary="Get Run Details")
def api_get_run(run_id: str):
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return run


@router.post("/runs/{run_id}/stop", summary="Stop Running Benchmark")
def api_stop_run(run_id: str):
    ok = stop_run(run_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Run not found or already completed")
    return {"ok": True}


@router.get("/runs/{run_id}/events", summary="Stream Live Events (SSE)")
def api_stream_events(run_id: str):
    """Server-Sent Events stream of live benchmark progress."""
    q = subscribe(run_id)

    def event_generator():
        try:
            while True:
                try:
                    event = q.get(timeout=30)
                    yield f"data: {json.dumps(event)}\n\n"
                    if event.get("type") == "run_done":
                        break
                except Exception:
                    yield ": keepalive\n\n"
        finally:
            unsubscribe(run_id, q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
