"""Tests for screenshot_sequence (#5) — frame-burst capture + caching."""

import pytest

from gitd.services import agent_tools
from gitd.services.agent_tools import SAFE_DEVICE_TOOLS


@pytest.fixture()
def fast(monkeypatch):
    """No real sleeps; deterministic frame source."""
    monkeypatch.setattr("time.sleep", lambda _s: None)
    agent_tools._SEQ_FRAMES.clear()


def test_captures_n_frames_and_caches(fast, monkeypatch):
    calls = {"n": 0}

    def fake_shot(device):
        calls["n"] += 1
        return f"frame{calls['n']}"

    monkeypatch.setattr(agent_tools, "get_screenshot_b64", fake_shot)
    out = agent_tools._capture_sequence("dev", {"duration_seconds": 4, "fps": 1.0})
    # 4s @ 1fps → 4 frames
    assert agent_tools._SEQ_FRAMES["dev"] == ["frame1", "frame2", "frame3", "frame4"]
    assert "captured 4 frames" in out and "cached for sub_agent" in out


def test_fps_and_duration_clamped(fast, monkeypatch):
    monkeypatch.setattr(agent_tools, "get_screenshot_b64", lambda d: "f")
    # fps clamped to 4.0, duration min 2 → 2*4 = 8 frames
    agent_tools._capture_sequence("dev", {"duration_seconds": 1, "fps": 99})
    assert len(agent_tools._SEQ_FRAMES["dev"]) == 8


def test_skips_none_frames(fast, monkeypatch):
    seq = iter(["a", None, "b"])
    monkeypatch.setattr(agent_tools, "get_screenshot_b64", lambda d: next(seq, None))
    agent_tools._capture_sequence("dev", {"duration_seconds": 3, "fps": 1.0})
    assert agent_tools._SEQ_FRAMES["dev"] == ["a", "b"]  # the None dropped


def test_screenshot_sequence_is_safe_and_chainable():
    # SAFE → an agent can chain it (chain gates sub-actions to SAFE_DEVICE_TOOLS)
    assert "screenshot_sequence" in SAFE_DEVICE_TOOLS


def test_dispatch_routes_to_capture(fast, monkeypatch):
    monkeypatch.setattr(agent_tools, "get_screenshot_b64", lambda d: "f")
    out = agent_tools._execute_tool_inner("screenshot_sequence", {"device": "dev", "duration_seconds": 2, "fps": 1.0})
    assert "captured 2 frames" in out
    assert agent_tools._SEQ_FRAMES["dev"] == ["f", "f"]
