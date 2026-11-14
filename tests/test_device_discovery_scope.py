"""Device selection limits discovery before model/status probes are performed."""

import json
from types import SimpleNamespace

import pytest

from gitd import mcp_server
from gitd.bots.common import device
from gitd.services.agent_tools import execute_tool


@pytest.fixture(autouse=True)
def discovery(monkeypatch):
    monkeypatch.delenv("GHOST_DEVICE", raising=False)
    monkeypatch.delenv("ANDROID_SERIAL", raising=False)
    monkeypatch.setattr(device, "list_connected", lambda: ["mock-phone", "other-phone"])
    monkeypatch.setattr(device, "ios_refs_from_host", lambda: ["ios:mock", "ios:other"])
    monkeypatch.setattr(device, "ios_enabled", lambda: True)


@pytest.mark.parametrize("variable", ["GHOST_DEVICE", "ANDROID_SERIAL"])
def test_android_selection_filters_both_agent_interfaces_and_avoids_ios(monkeypatch, variable):
    monkeypatch.setenv(variable, "mock-phone")
    monkeypatch.setattr(device, "ios_refs_from_host", lambda: pytest.fail("must not discover other platforms"))
    monkeypatch.setattr(device, "discover_host_ios_devices", lambda **kw: pytest.fail("must not probe iOS"))

    class Phone:
        def __init__(self, ref):
            assert ref == "mock-phone"

        def adb(self, *args, **kwargs):
            return "Test Phone"

    monkeypatch.setattr(mcp_server, "Device", Phone)
    assert device.list_connected_device_refs() == ["mock-phone"]
    assert mcp_server.list_devices().splitlines() == [mcp_server.DEVICE_LIST_HEADER, "mock-phone  model=Test Phone"]
    assert json.loads(execute_tool("list_devices", {})) == [{"serial": "mock-phone", "platform": "android"}]


def test_explicit_ghost_selection_wins_over_android_serial(monkeypatch):
    monkeypatch.setenv("GHOST_DEVICE", "other-phone")
    monkeypatch.setenv("ANDROID_SERIAL", "mock-phone")
    assert device.list_connected_device_refs() == ["other-phone"]


def test_blank_ghost_selection_falls_back_to_android_serial(monkeypatch):
    monkeypatch.setenv("GHOST_DEVICE", " ")
    monkeypatch.setenv("ANDROID_SERIAL", "mock-phone")
    assert device.list_connected_device_refs() == ["mock-phone"]


def test_missing_selected_device_never_exposes_others(monkeypatch):
    monkeypatch.setenv("GHOST_DEVICE", "missing-phone")
    assert device.list_connected_device_refs() == []
    assert "No devices connected" in mcp_server.list_devices()
    assert json.loads(execute_tool("list_devices", {})) == []


def test_unset_selection_preserves_all_device_discovery():
    assert device.list_connected_device_refs() == ["mock-phone", "other-phone", "ios:mock", "ios:other"]


def test_ios_selection_probes_only_the_selected_ref(monkeypatch):
    monkeypatch.setenv("GHOST_DEVICE", "ios:mock")
    monkeypatch.setattr(device, "list_connected", lambda: pytest.fail("must not discover Android"))
    monkeypatch.setattr(device, "discover_host_ios_devices", lambda **kw: [])
    cfg = SimpleNamespace(device_name="Mock iPhone", appium_url="http://127.0.0.1:4723",
                          platform_version="17", bundle_id="", browser_name="", wda_url="",
                          mjpeg_server_port=9100, mjpeg_settings=lambda: {})
    monkeypatch.setattr(device, "ios_config_for_udid", lambda ref: cfg)
    probes = []

    def probe(ref, **kwargs):
        probes.append(ref)
        return SimpleNamespace(to_dict=lambda: {"state": "available"})

    monkeypatch.setattr(device, "probe_ios_device", probe)
    assert device.list_connected_device_refs() == ["ios:mock"]
    assert [d["serial"] for d in device.list_configured_ios_devices()] == ["ios:mock"]
    assert probes == ["ios:mock"]
