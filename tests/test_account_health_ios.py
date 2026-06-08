from fastapi.testclient import TestClient

from gitd.app import app
from gitd.db import get_connection
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


def test_ios_account_switch_succeeds_when_target_already_active(monkeypatch):
    account_health._cache.clear()
    monkeypatch.setattr(account_health, "get_device", lambda device: FakeIOSAccountDevice())
    monkeypatch.setattr(account_health.time, "sleep", lambda *_args, **_kwargs: None)

    switch = account_health.switch_active_account("ios:abc123", "@ghost")

    assert switch["ok"] is True
    assert switch["platform"] == "ios"
    assert switch["error"] is None
    assert switch["active"] == "ghost"
    assert switch["target"] == "ghost"
    assert switch["logged_in"] == ["ghost", "backup"]
    assert switch["switched"] is False
    assert switch["message"] == "target TikTok account is already active on iOS"


def test_ios_account_switch_returns_context_when_switch_needed(monkeypatch):
    account_health._cache.clear()
    monkeypatch.setattr(account_health, "get_device", lambda device: FakeIOSAccountDevice())
    monkeypatch.setattr(account_health.time, "sleep", lambda *_args, **_kwargs: None)

    switch = account_health.switch_active_account("ios:abc123", "@backup")

    assert switch["ok"] is False
    assert switch["platform"] == "ios"
    assert switch["error"] == "unsupported_platform"
    assert switch["active"] == "ghost"
    assert switch["target"] == "backup"
    assert switch["logged_in"] == ["ghost", "backup"]
    assert switch["health_ok"] is True
    assert switch["health_error"] is None


def test_ios_account_switch_returns_health_error_when_undetectable(monkeypatch):
    account_health._cache.clear()
    monkeypatch.setattr(account_health, "get_device", lambda device: FakeIOSAccountDevice("Profile\nNo videos yet"))
    monkeypatch.setattr(account_health.time, "sleep", lambda *_args, **_kwargs: None)

    switch = account_health.switch_active_account("ios:nohandle", "@ghost")

    assert switch["ok"] is False
    assert switch["platform"] == "ios"
    assert switch["error"] == "unsupported_platform"
    assert switch["active"] is None
    assert switch["target"] == "ghost"
    assert switch["logged_in"] == []
    assert switch["health_ok"] is False
    assert switch["health_error"] == "no visible TikTok account handle detected"


def test_ios_account_sync_writes_detected_handles(tmp_path, monkeypatch):
    db_path = tmp_path / "gitd.db"
    account_health._cache.clear()
    monkeypatch.setattr("gitd.db.DEFAULT_DB", db_path)
    monkeypatch.setattr(account_health, "get_device", lambda device: FakeIOSAccountDevice())
    monkeypatch.setattr(account_health.time, "sleep", lambda *_args, **_kwargs: None)

    sync = account_health.sync_tiktok_accounts_table("ios:abc123")

    assert sync["ok"] is True
    assert sync["platform"] == "ios"
    assert sync["added"] == ["ghost", "backup"]
    assert sync["updated"] == []
    assert sync["active"] == "ghost"
    assert sync["error"] is None

    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT handle, phone_serial, is_active FROM tiktok_accounts ORDER BY handle"
        ).fetchall()
    finally:
        conn.close()
    assert [dict(row) for row in rows] == [
        {"handle": "backup", "phone_serial": "ios:abc123", "is_active": 1},
        {"handle": "ghost", "phone_serial": "ios:abc123", "is_active": 1},
    ]


def test_ios_account_sync_reports_detection_failure(tmp_path, monkeypatch):
    account_health._cache.clear()
    monkeypatch.setattr("gitd.db.DEFAULT_DB", tmp_path / "gitd.db")
    monkeypatch.setattr(account_health, "get_device", lambda device: FakeIOSAccountDevice("Profile\nNo videos yet"))
    monkeypatch.setattr(account_health.time, "sleep", lambda *_args, **_kwargs: None)

    sync = account_health.sync_tiktok_accounts_table("ios:nohandle")

    assert sync["ok"] is False
    assert sync["platform"] == "ios"
    assert sync["error"] == "no visible TikTok account handle detected"
    assert sync["added"] == []
    assert sync["updated"] == []
    assert sync["active"] is None


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


def test_scheduler_account_health_routes_return_ios_detection(tmp_path, monkeypatch):
    account_health._cache.clear()
    monkeypatch.setattr("gitd.db.DEFAULT_DB", tmp_path / "gitd.db")
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
    assert switch.json()["ok"] is True
    assert switch.json()["error"] is None
    assert switch.json()["platform"] == "ios"
    assert switch.json()["active"] == "ghost"
    assert sync.status_code == 200
    assert sync.json()["ok"] is True
    assert sync.json()["platform"] == "ios"
    assert sync.json()["added"] == ["ghost", "backup"]
