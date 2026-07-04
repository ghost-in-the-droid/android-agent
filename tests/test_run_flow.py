"""Tests for the batch-flow MCP primitive (_run_flow / run_flow).

Covers the happy path (ordered execution, one final screenshot), the fail-fast
error behaviour, and — most importantly — the injection guard: a flow that
names a blocked tool is refused as a whole, executing NOTHING.
"""

import json

import gitd.services.agent_tools as agent_tools
from gitd.mcp_server import FLOW_BLOCKED_ACTIONS, MAX_FLOW_STEPS, _run_flow, run_flow


def _patch(monkeypatch, calls, *, raise_on=None, screenshot="IMGB64"):
    def fake_execute_tool(name, args):
        calls.append((name, dict(args)))
        if raise_on and name == raise_on:
            raise RuntimeError("adb ... failed (exit 1): device not found")
        return f"{name}-ok"

    shots = {"n": 0}

    def fake_shot(device):
        shots["n"] += 1
        return screenshot

    monkeypatch.setattr(agent_tools, "execute_tool", fake_execute_tool)
    monkeypatch.setattr(agent_tools, "get_screenshot_b64", fake_shot)
    return shots


def test_run_flow_executes_steps_in_order_with_one_screenshot(monkeypatch):
    calls = []
    shots = _patch(monkeypatch, calls)
    steps = [
        {"tool": "launch_app", "args": {"package": "com.x"}},
        {"tool": "tap", "args": {"x": 5, "y": 6}},
        {"tool": "type_text", "args": {"text": "hi"}},
    ]
    out = _run_flow("SER1", steps)

    assert [c[0] for c in calls] == ["launch_app", "tap", "type_text"]
    # device is injected into every step
    assert all(c[1]["device"] == "SER1" for c in calls)
    assert out["steps_run"] == 3 and out["stopped_early"] is False
    assert all(r["ok"] for r in out["results"])
    # exactly ONE final screenshot for the whole batch
    assert shots["n"] == 1
    assert out["final_screenshot"] == "IMGB64"


def test_run_flow_blocks_dangerous_tool_and_runs_nothing(monkeypatch):
    calls = []
    _patch(monkeypatch, calls)
    # A benign step FIRST, then a smuggled `shell` — the whole flow must be
    # refused before the benign step runs.
    steps = [
        {"tool": "tap", "args": {"x": 1, "y": 2}},
        {"tool": "shell", "args": {"command": "rm -rf /sdcard"}},
    ]
    out = _run_flow("SER1", steps)

    assert out.get("blocked") == "shell"
    assert "blocked" in out["error"]
    assert calls == [], "no step may execute when the flow contains a blocked tool"


def test_run_flow_blocklist_covers_all_injection_vectors():
    assert {"shell", "run_skill", "create_skill", "launch_intent"} <= set(FLOW_BLOCKED_ACTIONS)


def test_run_flow_aborts_on_first_error(monkeypatch):
    calls = []
    _patch(monkeypatch, calls, raise_on="tap")
    steps = [
        {"tool": "launch_app", "args": {"package": "com.x"}},
        {"tool": "tap", "args": {"x": 5, "y": 6}},  # raises
        {"tool": "type_text", "args": {"text": "never runs"}},
    ]
    out = _run_flow("SER1", steps)

    assert [c[0] for c in calls] == ["launch_app", "tap"]  # third step not reached
    assert out["stopped_early"] is True
    assert out["results"][-1]["ok"] is False
    assert "device not found" in out["results"][-1]["error"]


def test_run_flow_rejects_bad_shapes(monkeypatch):
    _patch(monkeypatch, [])
    assert "list" in _run_flow("S", {"not": "a list"})["error"]
    assert "empty" in _run_flow("S", [])["error"]
    assert "too many" in _run_flow("S", [{"tool": "tap"}] * (MAX_FLOW_STEPS + 1))["error"]
    assert "'tool'" in _run_flow("S", [{"args": {}}])["error"]


def test_run_flow_wrapper_parses_json_and_reports_bad_json(monkeypatch):
    calls = []
    _patch(monkeypatch, calls)
    # good JSON → executes
    res = json.loads(run_flow("SER1", '[{"tool":"tap","args":{"x":1,"y":2}}]'))
    assert res["steps_run"] == 1 and calls[0][0] == "tap"
    # bad JSON → clean error, no crash
    err = json.loads(run_flow("SER1", "{not json"))
    assert "valid JSON" in err["error"]
