"""Unit tests for the iOS platform matrix + RemoteXPC health-check fix (no hardware).

Covers two behaviour changes from this work:
  - speak_text is now cross-platform (native iOS TTS via the patched WDA).
  - remote_xpc_tunnel_status accepts the tunnel when devicectl reports it
    connected, instead of requiring Appium's tunnel address to equal devicectl's
    CoreDevice tunnel address (two independent tunnels that never match — the
    original false-'stale' bug that blocked the smoke test / stream).
"""

from gitd.bots.common import ios
from gitd.services.tool_platforms import supports_platform

# ── platform matrix ──────────────────────────────────────────────────────────

def test_speak_text_is_cross_platform():
    assert supports_platform("speak_text", "ios") is True
    assert supports_platform("speak_text", "android") is True


def test_shell_stays_android_only():
    assert supports_platform("shell", "android") is True
    assert supports_platform("shell", "ios") is False


# ── RemoteXPC health-check fix (F2) ──────────────────────────────────────────

def _host():
    return {"source": "host", "platform_version": "26.4.2"}


def test_tunnel_available_when_devicectl_connected(monkeypatch):
    # Registry (Appium's remotexpc tunnel) and devicectl (Apple's CoreDevice
    # tunnel) report DIFFERENT addresses — as they always do. The fixed check
    # must still report 'available' because devicectl says connected.
    def fake_registry(method, url, timeout):  # noqa: ARG001
        class R:
            status_code = 200

            @staticmethod
            def json():
                return {"status": "OK", "address": "fd23:a45d:8f2d::1"}

        return R()

    monkeypatch.setattr(ios.requests, "request", fake_registry)
    monkeypatch.setattr(
        ios, "devicectl_device_details",
        lambda udid: {"tunnel_state": "connected", "tunnel_ip_address": "fd52:b220:95a3::1"},
    )
    status = ios.remote_xpc_tunnel_status("udid", platform_version="26.4.2", host=_host())
    assert status["ok"] is True
    assert status["state"] == "available"
    # both addresses recorded, even though they differ
    assert status.get("registry_address") == "fd23:a45d:8f2d::1"
    assert status.get("current_address") == "fd52:b220:95a3::1"


def test_tunnel_stale_when_devicectl_not_connected(monkeypatch):
    def fake_registry(method, url, timeout):  # noqa: ARG001
        class R:
            status_code = 200

            @staticmethod
            def json():
                return {"status": "OK", "address": "fd23:a45d:8f2d::1"}

        return R()

    monkeypatch.setattr(ios.requests, "request", fake_registry)
    monkeypatch.setattr(
        ios, "devicectl_device_details",
        lambda udid: {"tunnel_state": "disconnected", "tunnel_ip_address": ""},
    )
    status = ios.remote_xpc_tunnel_status("udid", platform_version="26.4.2", host=_host())
    assert status["ok"] is False
    assert status["state"] == "stale"


def test_tunnel_missing_when_registry_absent(monkeypatch):
    def fake_registry(method, url, timeout):  # noqa: ARG001
        class R:
            status_code = 404

            @staticmethod
            def json():
                return {}

        return R()

    monkeypatch.setattr(ios.requests, "request", fake_registry)
    status = ios.remote_xpc_tunnel_status("udid", platform_version="26.4.2", host=_host())
    assert status["ok"] is False
    assert status["state"] == "missing"
