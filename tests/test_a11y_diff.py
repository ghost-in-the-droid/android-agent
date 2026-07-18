"""Tests for differential a11y state (#6) — the pure diff + execute_tool wiring."""

import pytest

from gitd.services import agent_tools
from gitd.services.a11y_diff import diff_elements, element_key, element_label


def _el(idx, text="", cls="Button", cx=100, cy=200, desc=""):
    return {
        "idx": idx,
        "text": text,
        "content_desc": desc,
        "resource_id": "",
        "class": cls,
        "bounds": {"x1": cx - 10, "y1": cy - 10, "x2": cx + 10, "y2": cy + 10},
        "center": {"x": cx, "y": cy},
        "clickable": True,
        "scrollable": False,
    }


# ── pure function ────────────────────────────────────────────────────────────


def test_no_prev_returns_empty():
    assert diff_elements(None, [_el(0, "A")]) == ""
    assert diff_elements([], [_el(0, "A")]) == ""


def test_identical_states_report_no_change():
    a = [_el(0, "Send"), _el(1, "Cancel")]
    b = [_el(0, "Send"), _el(1, "Cancel")]
    assert diff_elements(a, b) == "A11y diff: no change."


def test_added_element():
    prev = [_el(0, "Send")]
    curr = [_el(0, "Send"), _el(1, "Undo", cx=300)]
    out = diff_elements(prev, curr)
    assert "+ 'Undo' (Button)" in out
    assert "since last action" in out
    assert "- '" not in out  # nothing removed


def test_removed_element():
    prev = [_el(0, "Send"), _el(1, "Draft", cx=300)]
    curr = [_el(0, "Send")]
    out = diff_elements(prev, curr)
    assert "- 'Draft' (Button)" in out
    assert "+ '" not in out


def test_key_is_robust_to_small_coordinate_jitter():
    # same element, center shifted by a few px → same coarse key → no change
    prev = [_el(0, "Ok", cx=100, cy=200)]
    curr = [_el(0, "Ok", cx=108, cy=205)]
    assert element_key(prev[0]) == element_key(curr[0])
    assert diff_elements(prev, curr) == "A11y diff: no change."


def test_large_move_counts_as_change():
    prev = [_el(0, "Ok", cx=100, cy=200)]
    curr = [_el(0, "Ok", cx=100, cy=900)]
    out = diff_elements(prev, curr)
    assert "+ 'Ok'" in out and "- 'Ok'" in out


def test_label_falls_back_to_content_desc():
    assert element_label(_el(0, text="", desc="More options")) == "More options"
    assert element_label(_el(0, text="Reply", desc="ignored")) == "Reply"


def test_added_list_is_capped_with_overflow_count():
    prev = [_el(0, "keep")]
    curr = [_el(0, "keep")] + [_el(i, f"new{i}", cx=100 + i * 50) for i in range(1, 10)]
    out = diff_elements(prev, curr)
    assert "…3 more new" in out  # 9 new, 6 listed, 3 collapsed
    assert out.count("  + '") == 6


# ── execute_tool integration ─────────────────────────────────────────────────


@pytest.fixture()
def wired(monkeypatch):
    """Stub the device layer so execute_tool runs without a real phone."""
    agent_tools._LAST_ELEMENTS.clear()
    monkeypatch.setattr(agent_tools, "_execute_tool_inner", lambda name, args: f"ok:{name}")
    monkeypatch.setattr(agent_tools.ctx, "get_screen_tree", lambda d: '[0] Button "x" [] [0,0][1,1]')
    monkeypatch.setattr("time.sleep", lambda _s: None)

    state = {"elems": [_el(0, "Send")]}
    monkeypatch.setattr(agent_tools.ctx, "get_interactive_elements", lambda d: state["elems"])
    return state


def test_first_ui_action_appends_no_diff(wired):
    out = agent_tools.execute_tool("tap", {"device": "d", "x": 1, "y": 2})
    assert "A11y diff" not in out  # nothing cached yet to diff against
    assert agent_tools._LAST_ELEMENTS["d"] == wired["elems"]  # but state is now cached


def test_second_ui_action_appends_the_diff(wired):
    agent_tools.execute_tool("tap", {"device": "d", "x": 1, "y": 2})  # primes cache
    wired["elems"] = [_el(0, "Send"), _el(1, "Sent ✓", cx=400)]
    out = agent_tools.execute_tool("tap", {"device": "d", "x": 1, "y": 2})
    assert "A11y diff (since last action)" in out
    assert "+ 'Sent ✓'" in out


def test_no_change_is_suppressed(wired):
    agent_tools.execute_tool("tap", {"device": "d", "x": 1, "y": 2})
    out = agent_tools.execute_tool("tap", {"device": "d", "x": 1, "y": 2})  # same elems
    assert "no change" not in out
    assert "A11y diff" not in out


def test_kill_switch_disables_diff(wired, monkeypatch):
    from gitd.config import settings

    monkeypatch.setattr(settings, "a11y_diff_enabled", False)
    agent_tools.execute_tool("tap", {"device": "d", "x": 1, "y": 2})
    wired["elems"] = [_el(0, "Send"), _el(1, "New", cx=400)]
    out = agent_tools.execute_tool("tap", {"device": "d", "x": 1, "y": 2})
    assert "A11y diff" not in out


def test_read_only_tool_does_not_update_cache(wired):
    # screenshot is not a _UI_ACTION_TOOL → no diff, no cache write
    agent_tools.execute_tool("screenshot", {"device": "d"})
    assert "d" not in agent_tools._LAST_ELEMENTS


def test_diff_failure_is_fail_open(wired, monkeypatch):
    agent_tools.execute_tool("tap", {"device": "d", "x": 1, "y": 2})  # prime

    def boom(_d):
        raise RuntimeError("uiautomator dump failed")

    monkeypatch.setattr(agent_tools.ctx, "get_interactive_elements", boom)
    # must still return the normal result, no exception
    out = agent_tools.execute_tool("tap", {"device": "d", "x": 1, "y": 2})
    assert out.startswith("ok:tap")
