"""Tests for the vision sub-agent (#4) + its agent-tool wiring."""

import pytest

from gitd.services import agent_tools, sub_agent
from gitd.services.agent_tools import EXEC_CAPABLE_TOOLS, SAFE_DEVICE_TOOLS
from gitd.services.sub_agent import MAX_SUB_AGENT_FRAMES, _subsample, run_sub_agent


@pytest.fixture()
def with_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")


def test_missing_task_returns_error():
    assert "missing 'task'" in run_sub_agent("", ["frame"])
    assert "missing 'task'" in run_sub_agent("   ", ["frame"])


def test_no_frames_returns_hint():
    assert "no frames available" in run_sub_agent("read it", [])


def test_no_api_key_degrades_gracefully(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out = run_sub_agent("read it", ["frame1"])
    assert "unavailable" in out and "ANTHROPIC_API_KEY" in out


def test_happy_path_calls_vision_and_returns_text(with_key, monkeypatch):
    captured = {}

    def fake_call(system, content, model):
        captured["system"] = system
        captured["content"] = content
        captured["model"] = model
        return "milk, eggs, bread"

    monkeypatch.setattr(sub_agent, "_anthropic_vision_call", fake_call)
    out = run_sub_agent("transcribe the list", ["f1", "f2"], model="claude-sonnet-5")
    assert out == "milk, eggs, bread"
    # content = 2 (text+image) per frame + 1 task text
    assert len(captured["content"]) == 2 * 2 + 1
    assert captured["content"][-1] == {"type": "text", "text": "transcribe the list"}
    imgs = [c for c in captured["content"] if c.get("type") == "image"]
    assert all(c["source"]["media_type"] == "image/jpeg" for c in imgs)
    assert captured["model"] == "claude-sonnet-5"


def test_api_error_is_caught_not_raised(with_key, monkeypatch):
    def boom(system, content, model):
        raise RuntimeError("429 overloaded")

    monkeypatch.setattr(sub_agent, "_anthropic_vision_call", boom)
    out = run_sub_agent("x", ["f1"])
    assert out.startswith("sub_agent error:") and "429" in out


def test_frames_subsampled_to_cap(with_key, monkeypatch):
    seen = {}
    monkeypatch.setattr(
        sub_agent,
        "_anthropic_vision_call",
        lambda s, content, m: seen.setdefault("imgs", sum(1 for c in content if c.get("type") == "image")) or "ok",
    )
    run_sub_agent("x", [f"frame{i}" for i in range(200)], max_frames=10)
    assert seen["imgs"] == 10


def test_subsample_never_exceeds_hard_cap():
    out = _subsample([f"f{i}" for i in range(500)], max_frames=999)
    assert len(out) == MAX_SUB_AGENT_FRAMES
    # order preserved
    assert out == sorted(out, key=lambda s: int(s[1:]))


def test_subsample_returns_all_when_under_cap():
    assert _subsample(["a", "b", "c"], 60) == ["a", "b", "c"]


# ── agent-tool wiring ────────────────────────────────────────────────────────


def test_sub_agent_is_exec_capable_not_safe():
    assert "sub_agent" in EXEC_CAPABLE_TOOLS
    assert "sub_agent" not in SAFE_DEVICE_TOOLS


def test_tool_reads_cached_frames_and_labels_result(with_key, monkeypatch):
    agent_tools._SEQ_FRAMES.clear()
    agent_tools._SEQ_FRAMES["dev"] = ["f1", "f2", "f3"]
    monkeypatch.setattr("gitd.services.sub_agent._anthropic_vision_call", lambda s, c, m: "answer text")
    out = agent_tools._run_sub_agent_tool("dev", {"task": "read"})
    assert out == "SUB_AGENT RESULT (3 frames): answer text"


def test_tool_no_frames_returns_hint(with_key):
    agent_tools._SEQ_FRAMES.clear()
    out = agent_tools._run_sub_agent_tool("dev", {"task": "read"})
    assert "no frames available" in out
