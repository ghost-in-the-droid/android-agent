from fastapi.testclient import TestClient

from gitd.app import app
from gitd.services import account_health


def test_ios_account_health_returns_unsupported_without_premium_probe(monkeypatch):
    def fail_premium_probe():
        raise AssertionError("premium probe should not run for iOS account health")

    monkeypatch.setattr(account_health, "_premium_available", fail_premium_probe)

    result = account_health.device_account_health("ios:abc123", fresh=True)

    assert result["ok"] is False
    assert result["device"] == "ios:abc123"
    assert result["platform"] == "ios"
    assert result["error"] == "unsupported_platform"
    assert result["active"] is None
    assert result["logged_in"] == []
    assert result["cached"] is False
    assert "Android-only" in result["message"]


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
    monkeypatch.setattr("gitd.bots.common.adb.list_connected", lambda: ["emulator-5554"])
    monkeypatch.setattr("gitd.bots.common.device.ios_refs_from_host", lambda: ["ios:abc123"])
    monkeypatch.setattr(account_health, "_premium_available", lambda: False)

    results = account_health.all_devices_health()

    by_device = {item["device"]: item for item in results}
    assert set(by_device) == {"emulator-5554", "ios:abc123"}
    assert by_device["emulator-5554"]["platform"] == "android"
    assert by_device["emulator-5554"]["error"] == "premium not installed"
    assert by_device["ios:abc123"]["platform"] == "ios"
    assert by_device["ios:abc123"]["error"] == "unsupported_platform"


def test_expected_account_matches_does_not_block_ios_jobs():
    result = account_health.expected_account_matches("ios:abc123", "@ghost")

    assert result == {
        "ok": True,
        "reason": "undetectable: iOS TikTok account health is not implemented yet",
        "active": None,
        "expected": "ghost",
    }


def test_scheduler_account_health_routes_return_ios_unsupported():
    client = TestClient(app)

    health = client.get("/api/scheduler/account-health/ios:abc123")
    switch = client.post("/api/scheduler/account-switch/ios:abc123", json={"handle": "@ghost"})
    sync = client.post("/api/scheduler/account-sync/ios:abc123")

    assert health.status_code == 200
    assert health.json()["error"] == "unsupported_platform"
    assert health.json()["platform"] == "ios"
    assert switch.status_code == 200
    assert switch.json()["error"] == "unsupported_platform"
    assert switch.json()["platform"] == "ios"
    assert sync.status_code == 200
    assert sync.json()["error"] == "unsupported_platform"
    assert sync.json()["platform"] == "ios"
