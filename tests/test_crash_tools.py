"""Tests for the crash-report MCP tools (_parse_crashes / list_crashes / get_crash).

The parser is exercised against captured logcat crash-buffer text — no device.
"""

import json
import types

import pytest

import gitd.mcp_server as mcp_server
from gitd.mcp_server import _parse_crashes, get_crash, list_crashes

_SAMPLE = """--------- beginning of crash
06-24 02:45:49.127 21001 21001 E AndroidRuntime: FATAL EXCEPTION: main
06-24 02:45:49.127 21001 21001 E AndroidRuntime: Process: com.example.app, PID: 21001
06-24 02:45:49.127 21001 21001 E AndroidRuntime: java.lang.RuntimeException: Unable to start activity
06-24 02:45:49.127 21001 21001 E AndroidRuntime: \tat android.app.ActivityThread.performLaunchActivity(ActivityThread.java:3782)
06-24 03:00:00.000 1500 1600 E ActivityManager: ANR in com.other.app (com.other/.MainActivity)
06-24 04:10:10.000 999 999 E AndroidRuntime: FATAL EXCEPTION: worker
06-24 04:10:10.000 999 999 E AndroidRuntime: Process: com.late.crash, PID: 999
06-24 04:10:10.000 999 999 E AndroidRuntime: java.lang.NullPointerException: boom
06-24 04:10:10.000 999 999 E AndroidRuntime: \tat com.late.Thing.run(Thing.java:1)
"""


def test_parse_java_crash_extracts_process_and_summary():
    crashes = _parse_crashes(_SAMPLE)
    java = [c for c in crashes if c["type"] == "java"]
    assert len(java) == 2
    first = next(c for c in java if c["process"] == "com.example.app")
    assert first["timestamp"] == "06-24 02:45:49.127"
    assert "RuntimeException" in first["summary"]
    assert "performLaunchActivity" in first["raw"]  # full stack retained


def test_parse_anr():
    anr = [c for c in _parse_crashes(_SAMPLE) if c["type"] == "anr"]
    assert len(anr) == 1
    assert anr[0]["process"] == "com.other.app"


def test_most_recent_first():
    crashes = _parse_crashes(_SAMPLE)
    # the 04:10 NullPointer crash is latest in the log → first in the result
    assert crashes[0]["process"] == "com.late.crash"


def test_parse_empty_is_empty():
    assert _parse_crashes("") == []
    assert _parse_crashes("06-24 nothing interesting here\n") == []


def test_list_crashes_shape_and_package_filter(monkeypatch):
    monkeypatch.setattr(mcp_server, "_run_logcat_crash", lambda device, timeout=10: _SAMPLE)
    body = json.loads(list_crashes("SER1"))
    assert body["count"] == 3
    assert {c["type"] for c in body["crashes"]} == {"java", "anr"}

    filtered = json.loads(list_crashes("SER1", package="com.example"))
    assert filtered["count"] == 1
    assert filtered["crashes"][0]["process"] == "com.example.app"


def test_get_crash_returns_most_recent_full_stack(monkeypatch):
    monkeypatch.setattr(mcp_server, "_run_logcat_crash", lambda device, timeout=10: _SAMPLE)
    out = get_crash("SER1")
    assert "com.late.crash" in out and "NullPointerException" in out

    scoped = get_crash("SER1", package="com.example.app")
    assert "RuntimeException" in scoped and "performLaunchActivity" in scoped


def test_get_crash_no_crashes(monkeypatch):
    monkeypatch.setattr(mcp_server, "_run_logcat_crash", lambda device, timeout=10: "")
    assert "No crashes found" in get_crash("SER1")


# ── #675: adb failure must surface, not read as "no crashes" ─────────────────


def _fake_run(returncode, stdout="", stderr=""):
    return lambda *a, **k: types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def test_run_logcat_crash_raises_on_nonzero(monkeypatch):
    monkeypatch.setattr(mcp_server.subprocess, "run", _fake_run(1, "", "error: device offline"))
    with pytest.raises(RuntimeError, match="offline"):
        mcp_server._run_logcat_crash("SER1")


def test_offline_device_surfaces_error_not_phantom_no_crashes(monkeypatch):
    # nonzero exit + empty stdout used to parse to zero crashes → "app is fine".
    monkeypatch.setattr(mcp_server.subprocess, "run", _fake_run(1, "", "device offline"))
    body = json.loads(list_crashes("SER1"))
    assert "error" in body and body.get("count") != 0
    assert get_crash("SER1").startswith("Error")


# ── #675: ANRs come from the events buffer (am_anr), not the crash buffer ─────

_ANR_EVENT = "06-24 05:00:00.000 1500 1600 I am_anr  : [0,21001,com.anr.app,952647748,Input dispatching timed out]"


def test_parse_am_anr_event():
    anr = [c for c in _parse_crashes(_ANR_EVENT) if c["type"] == "anr"]
    assert len(anr) == 1
    assert anr[0]["process"] == "com.anr.app"
    assert "timed out" in anr[0]["summary"]
