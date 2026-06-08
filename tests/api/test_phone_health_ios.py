import pytest


@pytest.mark.parametrize(
    ("issue", "state"),
    [
        ("start_appium", "appium_down"),
        ("check_ios_device_config", "configured_unreachable"),
        ("unlock_and_trust_device", "locked"),
        ("fix_wda_signing", "wda_signing_failed"),
    ],
)
def test_ios_health_fix_returns_manual_recovery_for_recommended_codes(client, issue, state):
    response = client.post("/api/phone/health/ios:abc123/fix", json={"issue": issue})

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["platform"] == "ios"
    assert body["issue"] == issue
    assert body["manual_action_required"] is True
    assert body["recovery"]["state"] == state
    assert body["recovery"]["code"] == issue
    assert body["recovery"]["steps"]


def test_ios_health_fix_resets_appium_session(client, monkeypatch):
    calls = []

    class FakeIOSDevice:
        def reset_session(self):
            calls.append("reset")

    monkeypatch.setattr("gitd.routers.phone.get_device", lambda device: FakeIOSDevice())

    response = client.post("/api/phone/health/ios:abc123/fix", json={"issue": "reset_session"})

    assert response.status_code == 200
    assert response.json() == {"ok": True, "platform": "ios", "message": "iOS Appium session reset"}
    assert calls == ["reset"]


def test_ios_health_fix_restarts_remote_xpc_tunnel(client, monkeypatch):
    calls = []

    class FakeIOSDevice:
        def restart_remote_xpc_tunnel(self):
            calls.append("restart")
            return {
                "ok": True,
                "platform": "ios",
                "issue": "restart_remote_xpc_tunnel",
                "pid": 1234,
            }

    monkeypatch.setattr("gitd.routers.phone.get_device", lambda device: FakeIOSDevice())

    response = client.post("/api/phone/health/ios:abc123/fix", json={"issue": "restart_remote_xpc_tunnel"})

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "platform": "ios",
        "issue": "restart_remote_xpc_tunnel",
        "pid": 1234,
    }
    assert calls == ["restart"]
