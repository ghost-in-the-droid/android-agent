import base64
import json
import os

import pytest

from gitd.bots.common.device import (
    get_device,
    ios_refs_from_env,
    ios_refs_from_host,
    list_configured_ios_devices,
    platform_for_device,
)
from gitd.bots.common.ios import (
    IOSBackendError,
    IOSDevice,
    _parse_devicectl_details,
    _parse_xctrace_devices,
    _skill_ios_app_inventory,
    classify_ios_error,
    configured_ios_udids,
    discover_host_ios_devices,
    ios_config_for_udid,
    ios_xml_to_elements,
    known_ios_udids,
    normalize_wda_xml,
    remote_xpc_manual_recovery,
    remote_xpc_tunnel_status,
    visible_text_entries_from_xml,
)

RAW_WDA_XML = """<?xml version="1.0" encoding="UTF-8"?>
<AppiumAUT>
  <XCUIElementTypeApplication type="XCUIElementTypeApplication" name="Safari" label="Safari" enabled="true" visible="true" x="0" y="0" width="393" height="852">
    <XCUIElementTypeButton type="XCUIElementTypeButton" name="Done" label="Done" enabled="true" visible="true" x="10" y="20" width="100" height="30"/>
    <XCUIElementTypeTextField type="XCUIElementTypeTextField" name="Address" label="Address" value="ghostinthedroid.com" enabled="true" visible="true" x="20" y="60" width="300" height="44"/>
    <XCUIElementTypeScrollView type="XCUIElementTypeScrollView" name="Page" label="Page" enabled="true" visible="true" x="0" y="120" width="393" height="700"/>
  </XCUIElementTypeApplication>
</AppiumAUT>
"""

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


class FakeResponse:
    def __init__(self, data, status_code=200, text=""):
        self._data = data
        self.status_code = status_code
        self.text = text

    def json(self):
        return self._data


def test_normalize_wda_xml_scales_bounds_and_marks_interactive():
    xml = normalize_wda_xml(RAW_WDA_XML, scale_x=3.0, scale_y=3.0)

    assert "<hierarchy" in xml
    assert 'class="XCUIElementTypeButton"' in xml
    assert 'text="Done"' in xml
    assert 'content-desc="Done"' in xml
    assert 'resource-id="Done"' in xml
    assert 'clickable="true"' in xml
    assert 'bounds="[30,60][330,150]"' in xml
    assert 'ios-point-bounds="[10,20][110,50]"' in xml
    assert 'class="XCUIElementTypeScrollView"' in xml
    assert 'scrollable="true"' in xml


def test_ios_xml_to_elements_matches_android_element_shape():
    xml = normalize_wda_xml(RAW_WDA_XML, scale_x=2.0, scale_y=2.0)
    elements = ios_xml_to_elements(xml)

    done = next(el for el in elements if el["text"] == "Done")
    assert done["content_desc"] == "Done"
    assert done["resource_id"] == "Done"
    assert done["class"] == "XCUIElementTypeButton"
    assert done["bounds"] == {"x1": 20, "y1": 40, "x2": 220, "y2": 100}
    assert done["center"] == {"x": 120, "y": 70}
    assert done["clickable"] is True

    assert any(el["scrollable"] for el in elements)


def test_factory_routes_ios_prefix(monkeypatch):
    monkeypatch.setenv("IOS_DEVICE_UDID", "abc123")
    monkeypatch.delenv("IOS_DEVICE_UDIDS", raising=False)
    monkeypatch.setattr("gitd.bots.common.device.discover_host_ios_devices", lambda include_simulators=True: [])

    assert platform_for_device("ios:abc123") == "ios"
    assert platform_for_device("emulator-5554") == "android"
    assert ios_refs_from_env() == ["ios:abc123"]
    dev = get_device("ios:abc123")
    assert isinstance(dev, IOSDevice)
    assert dev.udid == "abc123"


def test_list_configured_ios_devices_includes_config_and_probe_state(monkeypatch):
    calls = []

    class ProbeStatus:
        def to_dict(self):
            return {
                "platform": "ios",
                "device": "ios:abc123",
                "udid": "abc123",
                "state": "available",
                "message": "Appium is reachable",
                "appium_url": "http://appium.local",
            }

    monkeypatch.setenv("IOS_DEVICE_UDID", "abc123")
    monkeypatch.setenv("IOS_DEVICE_NAME", "Blah's iPhone")
    monkeypatch.setenv("IOS_PLATFORM_VERSION", "17.5")
    monkeypatch.setenv("IOS_BUNDLE_ID", "com.google.chrome.ios")
    monkeypatch.setenv("IOS_APPIUM_URL", "http://appium.local")
    monkeypatch.setenv("IOS_MJPEG_SERVER_PORT", "9107")
    monkeypatch.setenv("IOS_MJPEG_SERVER_FRAMERATE", "12")
    monkeypatch.setenv("IOS_MJPEG_SCALING_FACTOR", "60")
    monkeypatch.setenv("IOS_MJPEG_SERVER_SCREENSHOT_QUALITY", "45")
    monkeypatch.setenv("IOS_MJPEG_FIX_ORIENTATION", "false")
    monkeypatch.delenv("IOS_DEVICE_UDIDS", raising=False)
    monkeypatch.delenv("IOS_DEVICES_JSON", raising=False)
    monkeypatch.setattr("gitd.bots.common.device.discover_host_ios_devices", lambda include_simulators=True: [])

    def fake_probe(device, deep=True):
        calls.append((device, deep))
        return ProbeStatus()

    monkeypatch.setattr("gitd.bots.common.device.probe_ios_device", fake_probe)

    devices = list_configured_ios_devices(deep_probe=True)

    assert calls == [("ios:abc123", True)]
    assert devices == [
        {
            "serial": "ios:abc123",
            "model": "Blah's iPhone",
            "connection": "appium-wda",
            "platform": "ios",
            "source": "configured",
            "host_state": "",
            "status": "available",
            "status_message": "Appium is reachable",
            "appium_url": "http://appium.local",
            "device_name": "Blah's iPhone",
            "platform_version": "17.5",
            "bundle_id": "com.google.chrome.ios",
            "browser_name": "",
            "wda_url": "",
            "mjpeg_server_port": 9107,
            "mjpeg_settings": {
                "mjpegServerFramerate": 12,
                "mjpegScalingFactor": 60.0,
                "mjpegServerScreenshotQuality": 45,
                "mjpegFixOrientation": False,
            },
            "details": {
                "platform": "ios",
                "device": "ios:abc123",
                "udid": "abc123",
                "state": "available",
                "message": "Appium is reachable",
                "appium_url": "http://appium.local",
            },
        }
    ]


def test_parse_xctrace_devices_discovers_connected_ios_and_booted_simulators():
    output = """
== Devices ==
Blah's MacBook Pro (15.5) (00006000-0000000000000000)
Blah's iPhone (18.5) (00008110-0012345678901234)
QA Phone (26.5) (00008110-0016443101D0401E)
iPad QA (17.5) (00008101-0098765432109876)
== Simulators ==
iPhone 16 Pro (18.5) (11111111-2222-3333-4444-555555555555) (Booted)
iPhone 15 (17.5) (aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee) (Shutdown)
iPad mini (18.5) (99999999-8888-7777-6666-555555555555) (Booted)
"""

    assert _parse_xctrace_devices(output) == [
        {
            "udid": "00008110-0012345678901234",
            "name": "Blah's iPhone",
            "platform_version": "18.5",
            "source": "host",
            "state": "connected",
        },
        {
            "udid": "00008110-0016443101D0401E",
            "name": "QA Phone",
            "platform_version": "26.5",
            "source": "host",
            "state": "connected",
        },
        {
            "udid": "00008101-0098765432109876",
            "name": "iPad QA",
            "platform_version": "17.5",
            "source": "host",
            "state": "connected",
        },
        {
            "udid": "11111111-2222-3333-4444-555555555555",
            "name": "iPhone 16 Pro",
            "platform_version": "18.5",
            "source": "simulator",
            "state": "Booted",
        },
        {
            "udid": "99999999-8888-7777-6666-555555555555",
            "name": "iPad mini",
            "platform_version": "18.5",
            "source": "simulator",
            "state": "Booted",
        },
    ]

    assert [item["udid"] for item in _parse_xctrace_devices(output, include_simulators=False)] == [
        "00008110-0012345678901234",
        "00008110-0016443101D0401E",
        "00008101-0098765432109876",
    ]


def test_discover_host_ios_devices_adds_booted_simctl_simulators(monkeypatch):
    xctrace_output = """
== Devices ==
QA Phone (26.5) (00008110-0016443101D0401E)
== Simulators ==
iPhone 15 Pro Simulator (17.5) (32918B6B-71E5-4A14-94C6-97F0B8B2DC44)
"""
    simctl_output = json.dumps(
        {
            "devices": {
                "com.apple.CoreSimulator.SimRuntime.iOS-17-5": [
                    {
                        "udid": "32918B6B-71E5-4A14-94C6-97F0B8B2DC44",
                        "name": "iPhone 15 Pro",
                        "state": "Booted",
                        "isAvailable": True,
                    }
                ]
            }
        }
    )

    def fake_check_output(cmd, **_kwargs):
        if cmd[:3] == ["xcrun", "xctrace", "list"]:
            return xctrace_output
        if cmd[:4] == ["xcrun", "simctl", "list", "devices"]:
            return simctl_output
        raise AssertionError(cmd)

    monkeypatch.setattr("gitd.bots.common.ios.subprocess.check_output", fake_check_output)

    assert discover_host_ios_devices() == [
        {
            "udid": "00008110-0016443101D0401E",
            "name": "QA Phone",
            "platform_version": "26.5",
            "source": "host",
            "state": "connected",
        },
        {
            "udid": "32918B6B-71E5-4A14-94C6-97F0B8B2DC44",
            "name": "iPhone 15 Pro",
            "platform_version": "17.5",
            "source": "simulator",
            "state": "Booted",
        },
    ]

    assert discover_host_ios_devices(include_simulators=False) == [
        {
            "udid": "00008110-0016443101D0401E",
            "name": "QA Phone",
            "platform_version": "26.5",
            "source": "host",
            "state": "connected",
        }
    ]


def test_parse_xctrace_devices_ignores_offline_devices():
    output = """
== Devices ==
Blah's MacBook Pro (15.5) (00006000-0000000000000000)
test_owner (26.5) (00008110-0016443101D0401E)

== Devices Offline ==
iPhone von Tobias (18.5) (00008030-000134EA11C3402E)
mad_pad (18.6.2) (00008112-000429D2362A201E)

== Simulators ==
iPhone 16 Pro (18.5) (11111111-2222-3333-4444-555555555555) (Booted)
"""

    assert _parse_xctrace_devices(output) == [
        {
            "udid": "00008110-0016443101D0401E",
            "name": "test_owner",
            "platform_version": "26.5",
            "source": "host",
            "state": "connected",
        },
        {
            "udid": "11111111-2222-3333-4444-555555555555",
            "name": "iPhone 16 Pro",
            "platform_version": "18.5",
            "source": "simulator",
            "state": "Booted",
        },
    ]


def test_parse_devicectl_details_extracts_remote_xpc_tunnel_fields():
    output = """
Current device information:
• identifier: 12E9E87A-11C8-5607-B09B-B58265CE5D4E
▿ deviceProperties:
    • bootState: booted
    • developerModeStatus: enabled
    • name: test_owner
    • osVersionNumber: 26.5
▿ connectionProperties:
    • pairingState: paired
    • transportType: localNetwork
    • tunnelTransportProtocol: tcp
    • tunnelIPAddress: fdc0:1f0c:103c::1
    • tunnelState: connected
"""

    assert _parse_devicectl_details(output) == {
        "identifier": "12E9E87A-11C8-5607-B09B-B58265CE5D4E",
        "boot_state": "booted",
        "developer_mode": "enabled",
        "name": "test_owner",
        "os_version": "26.5",
        "pairing_state": "paired",
        "transport_type": "localNetwork",
        "tunnel_transport_protocol": "tcp",
        "tunnel_ip_address": "fdc0:1f0c:103c::1",
        "tunnel_state": "connected",
    }


def test_remote_xpc_tunnel_status_detects_stale_registry_address(monkeypatch):
    monkeypatch.delenv("IOS_REMOTE_XPC_REGISTRY_PORT", raising=False)
    monkeypatch.delenv("IOS_REMOTE_XPC_REGISTRY_PORTS", raising=False)

    def fake_request(method, url, timeout=None, **kwargs):
        assert method == "GET"
        assert "42314/remotexpc/tunnels/00008110-0016443101D0401E" in url
        return FakeResponse(
            {
                "status": "OK",
                "udid": "00008110-0016443101D0401E",
                "address": "fd5d:d8f1:7a61::1",
                "rsdPort": 63925,
            }
        )

    monkeypatch.setattr("gitd.bots.common.ios.requests.request", fake_request)
    monkeypatch.setattr(
        "gitd.bots.common.ios.devicectl_device_details",
        lambda udid: {"tunnel_ip_address": "fdc0:1f0c:103c::1", "tunnel_state": "connected"},
    )

    status = remote_xpc_tunnel_status(
        "00008110-0016443101D0401E",
        platform_version="26.5",
        host={"source": "host", "platform_version": "26.5"},
    )

    assert status["required"] is True
    assert status["ok"] is False
    assert status["state"] == "stale"
    assert status["registry"]["address"] == "fd5d:d8f1:7a61::1"
    assert status["devicectl"]["tunnel_ip_address"] == "fdc0:1f0c:103c::1"
    assert status["registry_address"] == "fd5d:d8f1:7a61::1"
    assert status["current_address"] == "fdc0:1f0c:103c::1"
    assert status["devicectl_connected"] is True
    assert status["stale_reason"] == "registry_address_mismatch"


