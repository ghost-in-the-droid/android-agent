"""AndroidWorld before/after bench, replay arm.

The replay arm answers one question per task and seed: does the hub skill, replayed deterministically
by this engine with zero model calls, satisfy AndroidWorld's own ``task.is_successful``? The task
lifecycle (seeded params, ``initialize_task``, scoring, ``tear_down``) stays inside AndroidWorld behind
``tools/bench/aw_bridge.py``; this module only talks JSON lines to that bridge and drives the skill
against the same emulator over adb. Hub points never come from the AndroidWorld score: every replay
writes an ordinary signed run artifact (``runs/`` or ``verifications/``) with a nested ``bench`` block,
and the per-skill ``bench/androidworld.json`` summary is display only.
"""

from __future__ import annotations

import json
import shlex
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .androidworld import action_name as aw_action_name
from .loader import SkillDef
from .runner import run_action

SUITE = "androidworld"
ARM_REPLAY = "after_replay"  # web2's card reads before / after_replay / after_mcp
PROTOCOL_DOC = "docs/benchmark-protocol.md"
REPLAY_PRINCIPAL = (
    "ghost-aw-replay"  # platform principal in skillhub/verifier-keys.yml; its verifications count as independent
)


class BridgeError(RuntimeError):
    """The bridge refused a request or went away; the seed is scored as an error, never as a pass."""


