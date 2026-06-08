import json

from fastapi.testclient import TestClient

from gitd.app import app
from gitd.services.agent_tools import execute_tool, tools_for_device
from gitd.services.tool_platforms import supports_platform, tool_platform_info


def test_ios_app_state_normalizes_query_app_state(monkeypatch):
    from gitd.services.device_context import app_state

    class FakeIOSDevice:
        def app_state(self, package):
            assert package == "com.google.chrome.ios"
            return 4

    monkeypatch.setattr("gitd.services.device_context.get_device", lambda device: FakeIOSDevice())

    result = app_state("ios:abc123", "com.google.chrome.ios")

    assert result == {
        "ok": True,
        "device": "ios:abc123",
        "platform": "ios",
        "package": "com.google.chrome.ios",
        "bundle_id": "com.google.chrome.ios",
        "state": "running_foreground",
        "raw_state": 4,
        "installed": True,
        "running": True,
        "foreground": True,
        "source": "appium_queryAppState",
    }


def test_android_app_state_uses_package_pid_and_foreground_window(monkeypatch):
    from gitd.services.device_context import app_state

    class FakeAndroidDevice:
        def __init__(self, serial):
            self.serial = serial

        def adb(self, *args, timeout=30):
            if args[:4] == ("shell", "dumpsys", "window", "windows"):
                return "mCurrentFocus=Window{abc u0 com.example.app/.MainActivity}"
            if args[:3] == ("shell", "pm", "path"):
                return "package:/data/app/com.example.app/base.apk"
            if args[:3] == ("shell", "pidof", "com.example.app"):
                return ""
            return ""

    monkeypatch.setattr("gitd.services.device_context.Device", FakeAndroidDevice)

    result = app_state("emulator-5554", "com.example.app")

    assert result["platform"] == "android"
    assert result["state"] == "running_foreground"
    assert result["raw_state"] == 4
    assert result["installed"] is True
    assert result["running"] is True
    assert result["foreground"] is True
    assert result["current_package"] == "com.example.app"


def test_app_state_rest_routes_use_device_context(monkeypatch):
    calls = []

    def fake_app_state(device, package):
        calls.append((device, package))
        return {
            "ok": True,
            "device": device,
            "platform": "ios",
            "package": package,
            "bundle_id": package,
            "state": "not_running",
            "raw_state": 1,
            "installed": True,
            "running": False,
            "foreground": False,
            "source": "appium_queryAppState",
        }

    monkeypatch.setattr("gitd.services.device_context.app_state", fake_app_state)
    client = TestClient(app)

    read = client.get("/api/phone/app-state/ios:abc123", params={"package": "com.google.chrome.ios"})
    posted = client.post(
        "/api/phone/app-state",
        json={"device": "ios:abc123", "package": "com.google.chrome.ios"},
    )

    assert read.status_code == 200
    assert posted.status_code == 200
    assert read.json()["state"] == "not_running"
    assert posted.json()["state"] == "not_running"
    assert calls == [
        ("ios:abc123", "com.google.chrome.ios"),
        ("ios:abc123", "com.google.chrome.ios"),
    ]


def test_app_state_rest_routes_validate_required_fields():
    client = TestClient(app)

    assert client.get("/api/phone/app-state/ios:abc123").status_code == 400
    assert client.post("/api/phone/app-state", json={"device": "ios:abc123"}).status_code == 400


def test_app_state_agent_and_platform_registry(monkeypatch):
    monkeypatch.setattr(
        "gitd.services.agent_tools.ctx.app_state",
        lambda device, package: {
            "ok": True,
            "device": device,
            "platform": "ios",
            "package": package,
            "state": "running_foreground",
        },
    )

    result = json.loads(execute_tool("app_state", {"device": "ios:abc123", "package": "com.google.chrome.ios"}))
    ios_tools = {tool["name"] for tool in tools_for_device("ios:abc123")}
    android_tools = {tool["name"] for tool in tools_for_device("emulator-5554")}

    assert result["state"] == "running_foreground"
    assert "app_state" in ios_tools
    assert "app_state" in android_tools
    assert supports_platform("app_state", "ios") is True
    assert tool_platform_info("app_state").support == "cross_platform"


def test_tools_hub_exposes_app_state_and_paste_text():
    client = TestClient(app)

    response = client.get("/api/tools")

    assert response.status_code == 200
    categories = {category["category"]: category["tools"] for category in response.json()}
    app_tools = {tool["name"]: tool for tool in categories["App Management"]}
    clipboard_tools = {tool["name"]: tool for tool in categories["Clipboard & Notifications"]}

    assert app_tools["app_state"]["platform_support"]["support"] == "cross_platform"
    assert app_tools["app_state"]["platform_support"]["ios"] is True
    assert clipboard_tools["paste_text"]["platform_support"]["support"] == "cross_platform"
    assert clipboard_tools["paste_text"]["platform_support"]["ios"] is True
