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


def test_ios_clipboard_and_notification_errors_are_structured(monkeypatch):
    class FailingIOSDevice:
        def paste_text(self, *_args, **_kwargs):
            raise RuntimeError("wda paste failed")

    monkeypatch.setattr("gitd.routers.phone.get_device", lambda device: FailingIOSDevice())
    monkeypatch.setattr(
        "gitd.services.device_context.clipboard_get",
        lambda device: (_ for _ in ()).throw(RuntimeError("wda clipboard get failed")),
    )
    monkeypatch.setattr(
        "gitd.services.device_context.clipboard_set",
        lambda device, text: (_ for _ in ()).throw(RuntimeError("wda clipboard set failed")),
    )
    monkeypatch.setattr(
        "gitd.services.device_context.get_notifications",
        lambda device: (_ for _ in ()).throw(RuntimeError("wda notifications list failed")),
    )
    monkeypatch.setattr(
        "gitd.services.device_context.open_notifications",
        lambda device: (_ for _ in ()).throw(RuntimeError("wda notifications open failed")),
    )
    monkeypatch.setattr(
        "gitd.services.device_context.clear_notifications",
        lambda device: (_ for _ in ()).throw(RuntimeError("wda notifications clear failed")),
    )
    client = TestClient(app)

    cases = [
        (client.get("/api/phone/clipboard/ios:abc123"), "wda clipboard get failed"),
        (client.post("/api/phone/clipboard", json={"device": "ios:abc123", "text": "new text"}), "wda clipboard set failed"),
        (client.post("/api/phone/paste-text", json={"device": "ios:abc123", "text": "paste me"}), "wda paste failed"),
        (client.get("/api/phone/notifications/ios:abc123"), "wda notifications list failed"),
        (client.post("/api/phone/notifications/open", json={"device": "ios:abc123"}), "wda notifications open failed"),
        (client.post("/api/phone/notifications/clear", json={"device": "ios:abc123"}), "wda notifications clear failed"),
    ]

    for response, error in cases:
        assert response.status_code == 200
        assert response.json() == {
            "ok": False,
            "device": "ios:abc123",
            "platform": "ios",
            "error": error,
        }


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
