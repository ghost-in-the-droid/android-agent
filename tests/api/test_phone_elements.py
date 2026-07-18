from fastapi.testclient import TestClient

from gitd.app import app


def test_ios_elements_endpoint_includes_screen_size(monkeypatch):
    class FakeIOSDevice:
        def get_screen_size(self):
            return (393, 852)

    monkeypatch.setattr(
        "gitd.services.device_context.get_interactive_elements",
        lambda device: [
            {
                "idx": 0,
                "text": "Search",
                "bounds": {"x1": 10, "y1": 20, "x2": 200, "y2": 64},
                "center": {"x": 105, "y": 42},
            }
        ],
    )
    monkeypatch.setattr("gitd.routers.phone.get_device", lambda device: FakeIOSDevice())
    client = TestClient(app)

    response = client.get("/api/phone/elements/ios:abc123")

    assert response.status_code == 200
    body = response.json()
    assert body["platform"] == "ios"
    assert body["screen_size"] == {"width": 393, "height": 852}
    assert body["count"] == 1
    assert body["elements"][0]["text"] == "Search"


def test_android_elements_endpoint_includes_screen_size(monkeypatch):
    class FakeAndroidDevice:
        def __init__(self, serial):
            self.serial = serial

        def adb(self, *args, timeout=30):
            assert args == ("shell", "wm", "size")
            return "Physical size: 1080x2400"

    monkeypatch.setattr("gitd.services.device_context.get_interactive_elements", lambda device: [])
    monkeypatch.setattr("gitd.bots.common.adb.Device", FakeAndroidDevice)
    client = TestClient(app)

    response = client.get("/api/phone/elements/emulator-5554")

    assert response.status_code == 200
    body = response.json()
    assert body["platform"] == "android"
    assert body["screen_size"] == {"width": 1080, "height": 2400}
    assert body["count"] == 0
