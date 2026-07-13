"""Tests for the `chain` action — batched sub-actions with a settle between."""

import pytest

from gitd.services import agent_tools
from gitd.services.agent_tools import EXEC_CAPABLE_TOOLS, SAFE_DEVICE_TOOLS, execute_tool


@pytest.fixture()
def record_dispatch(monkeypatch):
    """Capture every _execute_tool_inner sub-call and stub them out."""
    calls = []

    real_inner = agent_tools._execute_tool_inner

    def fake_inner(name, args):
        # chain itself must still go through the real dispatch → _execute_chain
        if name == "chain":
            return real_inner(name, args)
        calls.append((name, dict(args)))
        return f"ran {name}"

    monkeypatch.setattr(agent_tools, "_execute_tool_inner", fake_inner)
    # no real sleeps
    monkeypatch.setattr("time.sleep", lambda _s: None)
    return calls


def test_chain_runs_sub_actions_in_order(record_dispatch):
    out = execute_tool(
        "chain",
        {
            "device": "emulator-5554",
            "actions": [
                {"tool": "tap_element", "args": {"idx": 3}},
                {"tool": "type_text", "args": {"text": "hello"}},
                {"tool": "tap_element", "args": {"idx": 7}},
            ],
        },
    )
    assert [c[0] for c in record_dispatch] == ["tap_element", "type_text", "tap_element"]
    # device propagated into every sub-action
    assert all(c[1].get("device") == "emulator-5554" for c in record_dispatch)
    assert out.startswith("chain[3/3]:")


def test_chain_rejects_exec_tool_before_running_anything(record_dispatch):
    out = execute_tool(
        "chain",
        {
            "device": "d",
            "actions": [
                {"tool": "tap", "args": {"x": 1, "y": 2}},
                {"tool": "shell", "args": {"command": "rm -rf /"}},  # not allowed
            ],
        },
    )
    assert "not allowed inside a chain" in out
    assert record_dispatch == []  # fail-closed: nothing ran, incl. the benign first step


def test_chain_refuses_to_nest(record_dispatch):
    out = execute_tool(
        "chain",
        {"device": "d", "actions": [{"tool": "chain", "args": {"actions": []}}]},
    )
    assert "may not nest another chain" in out
    assert record_dispatch == []


def test_chain_rejects_oversized_batch(record_dispatch):
    out = execute_tool(
        "chain",
        {"device": "d", "actions": [{"tool": "tap", "args": {"x": 0, "y": 0}}] * 20},
    )
    assert "too many actions" in out
    assert record_dispatch == []


def test_chain_empty_or_bad_shape(record_dispatch):
    assert "non-empty list" in execute_tool("chain", {"device": "d", "actions": []})
    assert "non-empty list" in execute_tool("chain", {"device": "d"})
    assert "'tool' field" in execute_tool("chain", {"device": "d", "actions": [{"args": {}}]})


def test_chain_aborts_remaining_on_hard_failure(monkeypatch):
    calls = []

    def fake_inner(name, args):
        if name == "chain":
            return agent_tools._execute_chain(args.get("device", ""), args)
        calls.append(name)
        if name == "type_text":
            raise RuntimeError("focus lost")
        return f"ran {name}"

    monkeypatch.setattr(agent_tools, "_execute_tool_inner", fake_inner)
    monkeypatch.setattr("time.sleep", lambda _s: None)

    out = agent_tools._execute_chain(
        "d",
        {
            "actions": [
                {"tool": "tap", "args": {}},
                {"tool": "type_text", "args": {}},
                {"tool": "tap_element", "args": {}},  # should NOT run
            ]
        },
    )
    assert calls == ["tap", "type_text"]  # third never ran
    assert "err:focus lost" in out
    assert out.startswith("chain[2/3]:")


def test_chain_soft_continues_on_error_string_return(monkeypatch):
    """A sub-action that RETURNS an error string (not raises) must not abort.

    iOS `speak_text` on stock (un-patched) WDA no-ops and returns an
    ``ERROR: ...`` string rather than raising — a chain that announces status
    should log it and keep going, not fail the whole flow. Only a raised
    exception is a hard failure (see test_chain_aborts_remaining_on_hard_failure).
    """
    calls = []

    def fake_inner(name, args):
        if name == "chain":
            return agent_tools._execute_chain(args.get("device", ""), args)
        calls.append(name)
        if name == "speak_text":
            return "ERROR: speak_text requires the GhostAgent-patched WDA /wda/speak route"
        return f"ran {name}"

    monkeypatch.setattr(agent_tools, "_execute_tool_inner", fake_inner)
    monkeypatch.setattr("time.sleep", lambda _s: None)

    out = agent_tools._execute_chain(
        "d",
        {
            "actions": [
                {"tool": "tap", "args": {}},
                {"tool": "speak_text", "args": {"text": "done"}},  # soft-fails on iOS
                {"tool": "tap_element", "args": {"idx": 1}},  # MUST still run
            ]
        },
    )
    assert calls == ["tap", "speak_text", "tap_element"]  # all three ran
    assert out.startswith("chain[3/3]:")
    assert "ERROR: speak_text" in out


def test_chain_is_exec_capable_not_safe():
    # chain is a meta-executor: must be denied from run_flow / framework adapters
    # (fail-closed) exactly like the other exec vectors.
    assert "chain" in EXEC_CAPABLE_TOOLS
    assert "chain" not in SAFE_DEVICE_TOOLS


def test_chain_not_reachable_via_run_flow():
    """run_flow gates on SAFE_DEVICE_TOOLS; chain must not be in it."""
    from gitd.mcp_server import FLOW_ALLOWED_TOOLS

    assert "chain" not in FLOW_ALLOWED_TOOLS
