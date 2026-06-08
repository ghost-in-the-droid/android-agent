"""Smoke tests — one test per public router, verifying 200 OK and basic shape."""


class TestHealth:
    def test_health(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["server"] == "fastapi"


class TestFeatures:
    def test_features(self, client):
        r = client.get("/api/features")
        assert r.status_code == 200
        assert "premium_tabs" in r.json()


class TestBot:
    def test_status(self, client):
        r = client.get("/api/bot/status")
        assert r.status_code == 200

    def test_queue(self, client):
        r = client.get("/api/bot/queue")
        assert r.status_code == 200

    def test_history(self, client):
        r = client.get("/api/bot/history")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


class TestTests:
    def test_catalog(self, client):
        r = client.get("/api/tests")
        assert r.status_code == 200

    def test_recordings(self, client):
        r = client.get("/api/test-runner/recordings")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


class TestExplorer:
    def test_runs(self, client):
        r = client.get("/api/explorer/runs")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_status(self, client):
        r = client.get("/api/explorer/status")
        assert r.status_code == 200


class TestScheduler:
    def test_list(self, client):
        r = client.get("/api/schedules")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_queue(self, client):
        r = client.get("/api/scheduler/queue")
        assert r.status_code == 200

    def test_history(self, client):
        r = client.get("/api/scheduler/history")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


class TestPhone:
    def test_devices(self, client):
        r = client.get("/api/phone/devices")
        assert r.status_code == 200
        assert "devices" in r.json()

    def test_devices_deep_probe_query_reaches_ios_listing(self, client, monkeypatch):
        calls = []

        monkeypatch.setattr("gitd.routers.phone._try_wifi_reconnect", lambda db: None)
        monkeypatch.setattr("gitd.routers.phone.subprocess.check_output", lambda *args, **kwargs: b"List of devices attached\n")

        def fake_ios_devices(deep_probe=False):
            calls.append(deep_probe)
            return [{"serial": "ios:abc123", "model": "iPhone", "connection": "appium-wda", "platform": "ios"}]

        monkeypatch.setattr("gitd.routers.phone.list_configured_ios_devices", fake_ios_devices)

        r = client.get("/api/phone/devices?probe=deep")

        assert r.status_code == 200
        assert calls == [True]
        assert r.json()["devices"][0]["serial"] == "ios:abc123"


class TestSkills:
    def test_list(self, client):
        r = client.get("/api/skills")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


class TestCreator:
    def test_ollama_models(self, client):
        r = client.get("/api/creator/ollama-models")
        assert r.status_code in (200, 500)
