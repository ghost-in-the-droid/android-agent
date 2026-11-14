#!/usr/bin/env python3
"""AndroidWorld task bridge: a JSON-lines server that owns one task's lifecycle on one emulator.

Runs INSIDE the AndroidWorld container (``android_world`` importable, ``adb`` on PATH, emulator up).
The hub side (``gitd/skills/engine/bench.py``) drives it over stdin/stdout, so the skill engine never
imports AndroidWorld and AndroidWorld never imports the skill engine; the only shared state is the
emulator. stdout carries protocol lines only; everything else goes to stderr.

Usage (inside the container):
    python3 aw_bridge.py --console-port 5554 --grpc-port 8554 [--adb-path adb] [--family android_world]

Protocol: one JSON object per line, one reply per request, in order.
    {"op": "hello"}                               -> {"ok": true, "serial": "emulator-5554", "tasks": [...], "upstream": "<path>"}
    {"op": "init", "task": "<TaskName>", "seed": 30}
        seeds exactly like AndroidWorld's suite_utils (instance_seed = sha256(f"{seed}_{task}_0") mod 2**32,
        random.seed before generate_random_params, params["seed"] stamped), builds the task and calls
        initialize_task(env) with up to 3 retries of the SAME instance.
        -> {"ok": true, "task": ..., "goal": ..., "instance_seed": N, "complexity": x, "params": {...json-safe...}}
    {"op": "score"}                               -> {"ok": true, "is_successful": 1.0}   (float, 1.0 = full credit)
    {"op": "teardown"}                            -> {"ok": true}
    {"op": "reset"}                               -> {"ok": true}   (env.reset(go_home=True))
    {"op": "quit"}                                -> {"ok": true}, then exit 0
Errors: {"ok": false, "error": "<message>"}; the server stays up unless stdin closes.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import logging
import random
import sys
import time

log = logging.getLogger("aw_bridge")


def jsonable(value):
    """AndroidWorld params hold frozen dataclasses (rows); make them plain JSON."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {k: jsonable(v) for k, v in dataclasses.asdict(value).items()}
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def instance_seed_for(task_name: str, seed: int) -> int:
    return int(hashlib.sha256(f"{seed}_{task_name}_0".encode()).hexdigest(), 16) % (2**32)


class Bridge:
    def __init__(self, console_port: int, grpc_port: int, adb_path: str, family: str):
        from android_world import registry  # noqa: WPS433 (container-only import)
        from android_world.env import env_launcher

        self.env = env_launcher.load_and_setup_env(
            console_port=console_port,
            grpc_port=grpc_port,
            emulator_setup=False,
            freeze_datetime=False,
            adb_path=adb_path,
        )
        reg = registry.TaskRegistry()
        self.tasks = reg.get_registry(getattr(reg, family.upper() + "_FAMILY", reg.ANDROID_WORLD_FAMILY))
        self.serial = f"emulator-{console_port}"
        self.task = None
        self.task_name = None

    def hello(self, _req):
        import android_world

        return {"serial": self.serial, "tasks": sorted(self.tasks), "upstream": android_world.__file__}

    def init(self, req):
        name = req["task"]
        if name not in self.tasks:
            raise KeyError(f"unknown task {name!r}")
        if self.task is not None:
            self._teardown_quietly()
        seed = int(req.get("seed", 30))
        inst = instance_seed_for(name, seed)
        random.seed(inst)
        factory = self.tasks[name]
        params = factory.generate_random_params()
        if isinstance(params, dict):
            params["seed"] = inst
        task = factory(params)
        for attempt in range(3):
            try:
                task.initialize_task(self.env)
                break
            except Exception as exc:  # noqa: BLE001 (retry the same instance, never re-roll)
                if attempt == 2:
                    raise
                log.warning("initialize_task failed (%s/3): %s", attempt + 1, exc)
                time.sleep(5)
                try:
                    self.env.reset(go_home=True)
                except Exception:  # noqa: BLE001
                    pass
        self.task, self.task_name = task, name
        return {
            "task": name,
            "goal": task.goal,
            "instance_seed": inst,
            "seed": seed,
            "complexity": getattr(task, "complexity", None),
            "params": jsonable(params),
        }

    def score(self, _req):
        if self.task is None:
            raise RuntimeError("no task initialised")
        return {"is_successful": float(self.task.is_successful(self.env))}

    def teardown(self, _req):
        if self.task is None:
            return {}
        self._teardown_quietly()
        return {}

    def _teardown_quietly(self):
        try:
            self.task.tear_down(self.env)
        except Exception as exc:  # noqa: BLE001
            log.warning("tear_down error: %s", exc)
        self.task, self.task_name = None, None

    def reset(self, _req):
        self.env.reset(go_home=True)
        return {}


def serve(bridge: Bridge, stdin=sys.stdin, stdout=sys.stdout) -> int:
    ops = {
        "hello": bridge.hello,
        "init": bridge.init,
        "score": bridge.score,
        "teardown": bridge.teardown,
        "reset": bridge.reset,
    }
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            op = req.get("op")
            if op == "quit":
                reply = {"ok": True}
                stdout.write(json.dumps(reply) + "\n")
                stdout.flush()
                return 0
            if op not in ops:
                raise KeyError(f"unknown op {op!r}")
            reply = {"ok": True, **ops[op](req)}
        except Exception as exc:  # noqa: BLE001 (every failure becomes a protocol error, never silence)
            log.exception("request failed")
            reply = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        stdout.write(json.dumps(reply) + "\n")
        stdout.flush()
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--console-port", type=int, default=5554)
    ap.add_argument("--grpc-port", type=int, default=8554)
    ap.add_argument("--adb-path", default="adb")
    ap.add_argument("--family", default="android_world")
    args = ap.parse_args(argv)
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="aw_bridge %(levelname)s %(message)s")
    bridge = Bridge(args.console_port, args.grpc_port, args.adb_path, args.family)
    return serve(bridge)


if __name__ == "__main__":
    sys.exit(main())
