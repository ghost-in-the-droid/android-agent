"""Portal-backed XML and element serializers retain native accessibility state."""

import xml.etree.ElementTree as ET

import pytest

from gitd.bots.common.adb import Device
from gitd.services import device_context
from gitd.skills.auto_creator import extract_interactive_elements


@pytest.fixture(params=["provider", "http"])
def portal_device(request, monkeypatch):
    device = Device("mock-phone")
    bounds = {"left": 0, "top": 0, "right": 50, "bottom": 50} if request.param == "provider" else "0,0,50,50"
    occupied = {
        "className": "android.widget.Button", "resourceId": "com.example:id/cell",
        "text": "", "isClickable": True, "isEnabled": False, "isCheckable": True,
        "isChecked": True, "isFocusable": True, "isFocused": True, "isSelected": True,
        "boundsInScreen" if request.param == "provider" else "bounds": bounds,
    }
    empty = {**occupied, "resourceId": "com.example:id/empty", "isEnabled": True,
             "isChecked": False, "isSelected": False, "isFocused": False}
    tree = {"className": "android.view.View", "children": [occupied, empty]}
    monkeypatch.setattr(device, "dump_portal_json", lambda: tree)
    monkeypatch.setattr(device, "adb_soft", lambda *a, **kw: pytest.fail("must not fall back to uiautomator"))
    return device


def test_portal_dump_xml_distinguishes_disabled_occupied_cells(portal_device):
    root = ET.fromstring(portal_device.dump_xml())
    cell = root.find('.//*[@resource-id="com.example:id/cell"]')
    empty = root.find('.//*[@resource-id="com.example:id/empty"]')
    for key in ("enabled", "checked", "selected", "focused"):
        assert cell.get(key) == ("false" if key == "enabled" else "true")
        assert empty.get(key) == ("true" if key == "enabled" else "false")
    assert cell.get("checkable") == cell.get("focusable") == "true"
    assert root.find("node").get("enabled") == "true"  # older Portal nodes omit state


def test_portal_state_survives_element_serializers(portal_device, monkeypatch):
    monkeypatch.setattr(device_context, "get_device", lambda ref: portal_device)
    for elements in (device_context.get_interactive_elements("mock-phone"),
                     extract_interactive_elements(portal_device.dump_xml())):
        cell = next(e for e in elements if e["resource_id"].endswith("cell"))
        empty = next(e for e in elements if e["resource_id"].endswith("empty"))
        assert cell["enabled"] is False and empty["enabled"] is True
        for key in ("checked", "selected", "focused"):
            assert cell[key] is True and empty[key] is False


def test_screen_tree_exposes_state_even_for_unlabelled_disabled_cells(portal_device, monkeypatch):
    monkeypatch.setattr(device_context, "get_device", lambda ref: portal_device)
    monkeypatch.setattr(portal_device, "adb", lambda *a, **kw: "Physical size: 100x100")
    xml = portal_device.dump_xml().replace('clickable="true"', 'clickable="false"')
    monkeypatch.setattr(portal_device, "dump_xml", lambda: xml)
    tree = device_context.get_screen_tree("mock-phone")
    for state in ("disabled", "checked", "focused", "selected"):
        assert state in tree


def test_transient_targets_are_read_fresh_on_each_portal_http_snapshot(monkeypatch):
    import json
    from types import SimpleNamespace

    board = {"className": "android.view.View", "resourceId": "board", "children": []}
    targets = {**board, "children": [{"className": "android.view.View", "resourceId": "legal-e4",
                                     "boundsInScreen": {"left": 0, "top": 0, "right": 0, "bottom": 0}}]}
    replies = iter([board, targets, board])
    device = Device("mock-chess")
    monkeypatch.setattr(Device, "_portal_skip_until", {})
    monkeypatch.setattr(Device, "_portal_answered", set())
    monkeypatch.setattr(device, "_ensure_portal_forward", lambda: 18000)

    def response(*args, **kwargs):
        body = json.dumps({"status": "success", "result": json.dumps({"a11y_tree": next(replies)})}).encode()
        return SimpleNamespace(read=lambda: body)

    monkeypatch.setattr("urllib.request.urlopen", response)
    monkeypatch.setattr(device, "adb_soft", lambda *a, **kw: pytest.fail("must not use native dump"))
    assert "legal-e4" not in device.dump_xml()
    selected = ET.fromstring(device.dump_xml())
    target = selected.find('.//*[@resource-id="legal-e4"]')
    assert target is not None and target.get("bounds") == "[0,0][0,0]"
    assert "legal-e4" not in device.dump_xml()


def test_application_popup_window_roots_survive_portal_xml_conversion(monkeypatch):
    device = Device("mock-chess-popup")
    tree = {"className": "android.view.WindowRoots", "children": [
        {"className": "android.view.View", "resourceId": "board"},
        {"className": "android.view.View", "resourceId": "legal-e4", "text": "", "isClickable": False},
    ]}
    monkeypatch.setattr(device, "dump_portal_json", lambda: tree)
    monkeypatch.setattr(device, "adb_soft", lambda *a, **kw: pytest.fail("must not use native dump"))
    root = ET.fromstring(device.dump_xml())
    assert root.find('.//*[@resource-id="board"]') is not None
    assert root.find('.//*[@resource-id="legal-e4"]') is not None