def test_remote_xpc_tunnel_status_reports_missing_registry_entry(monkeypatch):
    monkeypatch.delenv("IOS_REMOTE_XPC_REGISTRY_PORT", raising=False)
    monkeypatch.delenv("IOS_REMOTE_XPC_REGISTRY_PORTS", raising=False)

    def fake_request(method, url, timeout=None, **kwargs):
        return FakeResponse({"status": "NOT_FOUND"}, status_code=404)

    monkeypatch.setattr("gitd.bots.common.ios.requests.request", fake_request)

    status = remote_xpc_tunnel_status(
        "00008110-0016443101D0401E",
        platform_version="26.5",
        host={"source": "host", "platform_version": "26.5"},
    )

    assert status["required"] is True
    assert status["ok"] is False
    assert status["state"] == "missing"
    assert status["registry"]["status_code"] == 404


def test_remote_xpc_tunnel_status_uses_configured_registry_ports(monkeypatch):
    urls = []
    monkeypatch.setenv("IOS_REMOTE_XPC_REGISTRY_PORTS", "50000, 42314")

    def fake_request(method, url, timeout=None, **kwargs):
        urls.append(url)
        if ":50000/" in url:
            return FakeResponse({"status": "NOT_FOUND"}, status_code=404)
        return FakeResponse(
            {
                "status": "OK",
                "udid": "00008110-0016443101D0401E",
                "address": "fdc0:1f0c:103c::1",
            }
        )

    monkeypatch.setattr("gitd.bots.common.ios.requests.request", fake_request)
    monkeypatch.setattr(
        "gitd.bots.common.ios.devicectl_device_details",
        lambda udid: {"tunnel_ip_address": "fdc0:1f0c:103c::1", "tunnel_state": "connected"},
    )

    status = remote_xpc_tunnel_status(
        "00008110-0016443101D0401E",
        platform_version="26.5",
        host={"source": "host", "platform_version": "26.5"},
    )

    assert status["ok"] is True
    assert status["state"] == "available"
    assert status["checked_ports"] == [50000, 42314]
    assert status["registry"]["port"] == 42314
    assert [":50000/" in url for url in urls] == [True, False]


def test_remote_xpc_tunnel_status_rejects_disconnected_devicectl_tunnel(monkeypatch):
    monkeypatch.delenv("IOS_REMOTE_XPC_REGISTRY_PORT", raising=False)
    monkeypatch.delenv("IOS_REMOTE_XPC_REGISTRY_PORTS", raising=False)

    def fake_request(method, url, timeout=None, **kwargs):
        return FakeResponse(
            {
                "status": "OK",
                "udid": "00008110-0016443101D0401E",
                "address": "fdc0:1f0c:103c::1",
            }
        )

    monkeypatch.setattr("gitd.bots.common.ios.requests.request", fake_request)
    monkeypatch.setattr(
        "gitd.bots.common.ios.devicectl_device_details",
        lambda udid: {"tunnel_state": "disconnected"},
    )

    status = remote_xpc_tunnel_status(
        "00008110-0016443101D0401E",
        platform_version="26.5",
        host={"source": "host", "platform_version": "26.5"},
    )

    assert status["required"] is True
    assert status["ok"] is False
    assert status["state"] == "stale"
    assert status["registry_address"] == "fdc0:1f0c:103c::1"
    assert status["current_address"] == ""
    assert status["devicectl_connected"] is False
    assert status["stale_reason"] == "devicectl_tunnel_disconnected"
    assert "not connected" in status["message"]


def test_remote_xpc_tunnel_status_requires_devicectl_tunnel_address(monkeypatch):
    monkeypatch.delenv("IOS_REMOTE_XPC_REGISTRY_PORT", raising=False)
    monkeypatch.delenv("IOS_REMOTE_XPC_REGISTRY_PORTS", raising=False)

    def fake_request(method, url, timeout=None, **kwargs):
        return FakeResponse(
            {
                "status": "OK",
                "udid": "00008110-0016443101D0401E",
                "address": "fdc0:1f0c:103c::1",
            }
        )

    monkeypatch.setattr("gitd.bots.common.ios.requests.request", fake_request)
    monkeypatch.setattr(
        "gitd.bots.common.ios.devicectl_device_details",
        lambda udid: {"tunnel_state": "connected"},
    )

    status = remote_xpc_tunnel_status(
        "00008110-0016443101D0401E",
        platform_version="26.5",
        host={"source": "host", "platform_version": "26.5"},
    )

    assert status["required"] is True
    assert status["ok"] is False
    assert status["state"] == "stale"
    assert status["registry_address"] == "fdc0:1f0c:103c::1"
    assert status["current_address"] == ""
    assert status["devicectl_connected"] is True
    assert status["stale_reason"] == "devicectl_address_missing"
    assert "no tunnel IP address" in status["message"]


def test_remote_xpc_tunnel_status_skips_simulators(monkeypatch):
    calls = []

    def fake_request(method, url, timeout=None, **kwargs):
        calls.append(url)
        return FakeResponse({"status": "OK"})

    monkeypatch.setattr("gitd.bots.common.ios.requests.request", fake_request)

    status = remote_xpc_tunnel_status(
        "11111111-2222-3333-4444-555555555555",
        platform_version="26.5",
        host={"source": "simulator", "platform_version": "26.5"},
    )

    assert status["required"] is False
    assert status["ok"] is True
    assert status["state"] == "not_required"
    assert calls == []


def test_known_ios_udids_merges_config_and_host_discovery(monkeypatch):
    monkeypatch.setenv("IOS_DEVICE_UDID", "abc123")
    monkeypatch.setenv("IOS_DEVICE_UDIDS", "ios:abc123,def456")
    monkeypatch.delenv("IOS_DEVICES_JSON", raising=False)
    monkeypatch.setattr(
        "gitd.bots.common.ios.discover_host_ios_devices",
        lambda include_simulators=True: [{"udid": "def456"}, {"udid": "sim789"}],
    )
    monkeypatch.setattr(
        "gitd.bots.common.device.discover_host_ios_devices",
        lambda include_simulators=True: [{"udid": "def456"}, {"udid": "sim789"}],
    )

    assert known_ios_udids() == ["abc123", "def456", "sim789"]
    assert ios_refs_from_host() == ["ios:abc123", "ios:def456", "ios:sim789"]


def test_list_configured_ios_devices_includes_host_discovered_devices(monkeypatch):
    calls = []
    monkeypatch.delenv("IOS_DEVICE_UDID", raising=False)
    monkeypatch.delenv("IOS_DEVICE_UDIDS", raising=False)
    monkeypatch.delenv("IOS_DEVICES_JSON", raising=False)
    monkeypatch.setattr(
        "gitd.bots.common.device.discover_host_ios_devices",
        lambda include_simulators=True: [
            {
                "udid": "00008110-0012345678901234",
                "name": "Blah's iPhone",
                "platform_version": "18.5",
                "source": "host",
                "state": "connected",
            }
        ],
    )

    def fake_probe(device, deep=True):
        calls.append((device, deep))

        class ProbeStatus:
            def to_dict(self):
                return {
                    "platform": "ios",
                    "device": device,
                    "udid": "00008110-0012345678901234",
                    "state": "appium_down",
                    "message": "Appium is unreachable",
                    "appium_url": "http://127.0.0.1:4723",
                }

        return ProbeStatus()

    monkeypatch.setattr("gitd.bots.common.device.probe_ios_device", fake_probe)

    devices = list_configured_ios_devices(deep_probe=False)

    assert calls == [("ios:00008110-0012345678901234", False)]
    assert devices[0]["serial"] == "ios:00008110-0012345678901234"
    assert devices[0]["model"] == "Blah's iPhone"
    assert devices[0]["source"] == "host"
    assert devices[0]["host_state"] == "connected"
    assert devices[0]["platform_version"] == "18.5"
    assert devices[0]["status"] == "appium_down"


def test_per_device_ios_config_from_json(monkeypatch):
    monkeypatch.delenv("IOS_DEVICE_UDID", raising=False)
    monkeypatch.delenv("IOS_DEVICE_UDIDS", raising=False)
    monkeypatch.setenv(
        "IOS_DEVICES_JSON",
        json.dumps(
            {
                "abc123": {
                    "appium_url": "http://127.0.0.1:4725",
                    "bundle_id": "com.google.chrome.ios",
                    "known_apps": [
                        {"name": "Chrome", "bundle_id": "com.google.chrome.ios"},
                        {"name": "NPR", "bundleId": "org.npr.NPR"},
                    ],
                    "mjpeg_server_port": 9101,
                    "mjpeg_server_framerate": 15,
                    "mjpeg_scaling_factor": 50,
                    "mjpeg_server_screenshot_quality": 40,
                    "mjpeg_fix_orientation": False,
                    "screenshot_quality": 2,
                    "wda_launch_timeout": 180000,
                    "allow_provisioning_device_registration": True,
                }
            }
        ),
    )

    assert configured_ios_udids() == ["abc123"]
    cfg = ios_config_for_udid("ios:abc123")
    assert cfg.appium_url == "http://127.0.0.1:4725"
    assert cfg.bundle_id == "com.google.chrome.ios"
    assert cfg.known_apps == (("Chrome", "com.google.chrome.ios"), ("NPR", "org.npr.NPR"))
    assert cfg.mjpeg_server_port == 9101
    assert cfg.mjpeg_settings() == {
        "mjpegServerFramerate": 15,
        "mjpegScalingFactor": 50.0,
        "mjpegServerScreenshotQuality": 40,
        "mjpegFixOrientation": False,
    }
    assert cfg.capabilities()["appium:mjpegServerPort"] == 9101
    assert cfg.capabilities()["appium:screenshotQuality"] == 2
    assert cfg.capabilities()["appium:settings[mjpegServerFramerate]"] == 15
    assert cfg.capabilities()["appium:settings[mjpegScalingFactor]"] == 50.0
    assert cfg.capabilities()["appium:settings[mjpegServerScreenshotQuality]"] == 40
    assert cfg.capabilities()["appium:settings[mjpegFixOrientation]"] is False
    assert cfg.capabilities()["appium:wdaLaunchTimeout"] == 180000
    assert cfg.capabilities()["appium:allowProvisioningDeviceRegistration"] is True


def test_ios_config_infers_host_name_and_platform_version(monkeypatch):
    monkeypatch.delenv("IOS_DEVICE_NAME", raising=False)
    monkeypatch.delenv("IOS_PLATFORM_VERSION", raising=False)
    monkeypatch.delenv("IOS_DEVICES_JSON", raising=False)
    monkeypatch.delenv("IOS_CONFIG_FILE", raising=False)
    monkeypatch.setattr(
        "gitd.bots.common.ios.discover_host_ios_devices",
        lambda include_simulators=True: [
            {
                "udid": "00008110-0016443101D0401E",
                "name": "test_owner",
                "platform_version": "26.5",
                "source": "host",
                "state": "connected",
            }
        ],
    )

    cfg = ios_config_for_udid("ios:00008110-0016443101D0401E")

    assert cfg.device_name == "test_owner"
    assert cfg.platform_version == "26.5"


def test_ios_config_defaults_to_chrome_browser(monkeypatch):
    monkeypatch.delenv("IOS_BUNDLE_ID", raising=False)
    monkeypatch.delenv("IOS_DEVICES_JSON", raising=False)
    monkeypatch.delenv("IOS_CONFIG_FILE", raising=False)

    cfg = ios_config_for_udid("ios:abc123")

    assert cfg.bundle_id == "com.google.chrome.ios"


def test_ios_mjpeg_url_uses_appium_host_and_explicit_override():
    remote = IOSDevice("ios:abc123", appium_url="https://appium.example.test:4723")
    remote.mjpeg_server_port = 9123

    ipv6 = IOSDevice("ios:abc123", appium_url="http://[::1]:4723")
    ipv6.mjpeg_server_port = 9124

    explicit = IOSDevice("ios:abc123", appium_url="http://appium.example.test:4723")
    explicit.mjpeg_screenshot_url = "http://wda.example.test:9100/stream"

    assert IOSDevice("ios:abc123").mjpeg_url == "http://127.0.0.1:9100"
    assert remote.mjpeg_url == "https://appium.example.test:9123"
    assert ipv6.mjpeg_url == "http://[::1]:9124"
    assert explicit.mjpeg_url == "http://wda.example.test:9100/stream"


