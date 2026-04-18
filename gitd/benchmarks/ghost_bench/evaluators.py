"""Evaluators — run ADB commands to check if a task succeeded."""

import subprocess

from gitd.benchmarks.base import Task


def _adb(serial: str, *args: str, timeout: int = 10) -> str:
    cmd = ["adb", "-s", serial, "shell", *args]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return r.stdout.strip()


def initialize_task(task: Task, serial: str) -> str:
    """Set up preconditions. Returns description of what was done."""
    if not task.init or not task.init.get("cmd"):
        return "no init needed"
    _adb(serial, *task.init["cmd"].split())
    return task.init.get("desc", task.init["cmd"])


def evaluate_task(task: Task, serial: str) -> tuple[float, str]:
    """Check if a task succeeded. Returns (score 0.0-1.0, reason)."""
    ev = task.eval
    if not ev or not ev.get("cmd"):
        return 0.0, "no evaluator defined"

    result = _adb(serial, *ev["cmd"].split())

    if "expect" in ev:
        expected = str(ev["expect"])
        if result == expected:
            return 1.0, f"got '{result}' (expected '{expected}')"
        return 0.0, f"got '{result}' (expected '{expected}')"

    if "expect_in" in ev:
        if result in ev["expect_in"]:
            return 1.0, f"got '{result}' (in {ev['expect_in']})"
        return 0.0, f"got '{result}' (expected one of {ev['expect_in']})"

    if "expect_contains" in ev:
        needle = ev["expect_contains"]
        if needle.lower() in result.lower():
            return 1.0, f"found '{needle}' in output"
        return 0.0, f"'{needle}' not found in output (got: {result[:200]})"

    return 0.0, "unknown evaluator type"


def teardown_task(task: Task, serial: str) -> None:
    if task.teardown and task.teardown.get("cmd"):
        _adb(serial, *task.teardown["cmd"].split())


def reset_device(serial: str) -> None:
    _adb(serial, "input", "keyevent", "KEYCODE_HOME")
    _adb(serial, "input", "keyevent", "KEYCODE_HOME")
