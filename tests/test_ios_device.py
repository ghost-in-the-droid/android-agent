import base64
import json
import os

import pytest

from gitd.bots.common.device import get_device, ios_refs_from_env, platform_for_device
from gitd.bots.common.ios import (
    IOSDevice,
    configured_ios_udids,
    ios_config_for_udid,
    ios_xml_to_elements,
    normalize_wda_xml,
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

    assert platform_for_device("ios:abc123") == "ios"
    assert platform_for_device("emulator-5554") == "android"
    assert ios_refs_from_env() == ["ios:abc123"]
    dev = get_device("ios:abc123")
    assert isinstance(dev, IOSDevice)
    assert dev.udid == "abc123"


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
                    "mjpeg_server_port": 9101,
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
    assert cfg.mjpeg_server_port == 9101
    assert cfg.capabilities()["appium:mjpegServerPort"] == 9101
    assert cfg.capabilities()["appium:wdaLaunchTimeout"] == 180000
    assert cfg.capabilities()["appium:allowProvisioningDeviceRegistration"] is True


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


def test_probe_classifies_unreachable_appium(monkeypatch):
    def fake_request(method, url, json=None, timeout=None):
        raise __import__("requests").ConnectionError("connection refused")

    monkeypatch.setattr("gitd.bots.common.ios.requests.request", fake_request)
    status = IOSDevice("ios:abc123", appium_url="http://appium.local").probe(deep=True)

    assert status.state == "appium_down"
    assert "unreachable" in status.message.lower()


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