def test_ios_known_apps_env_accepts_name_to_bundle_mapping(monkeypatch):
    monkeypatch.delenv("IOS_DEVICES_JSON", raising=False)
    monkeypatch.setenv("IOS_KNOWN_APPS_JSON", json.dumps({"Chrome": "com.google.chrome.ios", "NPR": "org.npr.NPR"}))

    cfg = ios_config_for_udid("ios:abc123")

    assert cfg.known_apps == (("Chrome", "com.google.chrome.ios"), ("NPR", "org.npr.NPR"))


def test_ios_skill_app_inventory_reads_local_ios_skill_bundle_ids():
    bundles = {bundle_id for _name, bundle_id in _skill_ios_app_inventory()}

    assert "com.google.chrome.ios" in bundles
    assert "com.zhiliaoapp.musically" in bundles


def test_list_apps_includes_ios_skill_bundle_candidates(monkeypatch):
    monkeypatch.delenv("IOS_BUNDLE_ID", raising=False)
    monkeypatch.delenv("IOS_DEVICES_JSON", raising=False)
    monkeypatch.delenv("IOS_KNOWN_APPS_JSON", raising=False)
    monkeypatch.setattr("gitd.bots.common.ios._skill_ios_app_inventory", lambda: (("NPR Skill", "org.npr.NPR"),))

    dev = IOSDevice("ios:abc123", appium_url="http://appium.local")

    apps = dev.list_apps(query="npr", verify=False)

    assert apps == [
        {
            "name": "NPR Skill",
            "package": "org.npr.NPR",
            "bundle_id": "org.npr.NPR",
            "platform": "ios",
            "source": "skill",
            "verified": False,
            "installed": None,
        }
    ]


def test_list_apps_verifies_known_ios_bundles_with_appium(monkeypatch):
    monkeypatch.delenv("IOS_BUNDLE_ID", raising=False)
    monkeypatch.delenv("IOS_DEVICES_JSON", raising=False)
    monkeypatch.delenv("IOS_KNOWN_APPS_JSON", raising=False)
    calls = []

    def fake_request(method, url, json=None, timeout=None):
        calls.append({"method": method, "url": url, "json": json})
        if url.endswith("/session/session-1/execute/sync"):
            assert json["script"] == "mobile: queryAppState"
            bundle_id = json["args"][0]["bundleId"]
            state = 4 if bundle_id == "com.google.chrome.ios" else 0
            return FakeResponse({"value": state})
        raise AssertionError(f"unexpected request: {method} {url}")

    monkeypatch.setattr("gitd.bots.common.ios.requests.request", fake_request)
    dev = IOSDevice("ios:abc123", appium_url="http://appium.local")
    dev._session_id = "session-1"

    chrome = dev.list_apps(query="chrome")
    tiktok = dev.list_apps(query="tiktok")

    assert chrome == [
        {
            "name": "Chrome",
            "package": "com.google.chrome.ios",
            "bundle_id": "com.google.chrome.ios",
            "platform": "ios",
            "source": "default",
            "verified": True,
            "installed": True,
            "app_state": 4,
            "app_state_name": "running_foreground",
        }
    ]
    assert tiktok == []
    assert len(calls) == 2


def test_list_apps_returns_unverified_candidates_when_appium_is_unavailable(monkeypatch):
    monkeypatch.delenv("IOS_BUNDLE_ID", raising=False)
    monkeypatch.delenv("IOS_DEVICES_JSON", raising=False)
    monkeypatch.delenv("IOS_KNOWN_APPS_JSON", raising=False)

    def fake_request(method, url, json=None, timeout=None):
        raise __import__("requests").ConnectionError("connection refused")

    monkeypatch.setattr("gitd.bots.common.ios.requests.request", fake_request)
    dev = IOSDevice("ios:abc123", appium_url="http://appium.local")

    apps = dev.list_apps(query="chrome")

    assert apps[0]["name"] == "Chrome"
    assert apps[0]["bundle_id"] == "com.google.chrome.ios"
    assert apps[0]["verified"] is False
    assert apps[0]["installed"] is None
    assert "connection refused" in apps[0]["verification_error"]


def test_session_creation_uses_appium_xcuitest_payload(monkeypatch):
    IOSDevice._sessions.clear()
    calls = []

    def fake_request(method, url, json=None, timeout=None):
        calls.append({"method": method, "url": url, "json": json, "timeout": timeout})
        return FakeResponse({"value": {"sessionId": "session-1"}})

    monkeypatch.setattr("gitd.bots.common.ios.requests.request", fake_request)
    monkeypatch.delenv("IOS_WDA_URL", raising=False)
    monkeypatch.delenv("IOS_WEBDRIVERAGENT_URL", raising=False)
    dev = IOSDevice("ios:abc123", appium_url="http://appium.local", bundle_id="com.apple.mobilesafari", timeout=1)

    assert dev._ensure_session() == "session-1"
    body = calls[0]["json"]["capabilities"]["alwaysMatch"]
    assert calls[0]["method"] == "POST"
    assert calls[0]["url"] == "http://appium.local/session"
    assert body["platformName"] == "iOS"
    assert body["appium:automationName"] == "XCUITest"
    assert body["appium:udid"] == "abc123"
    assert body["appium:bundleId"] == "com.apple.mobilesafari"


def test_target_app_switch_clears_instance_session_and_browser_name(monkeypatch):
    IOSDevice._sessions.clear()
    calls = []

    def fake_request(method, url, json=None, timeout=None):
        calls.append({"method": method, "url": url, "json": json, "timeout": timeout})
        return FakeResponse({"value": {"sessionId": "session-chrome"}})

    monkeypatch.setattr("gitd.bots.common.ios.requests.request", fake_request)
    dev = IOSDevice(
        "ios:abc123",
        appium_url="http://appium.local",
        bundle_id="com.apple.mobilesafari",
        browser_name="Safari",
        timeout=1,
    )
    old_config = dev._config
    dev._session_id = "session-safari"
    IOSDevice._sessions[old_config] = "session-safari"

    dev.set_target_app(bundle_id="com.google.chrome.ios")

    assert dev.bundle_id == "com.google.chrome.ios"
    assert dev.browser_name == ""
    assert dev._session_id is None
    assert IOSDevice._sessions[old_config] == "session-safari"
    assert dev._ensure_session() == "session-chrome"
    body = calls[0]["json"]["capabilities"]["alwaysMatch"]
    assert body["appium:bundleId"] == "com.google.chrome.ios"
    assert "browserName" not in body


def test_target_app_switch_reuses_cached_session_for_new_bundle(monkeypatch):
    IOSDevice._sessions.clear()
    validate_calls = []

    def fake_request(method, url, json=None, timeout=None):
        validate_calls.append({"method": method, "url": url, "json": json, "timeout": timeout})
        if url.endswith("/session/session-chrome/window/rect"):
            return FakeResponse({"value": {"width": 393, "height": 852}})
        raise AssertionError(f"unexpected request: {method} {url}")

    monkeypatch.setattr("gitd.bots.common.ios.requests.request", fake_request)
    dev = IOSDevice("ios:abc123", appium_url="http://appium.local", bundle_id="com.apple.mobilesafari", timeout=1)
    dev.set_target_app(bundle_id="com.google.chrome.ios")
    IOSDevice._sessions[dev._config] = "session-chrome"

    assert dev._ensure_session() == "session-chrome"
    assert dev._session_id == "session-chrome"
    assert validate_calls == [
        {
            "method": "GET",
            "url": "http://appium.local/session/session-chrome/window/rect",
            "json": None,
            "timeout": 1,
        }
    ]


def test_stale_appium_session_is_evicted_and_recreated(monkeypatch):
    IOSDevice._sessions.clear()
    calls = []

    def fake_request(method, url, json=None, timeout=None):
        calls.append({"method": method, "url": url, "json": json})
        if url.endswith("/session/session-old/source"):
            return FakeResponse(
                {"value": {"error": "invalid session id", "message": "Session does not exist"}},
                status_code=404,
                text="invalid session id",
            )
        if method == "POST" and url.endswith("/session"):
            return FakeResponse({"value": {"sessionId": "session-new"}})
        if url.endswith("/session/session-new/source"):
            return FakeResponse({"value": RAW_WDA_XML})
        raise AssertionError(f"unexpected request: {method} {url}")

    monkeypatch.setattr("gitd.bots.common.ios.requests.request", fake_request)
    dev = IOSDevice("ios:abc123", appium_url="http://appium.local")
    dev._session_id = "session-old"
    IOSDevice._sessions[dev._config] = "session-old"

    assert dev._request("GET", "/session/session-old/source") == RAW_WDA_XML
    assert dev._session_id == "session-new"
    assert IOSDevice._sessions[dev._config] == "session-new"
    assert [c["url"] for c in calls] == [
        "http://appium.local/session/session-old/source",
        "http://appium.local/session",
        "http://appium.local/session/session-new/source",
    ]


def test_close_deletes_cached_session_even_without_instance_session(monkeypatch):
    IOSDevice._sessions.clear()
    calls = []

    def fake_request(method, url, json=None, timeout=None):
        calls.append({"method": method, "url": url, "json": json, "timeout": timeout})
        if method == "DELETE" and url.endswith("/session/session-cached"):
            return FakeResponse({"value": None})
        raise AssertionError(f"unexpected request: {method} {url}")

    monkeypatch.setattr("gitd.bots.common.ios.requests.request", fake_request)
    dev = IOSDevice("ios:abc123", appium_url="http://appium.local", bundle_id="com.google.chrome.ios", timeout=1)
    IOSDevice._sessions[dev._config] = "session-cached"

    dev.close()

    assert calls == [
        {
            "method": "DELETE",
            "url": "http://appium.local/session/session-cached",
            "json": {},
            "timeout": 1,
        }
    ]
    assert dev._session_id is None
    assert IOSDevice._sessions.get(dev._config) is None


def test_session_creation_includes_real_device_signing_capabilities(monkeypatch):
    IOSDevice._sessions.clear()
    calls = []

    def fake_request(method, url, json=None, timeout=None):
        calls.append({"method": method, "url": url, "json": json, "timeout": timeout})
        return FakeResponse({"value": {"sessionId": "session-1"}})

    monkeypatch.setattr("gitd.bots.common.ios.requests.request", fake_request)
    monkeypatch.setenv("IOS_XCODE_ORG_ID", "83JH73NBRY")
    monkeypatch.setenv("IOS_XCODE_SIGNING_ID", "Apple Development")
    monkeypatch.setenv("IOS_UPDATED_WDA_BUNDLE_ID", "com.ghostinthedroid.wda83")
    monkeypatch.setenv("IOS_ALLOW_PROVISIONING_DEVICE_REGISTRATION", "true")
    monkeypatch.setenv("IOS_WDA_LAUNCH_TIMEOUT", "180000")
    monkeypatch.setenv("IOS_WDA_STARTUP_RETRIES", "1")
    monkeypatch.setenv("IOS_WDA_STARTUP_RETRY_INTERVAL", "10000")
    dev = IOSDevice("ios:abc123", appium_url="http://appium.local", timeout=1)

    assert dev._ensure_session() == "session-1"
    body = calls[0]["json"]["capabilities"]["alwaysMatch"]
    assert body["appium:xcodeOrgId"] == "83JH73NBRY"
    assert body["appium:xcodeSigningId"] == "Apple Development"
    assert body["appium:updatedWDABundleId"] == "com.ghostinthedroid.wda83"
    assert body["appium:allowProvisioningDeviceRegistration"] is True
    assert body["appium:wdaLaunchTimeout"] == 180000
    assert body["appium:wdaStartupRetries"] == 1
    assert body["appium:wdaStartupRetryInterval"] == 10000


def test_session_creation_uses_host_discovered_platform_version(monkeypatch):
    IOSDevice._sessions.clear()
    calls = []

    def fake_request(method, url, json=None, timeout=None):
        calls.append({"method": method, "url": url, "json": json, "timeout": timeout})
        return FakeResponse({"value": {"sessionId": "session-1"}})

    monkeypatch.setattr("gitd.bots.common.ios.requests.request", fake_request)
    monkeypatch.setattr(
        "gitd.bots.common.ios.discover_host_ios_devices",
        lambda include_simulators=True: [
            {
                "udid": "00008110-0016443101D0401E",
                "name": "test_owner",
                "platform_version": "26.5",
                "source": "host",
                "state": "connected",
            }
        ],
    )
    monkeypatch.delenv("IOS_DEVICE_NAME", raising=False)
    monkeypatch.delenv("IOS_PLATFORM_VERSION", raising=False)
    monkeypatch.delenv("IOS_DEVICES_JSON", raising=False)
    monkeypatch.delenv("IOS_CONFIG_FILE", raising=False)
    dev = IOSDevice(
        "ios:00008110-0016443101D0401E",
        appium_url="http://appium.local",
        bundle_id="com.google.chrome.ios",
        timeout=1,
    )

    assert dev._ensure_session() == "session-1"
    body = calls[0]["json"]["capabilities"]["alwaysMatch"]
    assert body["appium:deviceName"] == "test_owner"
    assert body["appium:platformVersion"] == "26.5"


def test_probe_classifies_unreachable_appium(monkeypatch):
    def fake_request(method, url, json=None, timeout=None):
        raise __import__("requests").ConnectionError("connection refused")

    monkeypatch.setattr("gitd.bots.common.ios.requests.request", fake_request)
    status = IOSDevice("ios:abc123", appium_url="http://appium.local").probe(deep=True)

    assert status.state == "appium_down"
    assert "unreachable" in status.message.lower()


