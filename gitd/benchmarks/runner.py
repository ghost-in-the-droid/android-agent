"""Benchmark runner — orchestrates tasks through an agent and evaluates results."""

import json
import logging
import queue
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

import requests

from gitd.benchmarks.base import Task, TaskResult

log = logging.getLogger(__name__)

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

# ── Event pub/sub for live SSE streaming ─────────────────────────────────

_event_queues: dict[str, list[queue.Queue]] = {}


def subscribe(run_id: str) -> queue.Queue:
    q: queue.Queue = queue.Queue(maxsize=500)
    _event_queues.setdefault(run_id, []).append(q)
    return q


def unsubscribe(run_id: str, q: queue.Queue) -> None:
    if run_id in _event_queues:
        _event_queues[run_id] = [x for x in _event_queues[run_id] if x is not q]


def _emit(run_id: str, event: dict) -> None:
    for q in _event_queues.get(run_id, []):
        try:
            q.put_nowait(event)
        except queue.Full:
            pass


# ── Run data structures ──────────────────────────────────────────────────


@dataclass
class BenchmarkRun:
    id: str
    suite: str
    model: str
    provider: str
    device: str
    status: str = "running"
    results: list[TaskResult] = field(default_factory=list)
    started_at: float = 0.0
    finished_at: float = 0.0
    current_task: str = ""

    @property
    def success_rate(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.score for r in self.results) / len(self.results)

    @property
    def total_time(self) -> float:
        return sum(r.time_s for r in self.results)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "suite": self.suite,
            "model": self.model,
            "provider": self.provider,
            "device": self.device,
            "status": self.status,
            "success_rate": round(self.success_rate, 3),
            "total_tasks": len(self.results),
            "passed": sum(1 for r in self.results if r.score > 0),
            "total_time_s": round(self.total_time, 1),
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "current_task": self.current_task,
            "results": [asdict(r) for r in self.results],
        }

    def save(self) -> None:
        path = RESULTS_DIR / f"{self.id}.json"
        path.write_text(json.dumps(self.to_dict(), indent=2))


# ── Active runs registry ─────────────────────────────────────────────────

_active_runs: dict[str, BenchmarkRun] = {}


def list_runs() -> list[dict]:
    seen = set()
    runs = []
    for run in _active_runs.values():
        runs.append(run.to_dict())
        seen.add(run.id)
    for f in sorted(RESULTS_DIR.glob("*.json"), reverse=True):
        try:
            data = json.loads(f.read_text())
            if data["id"] not in seen:
                runs.append(data)
        except Exception:
            pass
    return runs


def get_run(run_id: str) -> dict | None:
    if run_id in _active_runs:
        return _active_runs[run_id].to_dict()
    path = RESULTS_DIR / f"{run_id}.json"
    if path.exists():
        return json.loads(path.read_text())
    return None


def stop_run(run_id: str) -> bool:
    if run_id in _active_runs:
        _active_runs[run_id].status = "stopped"
        return True
    return False


# ── Main runner ──────────────────────────────────────────────────────────


def run_benchmark(
    tasks: list[Task],
    model: str,
    device: str,
    provider: str = "ollama",
    suite: str = "ghost_bench",
    api_base: str = "http://localhost:5055",
    run_id: str = "",
) -> BenchmarkRun:
    """Run benchmark tasks sequentially. Blocking — run in a thread."""
    from gitd.benchmarks.ghost_bench.evaluators import (
        evaluate_task,
        initialize_task,
        reset_device,
        teardown_task,
    )

    if not run_id:
        run_id = str(uuid.uuid4())[:8]

    run = BenchmarkRun(
        id=run_id,
        suite=suite,
        model=model,
        provider=provider,
        device=device,
        started_at=time.time(),
    )
    _active_runs[run_id] = run
    _event_queues.setdefault(run_id, [])

    for task in tasks:
        if run.status == "stopped":
            break

        run.current_task = task.id
        t0 = time.time()
        _emit(run_id, {"type": "task_start", "task_id": task.id, "goal": task.goal})

        try:
            reset_device(device)
            time.sleep(1)

            init_desc = initialize_task(task, device)
            _emit(run_id, {"type": "init", "task_id": task.id, "desc": init_desc})
            time.sleep(1)

            agent_log = _run_agent(task, model, device, provider, api_base, run_id)

            time.sleep(1)
            score, reason = evaluate_task(task, device)
            _emit(run_id, {"type": "task_result", "task_id": task.id, "score": score, "reason": reason})

            elapsed = time.time() - t0
            result = TaskResult(
                task_id=task.id,
                goal=task.goal,
                model=model,
                device=device,
                score=score,
                reason=reason,
                steps=len([e for e in agent_log if e.get("type") == "tool_call"]),
                time_s=round(elapsed, 1),
                agent_log=agent_log,
            )
            teardown_task(task, device)

        except Exception as e:
            elapsed = time.time() - t0
            result = TaskResult(
                task_id=task.id,
                goal=task.goal,
                model=model,
                device=device,
                reason=f"error: {e}",
                time_s=round(elapsed, 1),
                error=str(e),
            )
            log.exception("Benchmark task %s failed", task.id)

        run.results.append(result)
        run.save()

    run.status = "completed" if run.status != "stopped" else "stopped"
    run.finished_at = time.time()
    run.current_task = ""
    run.save()
    _emit(run_id, {"type": "run_done", "status": run.status, "success_rate": run.success_rate})
    _active_runs.pop(run_id, None)
    _event_queues.pop(run_id, None)
    return run


def _run_agent(
    task: Task, model: str, device: str, provider: str, api_base: str, run_id: str
) -> list[dict]:
    """Send task goal to agent chat endpoint and collect SSE events."""
    events: list[dict] = []
    try:
        resp = requests.post(
            f"{api_base}/api/agent-chat/message",
            json={"content": task.goal, "device": device, "provider": provider, "model": model},
            timeout=300,
            stream=True,
        )
        for line in resp.iter_lines():
            if not line:
                continue
            text = line.decode()
            if text.startswith("data: "):
                try:
                    ev = json.loads(text[6:])
                    events.append(ev)
                    _emit(run_id, {"type": "agent", "task_id": task.id, **ev})
                except json.JSONDecodeError:
                    pass
    except Exception as e:
        events.append({"type": "error", "content": str(e)})
    return events
