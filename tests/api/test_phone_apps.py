from fastapi.testclient import TestClient

from gitd.app import app


def test_ios_apps_endpoint_returns_searchable_bundle_inventory(monkeypatch):
    calls = []

    class FakeIOSDevice:
        def list_apps(self, query="", verify=True):
            calls.append((query, verify))
            apps = [
                {
                    "name": "Chrome",
                    "package": "com.google.chrome.ios",
                    "bundle_id": "com.google.chrome.ios",
                    "platform": "ios",
                    "verified": True,
                    "installed": True,
                    "app_state": 1,
                    "app_state_name": "not_running",
                },
                {
                    "name": "TikTok",
                    "package": "com.zhiliaoapp.musically",
                    "bundle_id": "com.zhiliaoapp.musically",
                    "platform": "ios",
                    "verified": True,
                    "installed": True,
                    "app_state": 4,
                    "app_state_name": "running_foreground",
                },
            ]
            if query:
                needle = query.lower()
                apps = [app for app in apps if needle in app["name"].lower() or needle in app["bundle_id"].lower()]
            return apps

    monkeypatch.setattr("gitd.services.device_context.get_device", lambda device: FakeIOSDevice())
    client = TestClient(app)

    listed = client.get("/api/phone/apps/ios:abc123")
    searched = client.get("/api/phone/apps/ios:abc123", params={"query": "chrome"})

    assert listed.status_code == 200
    assert searched.status_code == 200
    assert listed.json()["platform"] == "ios"
    assert listed.json()["count"] == 2
    assert listed.json()["packages"] == ["com.google.chrome.ios", "com.zhiliaoapp.musically"]
    assert searched.json()["count"] == 1
    assert searched.json()["apps"][0]["bundle_id"] == "com.google.chrome.ios"
    assert calls == [("", True), ("chrome", True)]


def test_android_apps_endpoint_normalizes_package_names(monkeypatch):
    class FakeAndroidDevice:
        def __init__(self, serial):
            self.serial = serial

        def adb(self, *args, timeout=30):
            assert args == ("shell", "pm", "list", "packages", "-3")
            return "\n".join(
                [
                    "package:com.android.chrome",
                    "package:com.example.my_app",
                ]
            )

    monkeypatch.setattr("gitd.services.device_context.Device", FakeAndroidDevice)
    client = TestClient(app)

    response = client.get("/api/phone/apps/emulator-5554", params={"query": "chrome"})

    assert response.status_code == 200
    body = response.json()
    assert body["platform"] == "android"
    assert body["packages"] == ["com.android.chrome"]
    assert body["apps"] == [
        {
            "name": "Chrome",
            "package": "com.android.chrome",
            "bundle_id": "",
            "platform": "android",
            "verified": True,
            "installed": True,
        }
    ]


def test_device_context_list_packages_uses_ios_bundle_ids(monkeypatch):
    from gitd.services.device_context import list_packages

    class FakeIOSDevice:
        def list_apps(self, query="", verify=True):
            return [
                {
                    "name": "Chrome",
                    "package": "com.google.chrome.ios",
                    "bundle_id": "com.google.chrome.ios",
                    "platform": "ios",
                }
            ]

    monkeypatch.setattr("gitd.services.device_context.get_device", lambda device: FakeIOSDevice())

    assert list_packages("ios:abc123") == ["com.google.chrome.ios"]