def test_probe_reports_configured_unreachable_when_local_udid_not_visible(monkeypatch):
    IOSDevice._sessions.clear()
    calls = []

    def fake_request(method, url, json=None, timeout=None):
        calls.append(url)
        if url.endswith("/status"):
            return FakeResponse({"value": {"ready": True}})
        raise AssertionError(f"unexpected request: {url}")

    monkeypatch.setattr("gitd.bots.common.ios.requests.request", fake_request)
    monkeypatch.setattr("gitd.bots.common.ios.discover_host_ios_devices", lambda include_simulators=True: [])

    status = IOSDevice("ios:00008110-0016443101D0401E", timeout=1).probe(deep=False)

    assert status.state == "configured_unreachable"
    assert "not visible" in status.message
    assert status.checks["appium_status_code"] == 200
    assert status.checks["host_device"] == {"visible": False, "source": "xcrun xctrace list devices"}
    assert all(not url.endswith("/session") for url in calls)


def test_probe_allows_remote_appium_when_udid_not_visible_locally(monkeypatch):
    IOSDevice._sessions.clear()
    calls = []

    def fake_request(method, url, json=None, timeout=None):
        calls.append(url)
        if url.endswith("/status"):
            return FakeResponse({"value": {"ready": True}})
        raise AssertionError(f"unexpected request: {url}")

    monkeypatch.setattr("gitd.bots.common.ios.requests.request", fake_request)
    monkeypatch.setattr("gitd.bots.common.ios.discover_host_ios_devices", lambda include_simulators=True: [])
    monkeypatch.setattr(
        "gitd.bots.common.ios.remote_xpc_tunnel_status",
        lambda *args, **kwargs: {"required": False, "state": "not_required", "ok": True},
    )

    status = IOSDevice(
        "ios:00008110-0016443101D0401E",
        appium_url="http://appium.example.test:4723",
        timeout=1,
    ).probe(deep=False)

    assert status.state == "available"
    assert status.checks == {"appium_status_code": 200}


def test_probe_fails_fast_when_required_remote_xpc_tunnel_is_stale(monkeypatch):
    IOSDevice._sessions.clear()
    calls = []
    monkeypatch.delenv("IOS_REMOTE_XPC_REGISTRY_PORT", raising=False)
    monkeypatch.delenv("IOS_REMOTE_XPC_REGISTRY_PORTS", raising=False)

    def fake_request(method, url, json=None, timeout=None):
        calls.append(url)
        if url.endswith("/status"):
            return FakeResponse({"value": {"ready": True}})
        if "42314/remotexpc/tunnels/00008110-0016443101D0401E" in url:
            return FakeResponse(
                {
                    "status": "OK",
                    "udid": "00008110-0016443101D0401E",
                    "address": "fd5d:d8f1:7a61::1",
                }
            )
        raise AssertionError(f"unexpected request: {url}")

    monkeypatch.setattr("gitd.bots.common.ios.requests.request", fake_request)
    monkeypatch.setattr(
        "gitd.bots.common.ios.discover_host_ios_devices",
        lambda include_simulators=True: [
            {
                "udid": "00008110-0016443101D0401E",
                "name": "test_owner",
                "platform_version": "26.5",
                "source": "host",
                "state": "connected",
            }
        ],
    )
    monkeypatch.setattr(
        "gitd.bots.common.ios.devicectl_device_details",
        lambda udid: {"tunnel_ip_address": "fdc0:1f0c:103c::1", "tunnel_state": "connected"},
    )
    monkeypatch.delenv("IOS_DEVICE_NAME", raising=False)
    monkeypatch.delenv("IOS_PLATFORM_VERSION", raising=False)
    dev = IOSDevice("ios:00008110-0016443101D0401E", appium_url="http://appium.local", timeout=1)

    status = dev.probe(deep=True)

    assert status.state == "remote_xpc_tunnel_unavailable"
    assert "stale tunnel" in status.message
    assert status.checks["remote_xpc_tunnel"]["state"] == "stale"
    assert all(not url.endswith("/session") for url in calls)


def test_restart_remote_xpc_tunnel_starts_new_process_after_stopping_owned_process(monkeypatch, tmp_path):
    IOSDevice._sessions.clear()
    kill_calls = []
    popen_calls = []
    status_calls = []
    log_path = tmp_path / "tunnel.log"

    class FakePopen:
        pid = 4321

        def __init__(self, command, stdin=None, stdout=None, stderr=None, start_new_session=False):
            popen_calls.append(
                {
                    "command": command,
                    "stdin": stdin,
                    "stdout": stdout,
                    "stderr": stderr,
                    "start_new_session": start_new_session,
                }
            )

    def fake_tunnel_status(*args, **kwargs):
        status_calls.append((args, kwargs))
        if len(status_calls) == 1:
            return {"required": True, "state": "stale", "ok": False}
        return {"required": True, "state": "available", "ok": True}

    monkeypatch.setattr("gitd.bots.common.ios.remote_xpc_tunnel_status", fake_tunnel_status)
    monkeypatch.setattr(
        "gitd.bots.common.ios._remote_xpc_tunnel_processes",
        lambda udid: [{"pid": 1234, "uid": 501, "command": "appium driver run xcuitest tunnel-creation --udid abc123"}],
    )
    monkeypatch.setattr("gitd.bots.common.ios.os.getuid", lambda: 501)
    monkeypatch.setattr("gitd.bots.common.ios.os.kill", lambda pid, sig: kill_calls.append((pid, sig)))
    monkeypatch.setattr("gitd.bots.common.ios.subprocess.Popen", FakePopen)
    monkeypatch.setenv("IOS_REMOTE_XPC_REGISTRY_PORT", "50000")
    monkeypatch.setenv("IOS_REMOTE_XPC_TUNNEL_LOG", str(log_path))
    dev = IOSDevice("ios:abc123", appium_url="http://appium.local")

    result = dev.restart_remote_xpc_tunnel()

    assert result["ok"] is True
    assert result["pid"] == 4321
    assert result["tunnel_after"]["state"] == "available"
    assert result["attempts"] == 1
    assert result["killed"] == [
        {"pid": 1234, "uid": 501, "command": "appium driver run xcuitest tunnel-creation --udid abc123"}
    ]
    assert kill_calls == [(1234, __import__("signal").SIGTERM)]
    assert popen_calls[0]["command"] == [
        "appium",
        "driver",
        "run",
        "xcuitest",
        "tunnel-creation",
        "--udid",
        "abc123",
        "--tunnel-registry-port",
        "50000",
    ]
    assert popen_calls[0]["start_new_session"] is True
    assert result["log_path"] == str(log_path)


def test_restart_remote_xpc_tunnel_honors_appium_command_override(monkeypatch, tmp_path):
    IOSDevice._sessions.clear()
    popen_calls = []
    log_path = tmp_path / "tunnel.log"

    class FakePopen:
        pid = 4321

        def __init__(self, command, stdin=None, stdout=None, stderr=None, start_new_session=False):
            popen_calls.append(command)

    status_calls = []

    def fake_tunnel_status(*args, **kwargs):
        status_calls.append((args, kwargs))
        if len(status_calls) == 1:
            return {"required": True, "state": "missing", "ok": False, "checked_ports": [42314]}
        return {"required": True, "state": "available", "ok": True}

    monkeypatch.setattr("gitd.bots.common.ios.remote_xpc_tunnel_status", fake_tunnel_status)
    monkeypatch.setattr("gitd.bots.common.ios._remote_xpc_tunnel_processes", lambda udid: [])
    monkeypatch.setattr("gitd.bots.common.ios.subprocess.Popen", FakePopen)
    monkeypatch.setenv("IOS_APPIUM_COMMAND", "npx appium")
    monkeypatch.setenv("IOS_REMOTE_XPC_TUNNEL_LOG", str(log_path))

    dev = IOSDevice("ios:abc123", appium_url="http://appium.local")
    result = dev.restart_remote_xpc_tunnel()

    assert result["ok"] is True
    assert popen_calls == [
        ["npx", "appium", "driver", "run", "xcuitest", "tunnel-creation", "--udid", "abc123"]
    ]


def test_restart_remote_xpc_tunnel_reports_not_ready_after_start(monkeypatch, tmp_path):
    IOSDevice._sessions.clear()
    log_path = tmp_path / "tunnel.log"

    class FakePopen:
        pid = 4321

        def __init__(self, *args, **kwargs):
            pass

    monkeypatch.setattr(
        "gitd.bots.common.ios.remote_xpc_tunnel_status",
        lambda *args, **kwargs: {"required": True, "state": "missing", "ok": False, "checked_ports": [42314]},
    )
    monkeypatch.setattr("gitd.bots.common.ios._remote_xpc_tunnel_processes", lambda udid: [])
    monkeypatch.setattr("gitd.bots.common.ios.subprocess.Popen", FakePopen)
    monkeypatch.setenv("IOS_REMOTE_XPC_TUNNEL_START_TIMEOUT", "0")
    monkeypatch.setenv("IOS_REMOTE_XPC_TUNNEL_LOG", str(log_path))
    dev = IOSDevice("ios:abc123", appium_url="http://appium.local")

    result = dev.restart_remote_xpc_tunnel()

    assert result["ok"] is False
    assert result["manual_action_required"] is True
    assert result["pid"] == 4321
    assert result["tunnel_after"]["state"] == "missing"
    assert result["recovery"]["code"] == "restart_remote_xpc_tunnel"


def test_restart_remote_xpc_tunnel_returns_manual_action_for_foreign_process(monkeypatch):
    IOSDevice._sessions.clear()

    monkeypatch.setattr(
        "gitd.bots.common.ios.remote_xpc_tunnel_status",
        lambda *args, **kwargs: {"required": True, "state": "stale", "ok": False},
    )
    monkeypatch.setattr(
        "gitd.bots.common.ios._remote_xpc_tunnel_processes",
        lambda udid: [{"pid": 1234, "uid": 0, "command": "appium driver run xcuitest tunnel-creation --udid abc123"}],
    )
    monkeypatch.setattr("gitd.bots.common.ios.os.getuid", lambda: 501)
    monkeypatch.setattr(
        "gitd.bots.common.ios.subprocess.Popen",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not start process")),
    )
    dev = IOSDevice("ios:abc123", appium_url="http://appium.local")

    result = dev.restart_remote_xpc_tunnel()

    assert result["ok"] is False
    assert result["manual_action_required"] is True
    assert result["processes"][0]["uid"] == 0
    assert result["recovery"]["code"] == "restart_remote_xpc_tunnel"
    assert result["recovery"]["auto_fixable"] is False
    assert result["recovery"]["manual_action_required"] is True
    assert result["recovery"]["requires_sudo"] is True
    assert result["recovery"]["summary"] == "Stop the stale XCUITest tunnel process with sudo, then start a fresh tunnel."
    assert "sudo appium driver run xcuitest tunnel-creation --udid abc123" in result["recovery"]["steps"][1]
    assert result["recovery"]["kill_command"] == "sudo kill 1234"
    assert result["recovery"]["commands"] == [
        "sudo kill 1234",
        "sudo appium driver run xcuitest tunnel-creation --udid abc123",
        "curl -s http://127.0.0.1:42314/remotexpc/tunnels/abc123",
    ]


def test_remote_xpc_manual_recovery_honors_appium_command_override(monkeypatch):
    monkeypatch.setenv("IOS_APPIUM_COMMAND", "npx appium")
    monkeypatch.setattr("gitd.bots.common.ios._remote_xpc_tunnel_processes", lambda udid: [])

    recovery = remote_xpc_manual_recovery("abc123")

    assert recovery["start_command"] == "sudo npx appium driver run xcuitest tunnel-creation --udid abc123"
    assert recovery["commands"][0] == "sudo npx appium driver run xcuitest tunnel-creation --udid abc123"
    assert recovery["auto_fixable"] is True
    assert recovery["manual_action_required"] is False
    assert recovery["requires_sudo"] is False
    assert recovery["summary"] == "Ghost can restart the stale XCUITest tunnel; manual commands are provided as a fallback."


def test_ios_error_classifier_promotes_real_device_readiness_failures():
    cases = [
        "Unlock test_owner to Continue",
        "Device is passcode locked",
        "The device has not trusted this computer",
        "Developer Mode must be enabled before running WebDriverAgent",
        "UI Automation is not enabled for this device",
        "Timed out waiting for the user to unlock the device",
    ]

    for message in cases:
        state, details = classify_ios_error(RuntimeError(message))
        assert state == "locked"
        assert "blocked by iOS automation permissions" in details


def test_ios_error_classifier_keeps_wda_signing_failures_actionable():
    state, details = classify_ios_error(RuntimeError("xcodebuild failed with code 65: provisioning profile missing"))

    assert state == "wda_signing_failed"
    assert "WebDriverAgent signing" in details


