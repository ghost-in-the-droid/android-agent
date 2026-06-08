from gitd.routers.streaming import _webrtc_signal_sync, phone_stream, webrtc_ws_poll, webrtc_ws_send


class FakeIOSStreamDevice:
    mjpeg_url = "http://127.0.0.1:9123"
    mjpeg_settings = {
        "mjpegServerFramerate": 12,
        "mjpegScalingFactor": 60.0,
        "mjpegServerScreenshotQuality": 45,
    }


def test_ios_stream_headers_expose_effective_wda_mjpeg_mode(monkeypatch):
    monkeypatch.setattr("gitd.routers.streaming.get_device", lambda device: FakeIOSStreamDevice())

    response = phone_stream(device="ios:abc123", fps=99, mode="mjpeg")

    assert response.headers["x-phone-platform"] == "ios"
    assert response.headers["x-phone-stream-mode"] == "wda-mjpeg"
    assert response.headers["x-phone-stream-fallback-mode"] == "screenshot-polling"
    assert response.headers["x-phone-health-url"] == "/api/phone/health/ios:abc123"
    assert response.headers["x-phone-health-fix-url"] == "/api/phone/health/ios:abc123/fix"
    assert response.headers["x-phone-mjpeg-url"] == "http://127.0.0.1:9123"
    assert response.headers["x-phone-mjpeg-settings"] == (
        '{"mjpegScalingFactor": 60.0, "mjpegServerFramerate": 12, "mjpegServerScreenshotQuality": 45}'
    )


def test_ios_stream_headers_expose_screenshot_polling_fallback_mode(monkeypatch):
    monkeypatch.setattr("gitd.routers.streaming.get_device", lambda device: FakeIOSStreamDevice())

    response = phone_stream(device="ios:abc123", fps=5, mode="screencap")

    assert response.headers["x-phone-platform"] == "ios"
    assert response.headers["x-phone-stream-mode"] == "screenshot-polling"


def test_android_stream_headers_expose_effective_mode():
    response = phone_stream(device="emulator-5554", fps=5, mode="h264")

    assert response.headers["x-phone-platform"] == "android"
    assert response.headers["x-phone-stream-mode"] == "h264"
    assert response.headers["x-phone-health-url"] == "/api/phone/health/emulator-5554"
    assert response.headers["x-phone-health-fix-url"] == "/api/phone/health/emulator-5554/fix"


def test_ios_webrtc_signal_returns_wda_stream_fallback():
    response = _webrtc_signal_sync({"device": "ios:abc123", "method": "stream/start", "params": {}})

    assert response["ok"] is False
    assert response["platform"] == "ios"
    assert "WebRTC" in response["error"]
    assert response["stream_fallback"]["recommended_mode"] == "mjpeg"
    assert response["stream_fallback"]["url"] == "/api/phone/stream?device=ios:abc123&mode=mjpeg"
    assert response["recovery"]["health_endpoint"] == "/api/phone/health/ios:abc123"
    assert response["recovery"]["fix_endpoint"] == "/api/phone/health/ios:abc123/fix"
    assert response["recovery"]["fix_tool"] == "fix_device_health"
    assert "restart_remote_xpc_tunnel" in response["recovery"]["common_fixes"]


def test_ios_webrtc_ws_send_returns_wda_stream_fallback():
    response = webrtc_ws_send({"device": "ios:abc123", "message": {"type": "ping"}})

    assert response["ok"] is False
    assert response["platform"] == "ios"
    assert "Portal WebSocket" in response["error"]
    assert response["stream_fallback"]["fallback_mode"] == "screencap"


def test_ios_webrtc_ws_poll_returns_wda_stream_fallback():
    response = webrtc_ws_poll({"device": "ios:abc123"})

    assert response["ok"] is False
    assert response["platform"] == "ios"
    assert "Portal WebSocket polling" in response["error"]
    assert response["stream_fallback"]["endpoint"] == "/api/phone/stream"
