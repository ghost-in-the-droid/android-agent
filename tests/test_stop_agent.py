"""Tests for stop_agent session isolation.

stop_agent used to run a global `pkill -f claude...stream-json` safety net that
matched EVERY claude stream-json process on the box — so stopping session A (or
just A completing normally, since the router calls stop_agent in every stream's
finally) would reap session B mid-tap. The fix relies solely on the per-session
process group (claude is launched start_new_session=True), so a stop stays
scoped to its own session.
"""

import subprocess
import time

from gitd.services import agent_chat
from gitd.services.agent_chat import _active_procs, stop_agent


def _spawn_group():
    """A long-lived process in its own session/process group (like claude)."""
    return subprocess.Popen(["sleep", "30"], start_new_session=True)


def _dead(proc, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            return True
        time.sleep(0.05)
    return proc.poll() is not None


def test_stop_agent_kills_only_target_session():
    target = _spawn_group()  # session A — registered
    sibling = _spawn_group()  # session B — a different live session, NOT stopped
    _active_procs["sess-A"] = target
    try:
        stop_agent("sess-A")
        assert _dead(target), "the target session's process group must be killed"
        # The sibling must still be running — this is the whole bug being fixed.
        time.sleep(0.2)
        assert sibling.poll() is None, "a different session must survive stop_agent(A)"
    finally:
        for p in (target, sibling):
            try:
                p.kill()
            except Exception:
                pass
        _active_procs.pop("sess-A", None)


def test_stop_agent_unknown_session_is_noop():
    """No registered proc (e.g. anthropic/ollama providers) → clean no-op, no sweep."""
    _active_procs.pop("ghost-missing", None)
    stop_agent("ghost-missing")  # must not raise


def test_stop_agent_never_runs_global_pkill(monkeypatch):
    """Regression guard: stop_agent must never shell out to a global pkill."""
    seen = []
    real_run = agent_chat.subprocess.run

    def spy_run(cmd, *a, **k):
        seen.append(cmd)
        return real_run(["true"])

    monkeypatch.setattr(agent_chat.subprocess, "run", spy_run)

    target = _spawn_group()
    _active_procs["sess-guard"] = target
    try:
        stop_agent("sess-guard")
    finally:
        try:
            target.kill()
        except Exception:
            pass
        _active_procs.pop("sess-guard", None)

    assert not any(isinstance(c, list) and c and c[0] == "pkill" for c in seen), (
        "stop_agent must not run a global pkill"
    )