def test_ios_error_classifier_treats_wda_developer_certificate_trust_as_signing():
    message = (
        "WebDriverAgentRunner-Runner encountered an error: The application could not be launched because "
        "the Developer App Certificate is not trusted. Unable to launch com.ghostinthedroid.wda83.xctrunner "
        "because it has an invalid code signature, inadequate entitlements or its profile has not been "
        "explicitly trusted by the user."
    )

    state, details = classify_ios_error(RuntimeError(message))

    assert state == "wda_signing_failed"
    assert "WebDriverAgent signing" in details


def test_ios_error_classifier_treats_session_creation_read_timeout_as_wda_launch_timeout():
    message = (
        "Could not create Appium iOS session: HTTPConnectionPool(host='127.0.0.1', port=4723): "
        "Read timed out. (read timeout=120.0)"
    )

    state, details = classify_ios_error(RuntimeError(message))

    assert state == "wda_launch_timeout"
    assert "WebDriverAgent session creation timed out" in details


def test_ios_error_classifier_promotes_remote_xpc_tunnel_failures():
    state, details = classify_ios_error(
        RuntimeError("Could not create Appium iOS session (500): Could not find the expected device 'abc123'")
    )

    assert state == "remote_xpc_tunnel_unavailable"
    assert "RemoteXPC tunnel" in details


def test_ios_device_health_promotes_stable_wda_fields(monkeypatch):
    class ProbeStatus:
        def to_dict(self):
            return {
                "device": "ios:abc123",
                "udid": "abc123",
                "state": "available",
                "message": "iOS Appium/WDA session is usable",
                "appium_url": "http://appium.local",
                "session_id": "session-1",
                "active_app": {"name": "Chrome", "bundleId": "com.google.chrome.ios"},
                "screen_size": {"width": 393, "height": 852},
                "checks": {"screenshot_bytes": 68, "source_bytes": 2048},
            }

    class FakeIOSDevice:
        def probe(self, deep=True):
            assert deep is True
            return ProbeStatus()

        @property
        def mjpeg_url(self):
            return "http://appium.local/session/session-1/appium/device/screen_stream"

        @property
        def mjpeg_settings(self):
            return {"mjpegServerFramerate": 12, "mjpegScalingFactor": 60.0}

    monkeypatch.setattr("gitd.services.device_context.get_device", lambda device: FakeIOSDevice())

    from gitd.services.device_context import device_health

    health = device_health("ios:abc123")

    assert health["platform"] == "ios"
    assert health["connection"] == {"type": "appium-wda", "status": "available"}
    assert health["appium"]["reachable"] is True
    assert health["appium"]["session_id"] == "session-1"
    assert health["wda"]["session"] == "session-1"
    assert health["wda"]["ready"] is True
    assert health["wda"]["screenshot_ok"] is True
    assert health["wda"]["source_ok"] is True
    assert health["wda"]["active_app"]["bundleId"] == "com.google.chrome.ios"
    assert health["wda"]["mjpeg_url"].endswith("/screen_stream")
    assert health["wda"]["mjpeg_settings"] == {"mjpegServerFramerate": 12, "mjpegScalingFactor": 60.0}
    assert health["recommended_fix"] == ""
    assert health["recovery"] == {"code": "", "summary": "iOS Appium/WDA session is usable.", "steps": []}


def test_ios_device_health_includes_recovery_steps_for_remote_xpc_tunnel(monkeypatch):
    class ProbeStatus:
        def to_dict(self):
            return {
                "device": "ios:abc123",
                "udid": "abc123",
                "state": "remote_xpc_tunnel_unavailable",
                "message": "RemoteXPC tunnel or usbmux device listing is unavailable",
                "appium_url": "http://appium.local",
                "session_id": "",
                "active_app": None,
                "screen_size": None,
                "checks": {
                    "appium_status_code": 200,
                    "remote_xpc_tunnel": {"required": True, "state": "stale", "ok": False, "checked_ports": [42314]},
                },
            }

    class FakeIOSDevice:
        def probe(self, deep=True):
            assert deep is True
            return ProbeStatus()

        @property
        def mjpeg_url(self):
            return "http://appium.local:9100"

        @property
        def mjpeg_settings(self):
            return {}

    monkeypatch.setattr("gitd.services.device_context.get_device", lambda device: FakeIOSDevice())
    monkeypatch.setattr(
        "gitd.bots.common.ios._remote_xpc_tunnel_processes",
        lambda udid: [{"pid": 1234, "uid": 0, "command": "appium driver run xcuitest tunnel-creation --udid abc123"}],
    )
    monkeypatch.setattr("gitd.bots.common.ios.os.getuid", lambda: 501)

    from gitd.services.device_context import device_health

    health = device_health("ios:abc123")

    assert health["connection"]["status"] == "remote_xpc_tunnel_unavailable"
    assert health["appium"]["reachable"] is True
    assert health["appium"]["status_code"] == 200
    assert health["wda"]["ready"] is False
    assert health["recommended_fix"] == "restart_remote_xpc_tunnel"
    assert health["recovery"]["state"] == "remote_xpc_tunnel_unavailable"
    assert health["recovery"]["auto_fixable"] is False
    assert health["recovery"]["manual_action_required"] is True
    assert health["recovery"]["requires_sudo"] is True
    assert health["recovery"]["processes"][0]["pid"] == 1234
    assert health["recovery"]["steps"] == [
        "Stop the stale process ids with sudo: 1234",
        "Run: sudo appium driver run xcuitest tunnel-creation --udid abc123",
        "Verify: http://127.0.0.1:42314/remotexpc/tunnels/abc123",
    ]
    assert health["recovery"]["commands"] == [
        "sudo kill 1234",
        "sudo appium driver run xcuitest tunnel-creation --udid abc123",
        "curl -s http://127.0.0.1:42314/remotexpc/tunnels/abc123",
    ]
    assert health["recovery"]["registry_port"] == 42314


def test_ios_device_health_marks_local_appium_down_auto_fixable(monkeypatch):
    class ProbeStatus:
        def to_dict(self):
            return {
                "device": "ios:abc123",
                "udid": "abc123",
                "state": "appium_down",
                "message": "Appium is unreachable",
                "appium_url": "http://127.0.0.1:4723",
                "session_id": "",
                "checks": {"appium_status_code": None},
            }

    class FakeIOSDevice:
        appium_url = "http://127.0.0.1:4723"

        def probe(self, deep=True):
            assert deep is True
            return ProbeStatus()

        @property
        def mjpeg_url(self):
            return "http://127.0.0.1:9100"

        @property
        def mjpeg_settings(self):
            return {}

    monkeypatch.setattr("gitd.services.device_context.get_device", lambda device: FakeIOSDevice())

    from gitd.services.device_context import device_health

    health = device_health("ios:abc123")

    assert health["connection"]["status"] == "appium_down"
    assert health["recommended_fix"] == "start_appium"
    assert health["recovery"]["auto_fixable"] is True
    assert health["recovery"]["manual_action_required"] is False
    assert health["recovery"]["requires_sudo"] is False


def test_ios_device_health_marks_remote_appium_down_manual(monkeypatch):
    class ProbeStatus:
        def to_dict(self):
            return {
                "device": "ios:abc123",
                "udid": "abc123",
                "state": "appium_down",
                "message": "Appium is unreachable",
                "appium_url": "https://appium.example.test:4723",
                "session_id": "",
                "checks": {"appium_status_code": None},
            }

    class FakeIOSDevice:
        appium_url = "https://appium.example.test:4723"

        def probe(self, deep=True):
            assert deep is True
            return ProbeStatus()

        @property
        def mjpeg_url(self):
            return "http://127.0.0.1:9100"

        @property
        def mjpeg_settings(self):
            return {}

    monkeypatch.setattr("gitd.services.device_context.get_device", lambda device: FakeIOSDevice())

    from gitd.services.device_context import device_health

    health = device_health("ios:abc123")

    assert health["connection"]["status"] == "appium_down"
    assert health["recommended_fix"] == "start_appium"
    assert health["recovery"]["auto_fixable"] is False
    assert health["recovery"]["manual_action_required"] is True
    assert health["recovery"]["requires_sudo"] is False


def test_ios_device_health_includes_recovery_steps_for_wda_signing_failure(monkeypatch):
    class ProbeStatus:
        def to_dict(self):
            return {
                "device": "ios:abc123",
                "udid": "abc123",
                "state": "wda_signing_failed",
                "message": "WebDriverAgent signing/provisioning failed: xcodebuild failed with code 65",
                "appium_url": "http://appium.local",
                "session_id": "",
                "checks": {"appium_status_code": 200, "error": "xcodebuild failed with code 65"},
            }

    class FakeIOSDevice:
        def probe(self, deep=True):
            assert deep is True
            return ProbeStatus()

        @property
        def mjpeg_url(self):
            return "http://127.0.0.1:9100"

        @property
        def mjpeg_settings(self):
            return {}

    monkeypatch.setattr("gitd.services.device_context.get_device", lambda device: FakeIOSDevice())

    from gitd.services.device_context import device_health

    health = device_health("ios:abc123")

    assert health["connection"]["status"] == "wda_signing_failed"
    assert health["recommended_fix"] == "fix_wda_signing"
    assert health["recovery"]["state"] == "wda_signing_failed"
    assert health["recovery"]["code"] == "fix_wda_signing"
    assert "WebDriverAgent" in health["recovery"]["summary"]
    assert any("IOS_XCODE_ORG_ID" in step for step in health["recovery"]["steps"])


def test_ios_device_health_includes_recovery_steps_for_wda_launch_timeout(monkeypatch):
    class ProbeStatus:
        def to_dict(self):
            return {
                "device": "ios:abc123",
                "udid": "abc123",
                "state": "wda_launch_timeout",
                "message": "WebDriverAgent session creation timed out",
                "appium_url": "http://127.0.0.1:4723",
                "session_id": "",
                "checks": {"appium_status_code": 200, "error": "Read timed out"},
            }

    class FakeIOSDevice:
        appium_url = "http://127.0.0.1:4723"

        def probe(self, deep=True):
            assert deep is True
            return ProbeStatus()

        @property
        def mjpeg_url(self):
            return "http://127.0.0.1:9100"

        @property
        def mjpeg_settings(self):
            return {}

    monkeypatch.setattr("gitd.services.device_context.get_device", lambda device: FakeIOSDevice())

    from gitd.services.device_context import device_health

    health = device_health("ios:abc123")

    assert health["connection"]["status"] == "wda_launch_timeout"
    assert health["appium"]["reachable"] is True
    assert health["recommended_fix"] == "fix_wda_launch_timeout"
    assert health["recovery"]["state"] == "wda_launch_timeout"
    assert any("unlocked and awake" in step for step in health["recovery"]["steps"])


def test_fix_device_health_resets_ios_session(monkeypatch):
    calls = []

    class FakeIOSDevice:
        def reset_session(self):
            calls.append("reset")

    monkeypatch.setattr("gitd.services.device_context.get_device", lambda device: FakeIOSDevice())

    from gitd.services.device_context import fix_device_health

    result = fix_device_health("ios:abc123", "reset_session")

    assert result == {
        "ok": True,
        "platform": "ios",
        "issue": "reset_session",
        "message": "iOS Appium session reset",
    }
    assert calls == ["reset"]


def test_ios_start_appium_server_launches_loopback_process(monkeypatch, tmp_path):
    calls = []
    popen_calls = []
    log_path = tmp_path / "appium.log"

    class FakePopen:
        pid = 2468

        def __init__(self, command, stdin=None, stdout=None, stderr=None, start_new_session=False):
            popen_calls.append(
                {
                    "command": command,
                    "stdin": stdin,
                    "stdout": stdout,
                    "stderr": stderr,
                    "start_new_session": start_new_session,
                }
            )

    def fake_request(method, url, json=None, timeout=None):
        calls.append(url)
        if len(calls) == 1:
            raise __import__("requests").ConnectionError("connection refused")
        return FakeResponse({"value": {"ready": True}}, status_code=200)

    monkeypatch.setenv("IOS_APPIUM_LOG", str(log_path))
    monkeypatch.setattr("gitd.bots.common.ios.requests.request", fake_request)
    monkeypatch.setattr("gitd.bots.common.ios.subprocess.Popen", FakePopen)
    monkeypatch.setattr("gitd.bots.common.ios.time.sleep", lambda *_args: None)

    dev = IOSDevice("ios:abc123", appium_url="http://localhost:4729")
    result = dev.start_appium_server()

    assert result["ok"] is True
    assert result["pid"] == 2468
    assert result["command"] == ["appium", "--address", "127.0.0.1", "--port", "4729", "--log-level", "info"]
    assert result["log_path"] == str(log_path)
    assert popen_calls[0]["start_new_session"] is True
    assert calls == ["http://localhost:4729/status", "http://localhost:4729/status"]


