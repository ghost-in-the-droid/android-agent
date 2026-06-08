from fastapi.testclient import TestClient

from gitd.app import app


def test_ios_clipboard_rest_routes_use_device_context(monkeypatch):
    calls = []

    monkeypatch.setattr("gitd.services.device_context.clipboard_get", lambda device: "hello iOS")
    monkeypatch.setattr(
        "gitd.services.device_context.clipboard_set",
        lambda device, text: calls.append((device, text)) or True,
    )
    client = TestClient(app)

    read = client.get("/api/phone/clipboard/ios:abc123")
    wrote = client.post("/api/phone/clipboard", json={"device": "ios:abc123", "text": "new text"})

    assert read.status_code == 200
    assert read.json() == {"ok": True, "device": "ios:abc123", "platform": "ios", "text": "hello iOS"}
    assert wrote.status_code == 200
    assert wrote.json() == {"ok": True, "device": "ios:abc123", "platform": "ios"}
    assert calls == [("ios:abc123", "new text")]


def test_ios_paste_text_rest_route_uses_ios_backend(monkeypatch):
    calls = []

    class FakeIOSDevice:
        def paste_text(self, text):
            calls.append(text)
            return True

    monkeypatch.setattr("gitd.routers.phone.get_device", lambda device: FakeIOSDevice())
    client = TestClient(app)

    response = client.post("/api/phone/paste-text", json={"device": "ios:abc123", "text": "paste me"})

    assert response.status_code == 200
    assert response.json() == {"ok": True, "device": "ios:abc123", "platform": "ios"}
    assert calls == ["paste me"]


def test_ios_notifications_rest_routes_use_device_context(monkeypatch):
    monkeypatch.setattr(
        "gitd.services.device_context.get_notifications",
        lambda device: [{"title": "Slack", "text": "New message", "platform": "ios"}],
    )
    monkeypatch.setattr("gitd.services.device_context.open_notifications", lambda device: True)
    monkeypatch.setattr("gitd.services.device_context.clear_notifications", lambda device: True)
    client = TestClient(app)

    listed = client.get("/api/phone/notifications/ios:abc123")
    opened = client.post("/api/phone/notifications/open", json={"device": "ios:abc123"})
    cleared = client.post("/api/phone/notifications/clear", json={"device": "ios:abc123"})

    assert listed.status_code == 200
    assert listed.json() == {
        "ok": True,
        "device": "ios:abc123",
        "platform": "ios",
        "notifications": [{"title": "Slack", "text": "New message", "platform": "ios"}],
        "count": 1,
    }
    assert opened.json() == {"ok": True, "device": "ios:abc123", "platform": "ios"}
    assert cleared.json() == {"ok": True, "device": "ios:abc123", "platform": "ios"}


def test_clipboard_and_notification_mutations_require_device():
    client = TestClient(app)

    assert client.post("/api/phone/clipboard", json={"text": "x"}).status_code == 400
    assert client.post("/api/phone/paste-text", json={"text": "x"}).status_code == 400
    assert client.post("/api/phone/notifications/open", json={}).status_code == 400
    assert client.post("/api/phone/notifications/clear", json={}).status_code == 400
