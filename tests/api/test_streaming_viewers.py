from fastapi.testclient import TestClient

from gitd.app import app


def test_ios_webrtc_viewer_renders_wda_mjpeg_image_without_adb(monkeypatch):
    def fail_adb(*args, **kwargs):
        raise AssertionError("iOS viewer should not run adb forwarding")

    monkeypatch.setattr("gitd.routers.streaming_viewers.subprocess.run", fail_adb)

    response = TestClient(app).get("/api/phone/webrtc-viewer?device=ios:abc123")

    assert response.status_code == 200
    body = response.text
    assert 'src="/api/phone/stream?device=ios%3Aabc123&amp;fps=10&amp;mode=wda-mjpeg"' in body
    assert "<img" in body
    assert "ios" in body
    assert "wda-mjpeg" in body
    assert "<video" not in body


def test_ios_webrtc_multi_viewer_renders_wda_mjpeg_image_without_adb(monkeypatch):
    def fail_adb(*args, **kwargs):
        raise AssertionError("iOS multi-viewer should not run adb forwarding")

    monkeypatch.setattr("gitd.routers.streaming_viewers.subprocess.run", fail_adb)

    response = TestClient(app).get("/api/phone/webrtc-multi?device=ios:abc123")

    assert response.status_code == 200
    body = response.text
    assert '"platform": "ios"' in body
    assert '"mode": "wda-mjpeg"' in body
    assert '"streamUrl": "/api/phone/stream?device=ios%3Aabc123&fps=10&mode=wda-mjpeg"' in body
    assert "d.platform === 'ios'" in body


def test_mixed_webrtc_multi_viewer_only_sets_up_android_adb(monkeypatch):
    adb_devices = []
    adb_forwards = []

    class FakeAdbDevice:
        def __init__(self, serial):
            adb_devices.append(serial)

        def _ensure_portal_forward(self):
            return 18000

    def fake_run(cmd, capture_output=False, timeout=None):
        adb_forwards.append(cmd)

        class Result:
            returncode = 0

        return Result()

    monkeypatch.setattr("gitd.bots.common.adb.Device", FakeAdbDevice)
    monkeypatch.setattr("gitd.routers.streaming_viewers.subprocess.run", fake_run)

    response = TestClient(app).get("/api/phone/webrtc-multi?device=ios:abc123&device=emulator-5554")

    assert response.status_code == 200
    assert adb_devices == ["emulator-5554"]
    assert len(adb_forwards) == 1
    assert adb_forwards[0][:3] == ["adb", "-s", "emulator-5554"]
    body = response.text
    assert '"serial": "ios:abc123"' in body
    assert '"platform": "ios"' in body
    assert '"serial": "emulator-5554"' in body
    assert '"platform": "android"' in body