def test_ios_start_appium_server_honors_command_override(monkeypatch, tmp_path):
    calls = []
    popen_calls = []
    log_path = tmp_path / "appium.log"

    class FakePopen:
        pid = 2468

        def __init__(self, command, stdin=None, stdout=None, stderr=None, start_new_session=False):
            popen_calls.append(command)

    def fake_request(method, url, json=None, timeout=None):
        calls.append(url)
        if len(calls) == 1:
            raise __import__("requests").ConnectionError("connection refused")
        return FakeResponse({"value": {"ready": True}}, status_code=200)

    monkeypatch.setenv("IOS_APPIUM_COMMAND", "npx appium")
    monkeypatch.setenv("IOS_APPIUM_LOG", str(log_path))
    monkeypatch.setattr("gitd.bots.common.ios.requests.request", fake_request)
    monkeypatch.setattr("gitd.bots.common.ios.subprocess.Popen", FakePopen)
    monkeypatch.setattr("gitd.bots.common.ios.time.sleep", lambda *_args: None)

    dev = IOSDevice("ios:abc123", appium_url="http://127.0.0.1:4729")
    result = dev.start_appium_server()

    assert result["ok"] is True
    assert result["command"] == ["npx", "appium", "--address", "127.0.0.1", "--port", "4729", "--log-level", "info"]
    assert popen_calls == [result["command"]]


def test_ios_start_appium_server_rejects_invalid_command_override(monkeypatch):
    monkeypatch.setenv("IOS_APPIUM_COMMAND", "npx 'appium")
    monkeypatch.setattr(
        "gitd.bots.common.ios.subprocess.Popen",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not start process")),
    )
    monkeypatch.setattr(
        "gitd.bots.common.ios.requests.request",
        lambda *args, **kwargs: (_ for _ in ()).throw(__import__("requests").ConnectionError("down")),
    )

    dev = IOSDevice("ios:abc123", appium_url="http://127.0.0.1:4729")
    result = dev.start_appium_server()

    assert result["ok"] is False
    assert result["manual_action_required"] is True
    assert result["issue"] == "start_appium"
    assert "IOS_APPIUM_COMMAND is not parseable" in result["message"]


def test_ios_start_appium_server_refuses_remote_url():
    dev = IOSDevice("ios:abc123", appium_url="https://appium.example.test:4723")

    result = dev.start_appium_server()

    assert result["ok"] is False
    assert result["manual_action_required"] is True
    assert result["issue"] == "start_appium"
    assert "not a local HTTP server" in result["message"]


def test_fix_device_health_returns_manual_ios_recovery_for_nonlocal_fix():
    from gitd.services.device_context import fix_device_health

    result = fix_device_health("ios:abc123", "fix_wda_signing")

    assert result["ok"] is False
    assert result["platform"] == "ios"
    assert result["issue"] == "fix_wda_signing"
    assert result["manual_action_required"] is True
    assert result["recovery"]["state"] == "wda_signing_failed"


def test_visible_text_entries_filter_controls_and_offscreen_nodes():
    raw = """<?xml version="1.0" encoding="UTF-8"?>
<AppiumAUT>
  <XCUIElementTypeApplication type="XCUIElementTypeApplication" name="Chrome" label="Chrome" enabled="true" visible="true" x="0" y="0" width="393" height="852">
    <XCUIElementTypeButton type="XCUIElementTypeButton" name="Tabs" label="Tabs" enabled="true" visible="true" x="0" y="0" width="60" height="44"/>
    <XCUIElementTypeStaticText type="XCUIElementTypeStaticText" name="World leaders meet for climate talks today" label="World leaders meet for climate talks today" enabled="true" visible="true" x="10" y="120" width="360" height="44"/>
    <XCUIElementTypeStaticText type="XCUIElementTypeStaticText" name="Offscreen article should not appear" label="Offscreen article should not appear" enabled="true" visible="true" x="10" y="900" width="360" height="44"/>
    <XCUIElementTypeStaticText type="XCUIElementTypeStaticText" name="Hidden article should not appear" label="Hidden article should not appear" enabled="true" visible="false" x="10" y="180" width="360" height="44"/>
  </XCUIElementTypeApplication>
</AppiumAUT>
"""
    xml = normalize_wda_xml(raw)

    entries = visible_text_entries_from_xml(xml, screen_size=(393, 852))

    assert [entry["text"] for entry in entries] == ["World leaders meet for climate talks today"]


def test_web_context_entries_prefer_dom_text_and_article_urls(monkeypatch):
    calls = []
    snapshot = {
        "url": "https://text.npr.org/",
        "title": "NPR",
        "bodyText": "Top Stories\nWorld leaders meet for climate talks today",
        "entries": [
            {
                "text": "World leaders meet for climate talks today",
                "tag": "a",
                "href": "https://text.npr.org/article/123",
                "bounds": {"x1": 10, "y1": 100, "x2": 350, "y2": 140},
                "provenance": "web_context",
            }
        ],
    }

    def fake_request(method, url, json=None, timeout=None):
        calls.append({"method": method, "url": url, "json": json})
        if url.endswith("/session/session-1/contexts"):
            return FakeResponse({"value": ["NATIVE_APP", "WEBVIEW_1"]})
        if url.endswith("/session/session-1/context"):
            return FakeResponse({"value": None})
        if url.endswith("/session/session-1/execute/sync"):
            assert "document.querySelectorAll" in json["script"]
            return FakeResponse({"value": snapshot})
        raise AssertionError(f"unexpected request: {method} {url}")

    monkeypatch.setattr("gitd.bots.common.ios.requests.request", fake_request)
    dev = IOSDevice("ios:abc123", appium_url="http://appium.local")
    dev._session_id = "session-1"

    entries = dev.web_text_entries()
    articles = dev.extract_articles(max_items=1)

    assert entries[0]["text"] == "World leaders meet for climate talks today"
    assert entries[0]["url"] == "https://text.npr.org/article/123"
    assert entries[0]["provenance"] == "web_context"
    assert articles == [
        {
            "title": "World leaders meet for climate talks today",
            "url": "https://text.npr.org/article/123",
            "bounds": {"x1": 10, "y1": 100, "x2": 350, "y2": 140},
            "center": {"x": 180, "y": 120},
            "class": "a",
            "provenance": "web_context",
        }
    ]
    context_names = [call["json"]["name"] for call in calls if call["url"].endswith("/context")]
    assert "WEBVIEW_1" in context_names
    assert context_names[-1] == "NATIVE_APP"


def test_native_article_extraction_filters_browser_toolbar_controls(monkeypatch):
    dev = IOSDevice("ios:abc123", appium_url="http://appium.local")
    monkeypatch.setattr(dev, "web_text_entries", lambda max_entries=300: [])
    monkeypatch.setattr(
        dev,
        "native_text_entries",
        lambda include_controls=False, max_entries=300: [
            {
                "text": "Search your screen with Google Lens",
                "bounds": {"x1": 30, "y1": 153, "x2": 162, "y2": 261},
                "center": {"x": 96, "y": 207},
                "class": "XCUIElementTypeButton",
                "provenance": "native",
            },
            {
                "text": "text.npr.org Secure",
                "bounds": {"x1": 30, "y1": 153, "x2": 1140, "y2": 261},
                "center": {"x": 585, "y": 207},
                "class": "XCUIElementTypeButton",
                "provenance": "native",
            },
            {
                "text": "NPR : National Public Radio",
                "bounds": {"x1": 60, "y1": 498, "x2": 963, "y2": 585},
                "center": {"x": 511, "y": 541},
                "class": "XCUIElementTypeStaticText",
                "provenance": "native",
            },
            {
                "text": "Monday, June 8, 2026",
                "bounds": {"x1": 60, "y1": 711, "x2": 546, "y2": 774},
                "center": {"x": 303, "y": 742},
                "class": "XCUIElementTypeStaticText",
                "provenance": "native",
            },
            {
                "text": "Israel and Iran exchange missile fire threatening Middle East truce",
                "bounds": {"x1": 60, "y1": 834, "x2": 1092, "y2": 963},
                "center": {"x": 576, "y": 898},
                "class": "XCUIElementTypeLink",
                "provenance": "native",
            },
        ],
    )

    articles = dev.extract_articles(max_items=3)

    assert [article["title"] for article in articles] == [
        "Israel and Iran exchange missile fire threatening Middle East truce"
    ]


def test_web_context_body_text_fallback_preserves_article_text(monkeypatch):
    snapshot = {
        "url": "https://text.npr.org/article/123",
        "title": "NPR",
        "bodyText": (
            "World leaders meet for climate talks today. "
            "The article body is exposed through document.body even when no DOM entries are returned."
        ),
        "viewport": {"width": 393, "height": 852},
        "entries": [],
    }
    dev = IOSDevice("ios:abc123", appium_url="http://appium.local")

    monkeypatch.setattr(dev, "web_text_snapshot", lambda max_entries=300: snapshot)

    def fail_native_text_entries(**kwargs):
        raise AssertionError("WebView bodyText should be used before native XML fallback")

    monkeypatch.setattr(dev, "native_text_entries", fail_native_text_entries)

    entries = dev.visible_text_entries(max_entries=5)

    assert entries == [
        {
            "text": snapshot["bodyText"],
            "bounds": {"x1": 0, "y1": 0, "x2": 393, "y2": 852},
            "center": {"x": 196, "y": 426},
            "class": "body",
            "resource_id": "",
            "content_desc": "",
            "provenance": "web_context_body",
            "url": "https://text.npr.org/article/123",
            "role": "document",
        }
    ]
    assert dev.extract_visible_text(max_lines=1) == snapshot["bodyText"]


def test_web_context_article_extraction_uses_headings_without_urls(monkeypatch):
    snapshot = {
        "url": "https://news.example/",
        "title": "News",
        "bodyText": "Top Stories\nWorld leaders meet for climate talks today",
        "entries": [
            {
                "text": "World leaders meet for climate talks today",
                "tag": "h2",
                "href": "",
                "bounds": {"x1": 10, "y1": 100, "x2": 350, "y2": 140},
                "provenance": "web_context",
            },
            {
                "text": "Short dek",
                "tag": "p",
                "href": "",
                "bounds": {"x1": 10, "y1": 150, "x2": 350, "y2": 180},
                "provenance": "web_context",
            },
        ],
    }

    def fake_request(method, url, json=None, timeout=None):
        if url.endswith("/session/session-1/contexts"):
            return FakeResponse({"value": ["NATIVE_APP", "WEBVIEW_1"]})
        if url.endswith("/session/session-1/context"):
            return FakeResponse({"value": None})
        if url.endswith("/session/session-1/execute/sync"):
            return FakeResponse({"value": snapshot})
        raise AssertionError(f"unexpected request: {method} {url}")

    monkeypatch.setattr("gitd.bots.common.ios.requests.request", fake_request)
    dev = IOSDevice("ios:abc123", appium_url="http://appium.local")
    dev._session_id = "session-1"

    articles = dev.extract_articles(max_items=1)

    assert articles == [
        {
            "title": "World leaders meet for climate talks today",
            "url": "",
            "bounds": {"x1": 10, "y1": 100, "x2": 350, "y2": 140},
            "center": {"x": 180, "y": 120},
            "class": "h2",
            "provenance": "web_context",
        }
    ]


def test_web_context_article_extraction_prioritizes_content_links(monkeypatch):
    snapshot = {
        "url": "https://text.npr.org/",
        "title": "NPR",
        "bodyText": "Top Stories\nWorld leaders meet for climate talks today",
        "entries": [
            {
                "text": "Sign up for NPR daily newsletter today",
                "tag": "a",
                "href": "https://text.npr.org/newsletter",
                "bounds": {"x1": 10, "y1": 60, "x2": 350, "y2": 90},
                "provenance": "web_context",
            },
            {
                "text": "World leaders meet for climate talks today",
                "tag": "a",
                "href": "https://text.npr.org/2026/06/08/story/123",
                "bounds": {"x1": 10, "y1": 180, "x2": 350, "y2": 220},
                "provenance": "web_context",
            },
        ],
    }

    def fake_request(method, url, json=None, timeout=None):
        if url.endswith("/session/session-1/contexts"):
            return FakeResponse({"value": ["NATIVE_APP", "WEBVIEW_1"]})
        if url.endswith("/session/session-1/context"):
            return FakeResponse({"value": None})
        if url.endswith("/session/session-1/execute/sync"):
            return FakeResponse({"value": snapshot})
        raise AssertionError(f"unexpected request: {method} {url}")

    monkeypatch.setattr("gitd.bots.common.ios.requests.request", fake_request)
    dev = IOSDevice("ios:abc123", appium_url="http://appium.local")
    dev._session_id = "session-1"

    articles = dev.extract_articles(max_items=1)

    assert articles[0]["title"] == "World leaders meet for climate talks today"
    assert articles[0]["url"] == "https://text.npr.org/2026/06/08/story/123"