class AWBridge:
    """Client for ``tools/bench/aw_bridge.py`` over a subprocess (``docker exec -i``, ``ssh``, or local)."""

    def __init__(self, command: list[str], timeout_s: float = 600.0):
        self.command = list(command)
        self.timeout_s = timeout_s
        self.proc: subprocess.Popen | None = None

    def __enter__(self):
        self.proc = subprocess.Popen(self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
        return self

    def __exit__(self, *_exc):
        self.close()

    def request(self, op: str, **fields) -> dict:
        if self.proc is None or self.proc.poll() is not None:
            raise BridgeError("bridge is not running")
        self.proc.stdin.write(json.dumps({"op": op, **fields}) + "\n")
        self.proc.stdin.flush()
        deadline = time.monotonic() + self.timeout_s
        while True:
            if time.monotonic() > deadline:
                raise BridgeError(f"bridge timed out on {op}")
            line = self.proc.stdout.readline()
            if not line:
                raise BridgeError(f"bridge closed its stdout during {op}")
            line = line.strip()
            if not line.startswith("{"):
                continue  # stray non-protocol output; the bridge logs to stderr but be lenient
            reply = json.loads(line)
            if not reply.get("ok"):
                raise BridgeError(reply.get("error") or f"bridge rejected {op}")
            return reply

    def close(self):
        if self.proc is None:
            return
        try:
            if self.proc.poll() is None:
                self.proc.stdin.write(json.dumps({"op": "quit"}) + "\n")
                self.proc.stdin.flush()
                self.proc.wait(timeout=20)
        except (OSError, subprocess.TimeoutExpired):
            self.proc.kill()
        finally:
            self.proc = None


# ── AndroidWorld params -> skill params ──────────────────────────────────────
# AndroidWorld hands a task its generated instance (rows, names, dates); the skill takes typed params.
# Adapters are keyed by task name and hold the ONLY task-specific knowledge in this module.

ParamAdapter = Callable[[dict], dict]
_ADAPTERS: dict[str, ParamAdapter] = {}


def adapter(*tasks: str):
    def register(fn: ParamAdapter) -> ParamAdapter:
        for task in tasks:
            _ADAPTERS[task] = fn
        return fn

    return register


def expense_rows(rows: list[dict]) -> list[dict]:
    """AndroidWorld Expense rows (amount in cents, category id) -> what a person reads in the app."""
    from .androidworld import EXPENSE_CATEGORIES

    out = []
    for row in rows:
        amount = int(row["amount"])
        out.append(
            {
                "name": row["name"],
                "amount": f"{amount / 100:.2f}",
                "category": EXPENSE_CATEGORIES.get(int(row.get("category", 0)), "Others"),
                "note": row.get("note") or "",
            }
        )
    return out


@adapter("ExpenseAddSingle", "ExpenseAddMultiple")
def _expense_add(params: dict) -> dict:
    return {"rows": expense_rows(params["row_objects"])}


@adapter("ExpenseAddMultipleFromMarkor", "ExpenseAddMultipleFromGallery")
def _expense_add_from_source(_params: dict) -> dict:
    return {}  # the skill reads the source (Markor file, gallery image) itself; nothing is handed over


@adapter("ExpenseDeleteSingle", "ExpenseDeleteMultiple", "ExpenseDeleteMultiple2")
def _expense_delete(params: dict) -> dict:
    return {"names": [row["name"] for row in params["row_objects"]]}


@adapter("ExpenseDeleteDuplicates", "ExpenseDeleteDuplicates2")
def _expense_dedupe(_params: dict) -> dict:
    return {}


def skill_params(task: str, aw_params: dict, action_params: list[str]) -> dict:
    """Adapter when one is registered, else pass through the scalar params the action declares."""
    if task in _ADAPTERS:
        return _ADAPTERS[task](aw_params)
    return {k: v for k, v in aw_params.items() if k in action_params and isinstance(v, (str, int, float, bool))}


def force_stop(device: str, package: str | None) -> None:
    """Best-effort `am force-stop` on a real device; fake devices and iOS refs are left alone."""
    if not package or not device or device.startswith(("fake:", "ios:")):
        return
    try:
        subprocess.run(
            ["adb", "-s", device, "shell", "am", "force-stop", package],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        pass


def screen_summary(device: str) -> dict:
    """What the phone showed when a replay failed: focused window plus the ids and texts on screen."""
    if not device or device.startswith(("fake:", "ios:")):
        return {}
    import re

    try:
        from gitd.bots.common.adb import Device

        from .dispatch import _fast_dump

        dev = Device(device)
        xml = _fast_dump(dev)
        focus = dev.adb_soft("shell", "dumpsys window | grep -m1 mCurrentFocus").stdout.strip()[-120:]
        ids = sorted({m.group(1).split("/")[-1] for m in re.finditer(r'resource-id="([^"]+)"', xml)})[:40]
        texts = [m.group(1)[:40] for m in re.finditer(r' text="([^"]+)"', xml)][:15]
        return {"focus": focus, "ids": ids, "texts": texts}
    except Exception as exc:  # noqa: BLE001 (diagnostics must never fail a cell)
        return {"error": str(exc)}


# ── one replay cell ───────────────────────────────────────────────────────────


def replay_task(
    skill: SkillDef,
    task: str,
    *,
    seeds: list[int],
    device: str,
    bridge: AWBridge,
    action: str | None = None,
    record: bool = True,
    login: str | None = None,
    artifact_dir: Path | None = None,
    progress=print,
) -> list[dict]:
    """Replay ``skill``'s action for ``task`` once per seed; return one result dict per seed."""
    action = action or aw_action_name(task)
    action_def = skill.action(action)
    declared = [p.name for p in action_def.params]
    fingerprint = None
    if record:
        from .evidence import collect_fingerprint

        fingerprint = collect_fingerprint(skill, device)
    results = []
    for seed in seeds:
        cell = {"suite": SUITE, "task_id": task, "arm": ARM_REPLAY, "seed": seed, "action": action}
        started = time.monotonic()
        # AndroidWorld's initialize_task replaces the app's database file; an app process that is still
        # alive keeps the old inode and later overwrites the seeded rows, so the app is stopped first and
        # again after the replay so the scorer reads a settled database.
        force_stop(device, skill.fingerprint.app_package)
        try:
            init = bridge.request("init", task=task, seed=seed)
            cell["instance_seed"] = init.get("instance_seed")
            cell["goal"] = init.get("goal")
            params = skill_params(task, init.get("params") or {}, declared)
            cell["params"] = params
            result = run_action(skill, action, params=params, device_serial=device)
            cell["skill_success"] = bool(result.success)
            cell["skill_error"] = result.error
            cell["steps"] = len(result.trace)
            if not result.success:
                cell["screen_at_failure"] = screen_summary(device)
            force_stop(device, skill.fingerprint.app_package)
            score = bridge.request("score")
            cell["is_successful"] = float(score["is_successful"])
            cell["success"] = cell["is_successful"] == 1.0
        except BridgeError as exc:
            cell.update({"success": False, "is_successful": 0.0, "error": f"bridge: {exc}"})
            result = None
        finally:
            try:
                bridge.request("teardown")
            except BridgeError as exc:
                cell.setdefault("error", f"teardown: {exc}")
        cell["wall_ms"] = int((time.monotonic() - started) * 1000)
        cell["tokens"] = 0
        if record and result is not None:
            from .evidence import write_evidence

            bench = {
                k: cell[k]
                for k in (
                    "suite",
                    "task_id",
                    "arm",
                    "seed",
                    "instance_seed",
                    "steps",
                    "tokens",
                    "wall_ms",
                    "is_successful",
                )
                if k in cell
            }
            # The signed artifact's success is the AndroidWorld verdict, never the skill's own validator.
            result.success = cell["success"]
            cell["artifact"] = str(
                write_evidence(
                    skill,
                    [result],
                    fingerprint,
                    login=login,
                    artifact_dir=artifact_dir,
                    simulated=device.startswith("fake:"),
                    bench=bench,
                    emulator=True,  # AndroidWorld always runs on its emulator image
                )
            )
        progress(
            f"{task} seed={seed} skill={'ok' if cell.get('skill_success') else 'fail'} "
            f"androidworld={'PASS' if cell['success'] else 'FAIL'} {cell['wall_ms']} ms"
        )
        results.append(cell)
    return results


def _median(values: list[int]) -> int:
    ordered = sorted(values)
    mid = len(ordered) // 2
    return int(ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2)


def write_summary(skill: SkillDef, results: list[dict], *, upstream_commit: str | None = None) -> Path:
    """Merge results into ``<skill>/bench/androidworld.json``, the display-only card the hub page renders.

    Shape agreed with the site (BenchCard): ``tasks`` is a list, arms are ``before`` / ``after_replay`` /
    ``after_mcp`` with ``passed``, ``total``, ``wall_ms_median``, ``tokens_median``. A seed counts once per
    task and arm; rerunning a seed replaces nothing and adds nothing.
    """
    path = skill.skill_dir / "bench" / f"{SUITE}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {"suite": SUITE, "skill": f"{skill.author}/{skill.name}", "protocol": PROTOCOL_DOC, "tasks": []}
    if path.exists():
        try:
            loaded = json.loads(path.read_text())
            if isinstance(loaded.get("tasks"), list):
                doc = loaded
        except ValueError:
            pass
    if upstream_commit:
        doc["upstream_commit"] = upstream_commit
    by_task = {t["task_id"]: t for t in doc["tasks"]}
    for cell in results:
        task = by_task.get(cell["task_id"])
        if task is None:
            task = {"task_id": cell["task_id"], "action": cell.get("action"), "seeds": 0, "arms": {}}
            by_task[cell["task_id"]] = task
            doc["tasks"].append(task)
        arm = task["arms"].setdefault(
            cell["arm"],
            {
                "passed": 0,
                "total": 0,
                "wall_ms_median": 0,
                "tokens_median": 0,
                "seeds_run": [],
                "wall_ms": [],
                "tokens": [],
                "artifacts": [],
            },
        )
        if cell["seed"] in arm["seeds_run"]:
            continue
        arm["seeds_run"].append(cell["seed"])
        arm["total"] += 1
        arm["passed"] += int(bool(cell["success"]))
        arm["wall_ms"].append(int(cell.get("wall_ms", 0)))
        arm["tokens"].append(int(cell.get("tokens", 0)))
        arm["wall_ms_median"] = _median(arm["wall_ms"])
        arm["tokens_median"] = _median(arm["tokens"])
        if cell.get("artifact"):
            arm["artifacts"].append(Path(cell["artifact"]).name)
        task["seeds"] = max(task["seeds"], arm["total"])
    doc["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    path.write_text(json.dumps(doc, indent=2) + "\n")
    return path


def bridge_command(spec: str) -> list[str]:
    return shlex.split(spec)
