"""Dispatch tests for RecordedStepAction new step types (M2).

Device-free: uses a mock Device and asserts the right Device call / service
call is made for locator-tap, long_press, open_url, and launch_intent. The
per-step settle sleep is patched out for speed.
"""

from unittest.mock import MagicMock

import pytest

import gitd.skills.base as base
from gitd.skills.base import RecordedStepAction


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(base.time, "sleep", lambda *a, **k: None)


def _run(step, device):
    return RecordedStepAction(device, step, 0).execute()


def test_locator_tap_uses_element_find():
    dev = MagicMock()
    dev.dump_xml.return_value = "<hierarchy/>"
    dev.find_bounds.return_value = "[0,0][20,20]"
    dev.bounds_center.return_value = (10, 10)
    res = _run({"action": "tap", "text": "Search"}, dev)
    assert res.success
    dev.tap.assert_called_once_with(10, 10)


def test_locator_tap_falls_back_to_coords():
    dev = MagicMock()
    dev.dump_xml.return_value = "<hierarchy/>"
    dev.find_bounds.return_value = None  # locator no longer resolves
    res = _run({"action": "tap", "resource_id": "com.x:id/gone", "x": 111, "y": 222}, dev)
    assert res.success
    dev.tap.assert_called_once_with(111, 222)


def test_locator_tap_fails_when_unresolved_and_no_coords():
    dev = MagicMock()
    dev.dump_xml.return_value = "<hierarchy/>"
    dev.find_bounds.return_value = None
    res = _run({"action": "tap", "text": "Nope"}, dev)
    assert not res.success
    assert "locator not found" in res.error
    dev.tap.assert_not_called()


def test_plain_coordinate_tap_still_works():
    dev = MagicMock()
    res = _run({"action": "tap", "x": 5, "y": 6}, dev)
    assert res.success
    dev.tap.assert_called_once_with(5, 6)


def test_long_press():
    dev = MagicMock()
    res = _run({"action": "long_press", "x": 100, "y": 200, "duration_ms": 1200}, dev)
    assert res.success
    dev.long_press.assert_called_once_with(100, 200, duration_ms=1200)


def test_open_url_routes_through_browser(monkeypatch):
    called = {}
    import gitd.services.browser as browser

    monkeypatch.setattr(browser, "open_url", lambda serial, url, bundle_id=None: called.update(serial=serial, url=url))
    dev = MagicMock()
    dev.serial = "SERIAL1"
    res = _run({"action": "open_url", "url": "https://www.reddit.com/r/LocalLLaMA/"}, dev)
    assert res.success
    assert called == {"serial": "SERIAL1", "url": "https://www.reddit.com/r/LocalLLaMA/"}


def test_launch_intent_routes_through_device_context(monkeypatch):
    captured = {}
    import gitd.services.device_context as dc

    def _fake(serial, action="", data="", package="", component="", extras=None):
        captured.update(serial=serial, action=action, data=data, package=package)

    monkeypatch.setattr(dc, "launch_intent", _fake)
    dev = MagicMock()
    dev.serial = "SERIAL2"
    step = {"action": "launch_intent", "intent_action": "android.intent.action.VIEW", "data": "geo:0,0"}
    res = _run(step, dev)
    assert res.success
    # 'intent_action' step field maps to the intent's 'action' arg (dispatch-key collision avoided)
    assert captured == {"serial": "SERIAL2", "action": "android.intent.action.VIEW", "data": "geo:0,0", "package": ""}