def test_web_context_article_extraction_keeps_unlinked_headings_when_noisy_links_exist(monkeypatch):
    snapshot = {
        "url": "https://news.example/",
        "title": "News",
        "bodyText": "Top Stories\nWorld leaders meet for climate talks today",
        "entries": [
            {
                "text": "Sign up for our daily newsletter today",
                "tag": "a",
                "href": "https://news.example/newsletter",
                "bounds": {"x1": 10, "y1": 60, "x2": 350, "y2": 90},
                "provenance": "web_context",
            },
            {
                "text": "World leaders meet for climate talks today",
                "tag": "h2",
                "href": "",
                "bounds": {"x1": 10, "y1": 140, "x2": 350, "y2": 180},
                "provenance": "web_context",
            },
        ],
    }

    def fake_request(method, url, json=None, timeout=None):
        if url.endswith("/session/session-1/contexts"):
            return FakeResponse({"value": ["NATIVE_APP", "WEBVIEW_1"]})
        if url.endswith("/session/session-1/context"):
            return FakeResponse({"value": None})
        if url.endswith("/session/session-1/execute/sync"):
            return FakeResponse({"value": snapshot})
        raise AssertionError(f"unexpected request: {method} {url}")

    monkeypatch.setattr("gitd.bots.common.ios.requests.request", fake_request)
    dev = IOSDevice("ios:abc123", appium_url="http://appium.local")
    dev._session_id = "session-1"

    articles = dev.extract_articles(max_items=1)

    assert articles == [
        {
            "title": "World leaders meet for climate talks today",
            "url": "",
            "bounds": {"x1": 10, "y1": 140, "x2": 350, "y2": 180},
            "center": {"x": 180, "y": 160},
            "class": "h2",
            "provenance": "web_context",
        }
    ]


def test_web_context_article_extraction_drops_only_low_value_links(monkeypatch):
    snapshot = {
        "url": "https://news.example/",
        "title": "News",
        "bodyText": "Subscribe\nSign in",
        "entries": [
            {
                "text": "Sign up for our daily newsletter today",
                "tag": "a",
                "href": "https://news.example/newsletter",
                "bounds": {"x1": 10, "y1": 60, "x2": 350, "y2": 90},
                "provenance": "web_context",
            },
            {
                "text": "Subscribe to support local news coverage",
                "tag": "a",
                "href": "https://news.example/subscribe",
                "bounds": {"x1": 10, "y1": 100, "x2": 350, "y2": 130},
                "provenance": "web_context",
            },
        ],
    }

    def fake_request(method, url, json=None, timeout=None):
        if url.endswith("/session/session-1/contexts"):
            return FakeResponse({"value": ["NATIVE_APP", "WEBVIEW_1"]})
        if url.endswith("/session/session-1/context"):
            return FakeResponse({"value": None})
        if url.endswith("/session/session-1/execute/sync"):
            return FakeResponse({"value": snapshot})
        raise AssertionError(f"unexpected request: {method} {url}")

    monkeypatch.setattr("gitd.bots.common.ios.requests.request", fake_request)
    dev = IOSDevice("ios:abc123", appium_url="http://appium.local")
    dev._session_id = "session-1"

    assert dev.extract_articles(max_items=3) == []


def test_ios_wait_for_url_matches_trusted_browser_url(monkeypatch):
    dev = IOSDevice("ios:abc123", appium_url="http://appium.local")
    urls = ["about:blank", "https://text.npr.org/?output=1"]

    monkeypatch.setattr(dev, "_current_url_from_webdriver", lambda: urls.pop(0))
    monkeypatch.setattr(dev, "web_text_snapshot", lambda max_entries=12: {})
    monkeypatch.setattr("gitd.bots.common.ios.time.sleep", lambda *_args, **_kwargs: None)

    status = dev.wait_for_url("https://text.npr.org/?output=1", timeout=1, interval=0.01)

    assert status == {
        "ok": True,
        "expected_url": "https://text.npr.org/?output=1",
        "url": "https://text.npr.org/?output=1",
        "state": "url_matched",
    }


def test_ios_wait_for_url_does_not_match_different_path(monkeypatch):
    dev = IOSDevice("ios:abc123", appium_url="http://appium.local")

    monkeypatch.setattr(dev, "_current_url_from_webdriver", lambda: "https://text.npr.org/article/1")
    monkeypatch.setattr(dev, "web_text_snapshot", lambda max_entries=12: {})

    status = dev.wait_for_url("https://text.npr.org/", timeout=0, interval=0.01)

    assert status["ok"] is False
    assert status["state"] == "timeout"
    assert status["url"] == "https://text.npr.org/article/1"


def test_ios_wait_for_url_falls_back_to_page_text_when_url_is_hidden(monkeypatch):
    dev = IOSDevice("ios:abc123", appium_url="http://appium.local")

    monkeypatch.setattr(dev, "_current_url_from_webdriver", lambda: "")
    monkeypatch.setattr(
        dev,
        "web_text_snapshot",
        lambda max_entries=12: {"bodyText": "Loaded article body", "entries": [{"text": "Loaded article body"}]},
    )

    status = dev.wait_for_url("https://example.com/article", timeout=0, interval=0.01)

    assert status == {
        "ok": True,
        "expected_url": "https://example.com/article",
        "url": "",
        "state": "page_text_available",
        "verified_url": False,
    }


def test_ios_wait_for_url_matches_native_toolbar_url_when_webview_url_is_hidden(monkeypatch):
    dev = IOSDevice("ios:abc123", appium_url="http://appium.local")

    monkeypatch.setattr(dev, "_current_url_from_webdriver", lambda: "")
    monkeypatch.setattr(dev, "web_text_snapshot", lambda max_entries=12: {})
    monkeypatch.setattr(dev, "_current_url_from_native_text", lambda: "text.npr.org")

    status = dev.wait_for_url("https://text.npr.org/", timeout=0, interval=0.01)

    assert status == {
        "ok": True,
        "expected_url": "https://text.npr.org/",
        "url": "text.npr.org",
        "state": "url_matched_native",
    }


def test_ios_get_phone_state_normalizes_active_app_keyboard_and_focus(monkeypatch):
    dev = IOSDevice("ios:abc123", appium_url="http://appium.local", bundle_id="com.google.chrome.ios")
    dev._session_id = "session-1"
    xml = """
    <hierarchy>
      <node class="XCUIElementTypeApplication" text="Chrome" visible="true" bounds="[0,0][393,852]" />
      <node class="XCUIElementTypeTextField" text="Search or type web address" content-desc="Address"
        resource-id="Address" focused="true" visible="true" bounds="[20,60][360,104]" />
      <node class="XCUIElementTypeKeyboard" text="" visible="true" bounds="[0,540][393,852]" />
    </hierarchy>
    """

    monkeypatch.setattr(dev, "_window_rect", lambda: {"x": 0, "y": 0, "width": 393, "height": 852})
    monkeypatch.setattr(dev, "get_screen_size", lambda: (393, 852))
    monkeypatch.setattr(
        dev,
        "_execute_mobile",
        lambda command, args=None: {"name": "Chrome", "bundleId": "com.google.chrome.ios"},
    )
    monkeypatch.setattr(dev, "dump_xml", lambda: xml)

    state = dev.get_phone_state()

    assert state["platform"] == "ios"
    assert state["device"] == "ios:abc123"
    assert state["bundleId"] == "com.google.chrome.ios"
    assert state["bundle_id"] == "com.google.chrome.ios"
    assert state["packageName"] == "com.google.chrome.ios"
    assert state["activityName"] == "com.google.chrome.ios"
    assert state["currentApp"] == "Chrome"
    assert state["keyboardVisible"] is True
    assert state["screenSize"] == {"width": 393, "height": 852}
    assert state["windowRect"] == {"x": 0, "y": 0, "width": 393, "height": 852}
    assert state["focusedElement"] == {
        "text": "Search or type web address",
        "content_desc": "Address",
        "resource_id": "Address",
        "class": "XCUIElementTypeTextField",
        "bounds": {"x1": 20, "y1": 60, "x2": 360, "y2": 104},
        "center": {"x": 190, "y": 82},
    }


def test_ios_get_phone_state_uses_target_bundle_defaults_when_enrichment_fails(monkeypatch):
    dev = IOSDevice("ios:abc123", appium_url="http://appium.local", bundle_id="com.google.chrome.ios")

    monkeypatch.setattr(dev, "_window_rect", lambda: {"x": 0, "y": 0, "width": 393, "height": 852})
    monkeypatch.setattr(dev, "get_screen_size", lambda: (393, 852))
    monkeypatch.setattr(dev, "_execute_mobile", lambda command, args=None: (_ for _ in ()).throw(RuntimeError("no active app")))
    monkeypatch.setattr(dev, "dump_xml", lambda: (_ for _ in ()).throw(RuntimeError("no source")))

    state = dev.get_phone_state()

    assert state["bundleId"] == "com.google.chrome.ios"
    assert state["bundle_id"] == "com.google.chrome.ios"
    assert state["packageName"] == "com.google.chrome.ios"
    assert state["activityName"] == "com.google.chrome.ios"
    assert state["currentApp"] == "Chrome"
    assert state["keyboardVisible"] is False
    assert state["focusedElement"] == {}


def test_ios_open_url_returns_navigation_evidence_from_webdriver(monkeypatch):
    calls = []

    def fake_request(method, url, json=None, timeout=None):
        calls.append({"method": method, "url": url, "json": json})
        if method == "POST" and url.endswith("/session/session-1/url"):
            return FakeResponse({"value": None})
        if method == "GET" and url.endswith("/session/session-1/url"):
            return FakeResponse({"value": "https://example.com/story?id=42&utm=agent"})
        raise AssertionError(f"unexpected request: {method} {url}")

    monkeypatch.setattr("gitd.bots.common.ios.requests.request", fake_request)
    dev = IOSDevice("ios:abc123", appium_url="http://appium.local")
    dev._session_id = "session-1"

    status = dev.open_url("example.com/story?id=42", delay=0)

    assert status["ok"] is True
    assert status["method"] == "webdriver_url"
    assert status["state"] == "url_matched"
    assert status["url"] == "https://example.com/story?id=42&utm=agent"
    assert [call["method"] for call in calls] == ["POST", "GET"]


def test_ios_open_url_falls_back_when_webdriver_url_is_unverified(monkeypatch):
    dev = IOSDevice("ios:abc123", appium_url="http://appium.local", bundle_id="com.google.chrome.ios")
    dev._session_id = "session-1"
    requests_seen = []
    address_calls = []
    statuses = iter(
        [
            {"ok": False, "state": "timeout", "error": "not loaded"},
            {
                "ok": True,
                "expected_url": "https://example.com/",
                "url": "https://example.com/",
                "state": "url_matched",
            },
        ]
    )

    monkeypatch.setattr(
        dev,
        "_request",
        lambda method, path, payload=None, timeout=None: requests_seen.append((method, path, payload)),
    )
    monkeypatch.setattr(dev, "wait_for_url", lambda url, timeout=8.0, interval=0.5: next(statuses))
    monkeypatch.setattr(dev, "_open_url_in_web_context", lambda url, delay=2.0: False)
    monkeypatch.setattr(
        dev,
        "_open_url_via_address_bar",
        lambda url, delay=2.0: address_calls.append((url, delay)) or "address_bar_ocr",
    )

    status = dev.open_url("example.com", delay=0)

    assert status["ok"] is True
    assert status["method"] == "address_bar"
    assert status["address_bar_source"] == "address_bar_ocr"
    assert status["errors"] == [
        {
            "method": "webdriver_url",
            "state": "timeout",
            "error": "not loaded",
        }
    ]
    assert requests_seen == [("POST", "/session/session-1/url", {"url": "https://example.com"})]
    assert address_calls == [("https://example.com", 0)]


def test_ios_open_url_falls_back_when_web_context_url_is_unverified(monkeypatch):
    dev = IOSDevice("ios:abc123", appium_url="http://appium.local", bundle_id="com.google.chrome.ios")
    dev._session_id = "session-1"
    address_calls = []
    statuses = iter(
        [
            {"ok": False, "state": "timeout", "error": "web context did not load"},
            {
                "ok": True,
                "expected_url": "https://example.com/",
                "url": "https://example.com/",
                "state": "url_matched",
            },
        ]
    )

    monkeypatch.setattr(
        dev,
        "_request",
        lambda method, path, payload=None, timeout=None: (_ for _ in ()).throw(IOSBackendError("webdriver failed")),
    )
    monkeypatch.setattr(dev, "wait_for_url", lambda url, timeout=8.0, interval=0.5: next(statuses))
    monkeypatch.setattr(dev, "_open_url_in_web_context", lambda url, delay=2.0: True)
    monkeypatch.setattr(
        dev,
        "_open_url_via_address_bar",
        lambda url, delay=2.0: address_calls.append((url, delay)),
    )

    status = dev.open_url("https://example.com", delay=0)

    assert status["ok"] is True
    assert status["method"] == "address_bar"
    assert status["errors"] == [
        {"method": "webdriver_url", "error": "webdriver failed"},
        {
            "method": "web_context",
            "state": "timeout",
            "error": "web context did not load",
        },
    ]
    assert address_calls == [("https://example.com", 0)]


def test_take_screenshot_decodes_base64(monkeypatch):
    def fake_request(method, url, json=None, timeout=None):
        assert method == "GET"
        assert url.endswith("/session/session-1/screenshot")
        return FakeResponse({"value": base64.b64encode(PNG_1X1).decode()})

    monkeypatch.setattr("gitd.bots.common.ios.requests.request", fake_request)
    dev = IOSDevice("ios:abc123", appium_url="http://appium.local")
    dev._session_id = "session-1"

    assert dev.take_screenshot() == PNG_1X1


