"""Process-local agent package policy (an accident guard, not an OS sandbox)."""
from __future__ import annotations

import inspect
import os
import re
import subprocess
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps


class PackagePolicyError(RuntimeError):
    """A denied package or an unverifiable foreground stopped this call."""


def denied_packages() -> frozenset[str]:
    return frozenset(p.strip() for p in os.environ.get("GHOST_DENY_PACKAGES", "").split(",") if p.strip())


@dataclass
class _Call:
    error: PackagePolicyError | None = None


_call: ContextVar[_Call | None] = ContextVar("ghost_package_call", default=None)


def _raise(message: str) -> None:
    error = PackagePolicyError(message)
    state = _call.get()
    if state is not None:
        state.error = state.error or error
        error = state.error
    raise error


def require_package(package: str) -> None:
    state = _call.get()
    if state and state.error:
        raise state.error
    package = package.strip().split("/", 1)[0]
    if package in denied_packages():
        _raise(f"GHOST_DENY_PACKAGES: refusing denied package {package}")


def _raw(device: str, *args: str):
    return subprocess.run(["adb", "-s", device, *args], capture_output=True, text=True, timeout=5)


def _foreground(device: str) -> str:
    if device.startswith("ios:"):
        from gitd.bots.common.device import get_device
        active = get_device(device)._execute_mobile("mobile: activeAppInfo", {})
        return str(active.get("bundleId") or active.get("bundle_id") or "")
    from gitd.bots.common.adb import Device
    return Device(device).foreground_package()


# Backoff between foreground observations while the owner is unknown (sum ~1.5 s).
_FOREGROUND_RETRY_DELAYS = (0.1, 0.2, 0.3, 0.4, 0.5)


def check_foreground(device: str) -> None:
    if not denied_packages() or not device:
        return
    state = _call.get()
    if state and state.error:
        raise state.error
    package = ""
    last_error = None
    # Window/activity owners can be null (or the probe can hiccup) for a while during an allowed
    # transition on slow devices; retry with backoff (~1.5 s total). A denied owner is handled at once.
    delays = _FOREGROUND_RETRY_DELAYS
    for attempt in range(len(delays) + 1):
        try:
            package = _foreground(device)
            last_error = None
        except Exception as exc:
            package, last_error = "", exc
        if package:
            break
        if attempt < len(delays):
            time.sleep(delays[attempt])
    if not package:
        detail = f": {last_error}" if last_error else ""
        _raise(f"GHOST_DENY_PACKAGES: cannot verify foreground on {device}{detail}; action refused")
    if package in denied_packages():
        # Latch BEFORE recovery: nested handlers must not swallow this and continue.
        message = f"GHOST_DENY_PACKAGES: denied foreground package {package}; sent HOME once; action stopped"
        if state is not None:
            state.error = PackagePolicyError(message)
        try:
            if device.startswith("ios:"):
                from gitd.bots.common.device import get_device
                get_device(device).press_key("HOME", delay=0)
            else:
                result = _raw(device, "shell", "input", "keyevent", "KEYCODE_HOME")
                if result.returncode:
                    raise RuntimeError(result.stderr or "HOME failed")
        except Exception as exc:
            message = f"GHOST_DENY_PACKAGES: denied foreground package {package}; HOME attempted once but failed: {exc}; action stopped"
            if state is not None:
                state.error = PackagePolicyError(message)
        _raise(message)


@contextmanager
def package_session(device: str, *, settle: bool = False):
    if not denied_packages():
        yield
        return
    token = _call.set(_Call()) if _call.get() is None else None
    try:
        check_foreground(device)
        try:
            yield
        finally:
            if settle and device:
                time.sleep(0.25)
            check_foreground(device)
    finally:
        if token is not None:
            _call.reset(token)


def check_tool_target(name: str, args: dict) -> None:
    if name in {"launch_app", "launch_intent", "open_url", "web_search"}:
        for key in ("package", "component", "bundle_id", "browser"):
            if args.get(key):
                require_package(args[key])


# `am start` switches that `cmd package resolve-activity` does not understand
# (its parser only accepts intent arguments). Anything else is passed through.
_AM_ONLY_FLAGS = {"-W", "-S", "-D", "-N", "--streaming", "--suspend", "--track-allocation", "--splashscreen-icon"}
_AM_ONLY_FLAGS_WITH_VALUE = {
    "-R", "-P", "--start-profiler", "--sampling", "--attach-agent", "--attach-agent-bind",
    "--windowingMode", "--activityType", "--display", "--task",
}


def _intent_options(options: list[str]) -> list[str]:
    kept: list[str] = []
    skip = False
    for value in options:
        if skip:
            skip = False
        elif value in _AM_ONLY_FLAGS_WITH_VALUE:
            skip = True
        elif value not in _AM_ONLY_FLAGS:
            kept.append(value)
    return kept


def guard_device_command(device: str, args, run):
    """Guard mutating Android commands, including commands inside Python skills.

    `run` bypasses policy for intent resolution, avoiding recursive ADB calls.
    Unknown/raw shell is still checked at the surrounding tool/skill boundary.
    """
    import shlex

    words = [str(a) for a in args]
    if not denied_packages() or not words or words[0] != "shell":
        return run(args)
    # Skill intent arguments are individually shell quoted. Raw text that is
    # not shell-quoted (the per-character `input text` fallbacks) may hold an
    # unbalanced quote; keep the tokens as given rather than crash the call.
    try:
        words = shlex.split(" ".join(words[1:]))
    except ValueError:
        words = words[1:]
    is_start = words[:2] in (["am", "start"], ["am", "start-activity"]) or words[:3] == ["cmd", "activity", "start-activity"]
    if not (is_start or words[:1] in (["input"], ["monkey"])):
        return run(args)
    with package_session(device):
        if is_start or words[:1] == ["monkey"]:
            for flag in ("-p", "-n", "--component"):
                if flag in words and words.index(flag) + 1 < len(words):
                    require_package(words[words.index(flag) + 1])
        if is_start:
            options = _intent_options(words[2:] if words[0] == "am" else words[3:])
            resolved = run(("shell", "cmd", "package", "resolve-activity", "--brief", *[shlex.quote(v) for v in options]))
            component = re.search(r"(?m)^([\w.]+)/[^\s]+$", resolved.stdout.strip())
            if resolved.returncode or component is None:
                _raise("GHOST_DENY_PACKAGES: cannot resolve intent target; launch refused")
            require_package(component[1])
        return run(args)


def tool_device(name: str, args: dict) -> str:
    device = args.get("device", "")
    if not device and name in {"run_skill", "run_skill_resume", "wait"}:
        device = os.environ.get("GHOST_DEVICE", "").strip() or os.environ.get("ANDROID_SERIAL", "").strip()
    return device


def guard_mcp_function(fn):
    """Keep tool schemas/signatures intact while guarding direct MCP handlers."""
    signature = inspect.signature(fn)

    @wraps(fn)
    def guarded(*args, **kwargs):
        if not denied_packages():
            return fn(*args, **kwargs)
        values = signature.bind(*args, **kwargs).arguments
        device = tool_device(fn.__name__, values)
        try:
            with package_session(device, settle=True):
                check_tool_target(fn.__name__, values)
                return fn(*args, **kwargs)
        except PackagePolicyError as exc:
            return f"Error: {exc}"

    return guarded
