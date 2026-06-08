from fastapi.testclient import TestClient

from gitd.app import app
from gitd.services import account_health


class FakeIOSAccountDevice:
    def __init__(self, text: str = "Profile\n@ghost\nFollowers\n@backup"):
        self.text = text
        self.launched = []

    def launch_app(self, bundle_id):
        self.launched.append(bundle_id)

    def extract_visible_text(self, max_lines=120):
        return self.text


def test_ios_account_health_detects_visible_handle_without_premium_probe(monkeypatch):
    def fail_premium_probe():
        raise AssertionError("premium probe should not run for iOS account health")

    account_health._cache.clear()
    monkeypatch.setattr(account_health, "_premium_available", fail_premium_probe)
    monkeypatch.setattr(account_health, "get_device", lambda device: FakeIOSAccountDevice())
    monkeypatch.setattr(account_health.time, "sleep", lambda *_args, **_kwargs: None)

    result = account_health.device_account_health("ios:abc123", fresh=True)

    assert result["ok"] is True
    assert result["device"] == "ios:abc123"
    assert result["platform"] == "ios"
    assert result["error"] is None
    assert result["active"] == "ghost"
    assert result["logged_in"] == ["ghost", "backup"]
    assert result["cached"] is False
    assert result["detection"]["method"] == "wda_visible_text"
    assert result["detection"]["bundle_id"] == "com.zhiliaoapp.musically"


def test_ios_account_health_reports_undetected_handle(monkeypatch):
    account_health._cache.clear()
    monkeypatch.setattr(account_health, "get_device", lambda device: FakeIOSAccountDevice("Profile\nNo videos yet"))
    monkeypatch.setattr(account_health.time, "sleep", lambda *_args, **_kwargs: None)

    result = account_health.device_account_health("ios:nohandle", fresh=True)

    assert result["ok"] is False
    assert result["platform"] == "ios"
    assert result["error"] == "no visible TikTok account handle detected"
    assert result["logged_in"] == []


def test_ios_account_switch_and_sync_return_unsupported():
    switch = account_health.switch_active_account("ios:abc123", "@ghost")
    sync = account_health.sync_tiktok_accounts_table("ios:abc123")

    assert switch["ok"] is False
    assert switch["platform"] == "ios"
    assert switch["error"] == "unsupported_platform"
    assert switch["target"] == "ghost"
    assert sync["ok"] is False
    assert sync["platform"] == "ios"
    assert sync["error"] == "unsupported_platform"
    assert sync["added"] == []
    assert sync["updated"] == []


def test_account_health_all_includes_ios_configured_refs(monkeypatch):
    account_health._cache.clear()
    monkeypatch.setattr("gitd.bots.common.adb.list_connected", lambda: ["emulator-5554"])
    monkeypatch.setattr("gitd.bots.common.device.ios_refs_from_host", lambda: ["ios:abc123"])
    monkeypatch.setattr(account_health, "_premium_available", lambda: False)
    monkeypatch.setattr(account_health, "get_device", lambda device: FakeIOSAccountDevice())
    monkeypatch.setattr(account_health.time, "sleep", lambda *_args, **_kwargs: None)

    results = account_health.all_devices_health()

    by_device = {item["device"]: item for item in results}
    assert set(by_device) == {"emulator-5554", "ios:abc123"}
    assert by_device["emulator-5554"]["platform"] == "android"
    assert by_device["emulator-5554"]["error"] == "premium not installed"
    assert by_device["ios:abc123"]["platform"] == "ios"
    assert by_device["ios:abc123"]["ok"] is True
    assert by_device["ios:abc123"]["active"] == "ghost"


def test_expected_account_matches_uses_ios_visible_handle(monkeypatch):
    account_health._cache.clear()
    monkeypatch.setattr(account_health, "get_device", lambda device: FakeIOSAccountDevice("Profile\n@ghost"))
    monkeypatch.setattr(account_health.time, "sleep", lambda *_args, **_kwargs: None)

    match = account_health.expected_account_matches("ios:abc123", "@ghost")
    mismatch = account_health.expected_account_matches("ios:abc123", "@other")

    assert match == {"ok": True, "reason": None, "active": "ghost", "expected": "ghost"}
    assert mismatch == {
        "ok": False,
        "reason": "wrong active account: have @ghost, expected @other",
        "active": "ghost",
        "expected": "other",
    }


def test_expected_account_matches_allows_ios_when_undetectable(monkeypatch):
    account_health._cache.clear()
    monkeypatch.setattr(account_health, "get_device", lambda device: FakeIOSAccountDevice("Profile\nNo videos yet"))
    monkeypatch.setattr(account_health.time, "sleep", lambda *_args, **_kwargs: None)

    result = account_health.expected_account_matches("ios:nohandle", "@ghost")

    assert result == {
        "ok": True,
        "reason": "undetectable: no visible TikTok account handle detected",
        "active": None,
        "expected": "ghost",
    }


def test_scheduler_account_health_routes_return_ios_detection(monkeypatch):
    account_health._cache.clear()
    monkeypatch.setattr(account_health, "get_device", lambda device: FakeIOSAccountDevice())
    monkeypatch.setattr(account_health.time, "sleep", lambda *_args, **_kwargs: None)
    client = TestClient(app)

    health = client.get("/api/scheduler/account-health/ios:abc123")
    switch = client.post("/api/scheduler/account-switch/ios:abc123", json={"handle": "@ghost"})
    sync = client.post("/api/scheduler/account-sync/ios:abc123")

    assert health.status_code == 200
    assert health.json()["ok"] is True
    assert health.json()["platform"] == "ios"
    assert health.json()["active"] == "ghost"
    assert switch.status_code == 200
    assert switch.json()["error"] == "unsupported_platform"
    assert switch.json()["platform"] == "ios"
    assert sync.status_code == 200
    assert sync.json()["error"] == "unsupported_platform"
    assert sync.json()["platform"] == "ios"