def test_tap_converts_screenshot_pixels_to_wda_points(monkeypatch):
    calls = []

    def fake_request(method, url, json=None, timeout=None):
        calls.append({"method": method, "url": url, "json": json})
        return FakeResponse({"value": None})

    monkeypatch.setattr("gitd.bots.common.ios.requests.request", fake_request)
    monkeypatch.setattr("gitd.bots.common.ios.time.sleep", lambda *_: None)
    dev = IOSDevice("ios:abc123", appium_url="http://appium.local")
    dev._session_id = "session-1"
    dev._scale = (3.0, 2.0)

    dev.tap(30, 40)

    move = calls[0]["json"]["actions"][0]["actions"][0]
    assert calls[0]["url"].endswith("/session/session-1/actions")
    assert move["x"] == 10
    assert move["y"] == 20
    assert move["origin"] == "viewport"


def test_launch_app_uses_mobile_launch_app(monkeypatch):
    calls = []

    def fake_request(method, url, json=None, timeout=None):
        calls.append({"method": method, "url": url, "json": json})
        return FakeResponse({"value": None})

    monkeypatch.setattr("gitd.bots.common.ios.requests.request", fake_request)
    monkeypatch.setattr("gitd.bots.common.ios.time.sleep", lambda *_: None)
    dev = IOSDevice("ios:abc123", appium_url="http://appium.local")
    dev._session_id = "session-1"

    assert dev.launch_app("com.apple.mobilesafari") == "com.apple.mobilesafari"
    assert calls[0]["url"].endswith("/session/session-1/execute/sync")
    assert calls[0]["json"] == {
        "script": "mobile: launchApp",
        "args": [{"bundleId": "com.apple.mobilesafari"}],
    }


def test_clipboard_get_decodes_appium_base64(monkeypatch):
    def fake_request(method, url, json=None, timeout=None):
        assert method == "POST"
        assert url.endswith("/session/session-1/appium/device/get_clipboard")
        assert json == {"contentType": "plaintext"}
        return FakeResponse({"value": base64.b64encode("hello iOS".encode()).decode()})

    monkeypatch.setattr("gitd.bots.common.ios.requests.request", fake_request)
    dev = IOSDevice("ios:abc123", appium_url="http://appium.local")
    dev._session_id = "session-1"

    assert dev.clipboard_get() == "hello iOS"


def test_clipboard_set_encodes_appium_payload(monkeypatch):
    calls = []

    def fake_request(method, url, json=None, timeout=None):
        calls.append({"method": method, "url": url, "json": json})
        return FakeResponse({"value": None})

    monkeypatch.setattr("gitd.bots.common.ios.requests.request", fake_request)
    dev = IOSDevice("ios:abc123", appium_url="http://appium.local")
    dev._session_id = "session-1"

    assert dev.clipboard_set("hello iOS") is True
    assert calls[0]["method"] == "POST"
    assert calls[0]["url"].endswith("/session/session-1/appium/device/set_clipboard")
    assert calls[0]["json"]["contentType"] == "plaintext"
    assert calls[0]["json"]["label"] == "Ghost in the Droid"
    assert base64.b64decode(calls[0]["json"]["content"]).decode() == "hello iOS"


def test_ios_paste_text_sets_clipboard_and_inserts_text(monkeypatch):
    dev = IOSDevice("ios:abc123", appium_url="http://appium.local")
    calls = []

    monkeypatch.setattr(dev, "clipboard_set", lambda text: calls.append(("clipboard", text)) or True)
    monkeypatch.setattr(dev, "type_text", lambda text, delay=0.3: calls.append(("type", text, delay)))

    assert dev.paste_text("hello iOS") is True
    assert calls == [("clipboard", "hello iOS"), ("type", "hello iOS", 0.3)]


def test_ios_clear_active_element_uses_webdriver_clear(monkeypatch):
    calls = []

    def fake_request(method, url, json=None, timeout=None):
        calls.append({"method": method, "url": url, "json": json})
        if method == "GET" and url.endswith("/session/session-1/element/active"):
            return FakeResponse({"value": {"element-6066-11e4-a52e-4f735466cecf": "element-1"}})
        if method == "POST" and url.endswith("/session/session-1/element/element-1/clear"):
            return FakeResponse({"value": None})
        raise AssertionError(f"unexpected request: {method} {url}")

    monkeypatch.setattr("gitd.bots.common.ios.requests.request", fake_request)
    dev = IOSDevice("ios:abc123", appium_url="http://appium.local")
    dev._session_id = "session-1"

    assert dev._clear_active_element() is True
    assert [call["method"] for call in calls] == ["GET", "POST"]
    assert calls[1]["json"] == {}


def test_ios_dismiss_browser_first_run_prompts_taps_known_actions(monkeypatch):
    dev = IOSDevice("ios:abc123", appium_url="http://appium.local", bundle_id="com.google.chrome.ios")
    tapped = []
    xmls = iter(
        [
            """
            <hierarchy>
              <node class="XCUIElementTypeButton" text="Accept &amp; Continue"
                content-desc="Accept &amp; Continue" resource-id="Accept &amp; Continue"
                bounds="[20,600][360,650]" clickable="true"/>
            </hierarchy>
            """,
            """
            <hierarchy>
              <node class="XCUIElementTypeButton" text="No Thanks" content-desc="No Thanks"
                resource-id="No Thanks" bounds="[20,600][360,650]" clickable="true"/>
            </hierarchy>
            """,
            """
            <hierarchy>
              <node class="XCUIElementTypeTextField" text="Search or type web address" content-desc="Address"
                resource-id="Address" bounds="[20,60][360,104]" clickable="true"/>
            </hierarchy>
            """,
        ]
    )

    monkeypatch.setattr(dev, "dump_xml", lambda: next(xmls))
    monkeypatch.setattr(dev, "tap_node", lambda node, delay=0.5: tapped.append((dev.node_text(node), delay)) or True)

    assert dev._dismiss_browser_first_run_prompts() == 2
    assert tapped == [("Accept & Continue", 0.6), ("No Thanks", 0.6)]


def test_ios_url_address_bar_fallback_clears_before_typing(monkeypatch):
    dev = IOSDevice("ios:abc123", appium_url="http://appium.local", bundle_id="com.google.chrome.ios")
    calls = []
    xml = """
    <hierarchy>
      <node class="XCUIElementTypeTextField" text="Search or type web address" content-desc="Address"
        resource-id="Address" bounds="[20,60][360,104]" clickable="true"/>
    </hierarchy>
    """

    monkeypatch.setattr(dev, "launch_app", lambda bundle_id, delay=2.0: calls.append(("launch", bundle_id, delay)) or bundle_id)
    monkeypatch.setattr(dev, "dump_xml", lambda: xml)
    monkeypatch.setattr(dev, "tap_node", lambda node, delay=0.5: calls.append(("tap", delay)) or True)
    monkeypatch.setattr(dev, "_clear_active_element", lambda: calls.append(("clear",)) or True)
    monkeypatch.setattr(dev, "type_text", lambda text, delay=0.3: calls.append(("type", text, delay)))
    monkeypatch.setattr(dev, "press_enter", lambda delay=0.5: calls.append(("enter", delay)))

    dev._open_url_via_address_bar("https://example.com", delay=0.1)

    assert calls == [
        ("launch", "com.google.chrome.ios", 0.8),
        ("tap", 0.5),
        ("clear",),
        ("type", "https://example.com", 0.2),
        ("enter", 0.1),
    ]


def test_ios_url_address_bar_fallback_uses_ocr_when_xml_has_no_field(monkeypatch):
    dev = IOSDevice("ios:abc123", appium_url="http://appium.local", bundle_id="com.google.chrome.ios")
    calls = []

    monkeypatch.setattr(dev, "launch_app", lambda bundle_id, delay=2.0: calls.append(("launch", bundle_id, delay)) or bundle_id)
    monkeypatch.setattr(dev, "_dismiss_browser_first_run_prompts", lambda: 0)
    monkeypatch.setattr(dev, "dump_xml", lambda: "<hierarchy></hierarchy>")
    monkeypatch.setattr(
        "gitd.services.device_context.ocr_screen",
        lambda device: [{"text": "Search or type web address", "conf": 0.91, "x": 24, "y": 700, "w": 320, "h": 44}],
    )
    monkeypatch.setattr(dev, "tap", lambda x, y, delay=0.6: calls.append(("tap", x, y, delay)))
    monkeypatch.setattr(dev, "_clear_active_element", lambda: calls.append(("clear",)) or True)
    monkeypatch.setattr(dev, "type_text", lambda text, delay=0.3: calls.append(("type", text, delay)))
    monkeypatch.setattr(dev, "press_enter", lambda delay=0.5: calls.append(("enter", delay)))

    method = dev._open_url_via_address_bar("https://example.com", delay=0.1)

    assert method == "address_bar_ocr"
    assert calls == [
        ("launch", "com.google.chrome.ios", 0.8),
        ("tap", 184, 722, 0.5),
        ("clear",),
        ("type", "https://example.com", 0.2),
        ("enter", 0.1),
    ]


def test_ios_open_notifications_swipes_from_status_bar(monkeypatch):
    dev = IOSDevice("ios:abc123", appium_url="http://appium.local")
    calls = []

    monkeypatch.setattr(dev, "get_screen_size", lambda: (390, 844))
    monkeypatch.setattr(
        dev,
        "swipe",
        lambda x1, y1, x2, y2, ms=500, delay=0.5: calls.append(
            {"x1": x1, "y1": y1, "x2": x2, "y2": y2, "ms": ms, "delay": delay}
        ),
    )

    assert dev.open_notifications() is True
    assert calls == [{"x1": 195, "y1": 16, "x2": 195, "y2": 523, "ms": 650, "delay": 1.0}]


def test_ios_open_camera_launches_camera_and_taps_mode_controls(monkeypatch):
    dev = IOSDevice("ios:abc123", appium_url="http://appium.local")
    xml = """
    <hierarchy>
      <node text="Video" content-desc="Video" resource-id="Video" bounds="[10,10][90,50]"/>
      <node text="Switch Camera" content-desc="Switch Camera" resource-id="Switch Camera" bounds="[100,10][180,50]"/>
      <node text="Timer" content-desc="Timer" resource-id="Timer" bounds="[190,10][260,50]"/>
      <node text="3s" content-desc="3s" resource-id="3s" bounds="[270,10][320,50]"/>
    </hierarchy>
    """
    launched = []
    taps = []

    monkeypatch.setattr(dev, "launch_app", lambda bundle_id, delay=1.5: launched.append((bundle_id, delay)) or bundle_id)
    monkeypatch.setattr(dev, "dump_xml", lambda: xml)
    monkeypatch.setattr(dev, "tap_node", lambda node, delay=0.8: taps.append(dev.node_text(node)) or True)

    result = dev.open_camera(mode="selfie_video", timer_s=2)

    assert launched == [("com.apple.camera", 1.5)]
    assert result == {
        "platform": "ios",
        "bundle_id": "com.apple.camera",
        "mode": "selfie_video",
        "opened": True,
        "selected_mode": True,
        "switched_camera": True,
        "timer_s": 3,
        "timer_set": True,
    }
    assert taps == ["Video", "Switch Camera", "Timer", "3s"]


def test_ios_get_notifications_groups_visible_notification_center_text(monkeypatch):
    dev = IOSDevice("ios:abc123", appium_url="http://appium.local")

    monkeypatch.setattr(dev, "open_notifications", lambda delay=0.8: True)
    monkeypatch.setattr(
        dev,
        "native_text_entries",
        lambda include_controls=True, max_entries=120: [
            {"text": "Notification Center"},
            {"text": "Slack"},
            {"text": "New message from Dana"},
            {"text": "Calendar"},
            {"text": "Standup in 10 minutes"},
            {"text": "Clear"},
        ],
    )

    assert dev.get_notifications() == [
        {
            "package": "",
            "title": "Slack",
            "text": "New message from Dana",
            "time": "",
            "platform": "ios",
            "source": "notification_center",
        },
        {
            "package": "",
            "title": "Calendar",
            "text": "Standup in 10 minutes",
            "time": "",
            "platform": "ios",
            "source": "notification_center",
        },
    ]


def test_ios_clear_notifications_taps_visible_clear_control(monkeypatch):
    dev = IOSDevice("ios:abc123", appium_url="http://appium.local")
    xml = '<hierarchy><node text="Clear" content-desc="Clear" resource-id="Clear" bounds="[10,10][90,50]"/></hierarchy>'
    taps = []

    monkeypatch.setattr(dev, "open_notifications", lambda delay=0.5: True)
    monkeypatch.setattr(dev, "dump_xml", lambda: xml)
    monkeypatch.setattr(dev, "tap_node", lambda node, delay=0.8: taps.append(node) or True)

    assert dev.clear_notifications() is True
    assert len(taps) >= 1


@pytest.mark.skipif(
    not (os.getenv("IOS_APPIUM_URL") and os.getenv("IOS_DEVICE_UDID")),
    reason="set IOS_APPIUM_URL and IOS_DEVICE_UDID to run live iOS integration test",
)
def test_live_ios_screenshot_and_source():
    dev = IOSDevice(f"ios:{os.environ['IOS_DEVICE_UDID']}", appium_url=os.environ["IOS_APPIUM_URL"])
    try:
        assert len(dev.take_screenshot()) > 100
        assert "<hierarchy" in dev.dump_xml()
    finally:
        dev.close()
