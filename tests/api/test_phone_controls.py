from fastapi.testclient import TestClient

from gitd.app import app


class FakeIOSControlDevice:
    def __init__(self):
        self.calls = []

    def tap(self, x, y, *args, **kwargs):
        self.calls.append(("tap", x, y, kwargs))

    def swipe(self, x1, y1, x2, y2, *args, **kwargs):
        self.calls.append(("swipe", x1, y1, x2, y2, kwargs))

    def type_text(self, text):
        self.calls.append(("type_text", text))

    def back(self, delay=0):
        self.calls.append(("back", delay))

    def press_key(self, key):
        self.calls.append(("press_key", key))

    def launch_app(self, bundle_id):
        self.calls.append(("launch_app", bundle_id))

    def terminate_app(self, bundle_id):
        self.calls.append(("terminate_app", bundle_id))


def test_ios_control_routes_return_platform_metadata(monkeypatch):
    fake = FakeIOSControlDevice()
    monkeypatch.setattr("gitd.routers.phone.get_device", lambda device: fake)
    client = TestClient(app)

    responses = [
        client.post("/api/phone/input", json={"device": "ios:abc123", "action": "tap", "x": 11, "y": 22}),
        client.post("/api/phone/tap", json={"device": "ios:abc123", "x": 33, "y": 44}),
        client.post("/api/phone/type", json={"device": "ios:abc123", "text": "hello"}),
        client.post("/api/phone/back", json={"device": "ios:abc123"}),
        client.post("/api/phone/key", json={"device": "ios:abc123", "key": "HOME"}),
        client.post("/api/phone/force-stop", json={"device": "ios:abc123", "package": "com.google.chrome.ios"}),
        client.post("/api/phone/swipe", json={"device": "ios:abc123", "x1": 1, "y1": 2, "x2": 3, "y2": 4}),
    ]
    launch = client.post("/api/phone/launch", json={"device": "ios:abc123", "package": "com.google.chrome.ios"})

    for response in responses:
        assert response.status_code == 200
        assert response.json()["ok"] is True
        assert response.json()["device"] == "ios:abc123"
        assert response.json()["platform"] == "ios"
    assert launch.status_code == 200
    assert launch.json()["ok"] is True
    assert launch.json()["platform"] == "ios"
    assert launch.json()["package"] == "com.google.chrome.ios"
    assert launch.json()["bundle_id"] == "com.google.chrome.ios"

    assert fake.calls == [
        ("tap", 11, 22, {}),
        ("tap", 33, 44, {}),
        ("type_text", "hello"),
        ("back", 0.3),
        ("press_key", "HOME"),
        ("terminate_app", "com.google.chrome.ios"),
        ("swipe", 1, 2, 3, 4, {}),
        ("launch_app", "com.google.chrome.ios"),
    ]


def test_launch_route_requires_package(client):
    response = client.post("/api/phone/launch", json={"device": "ios:abc123"})

    assert response.status_code == 400
    assert response.json()["detail"] == "package required"
