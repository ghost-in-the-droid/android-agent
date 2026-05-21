"""
Emulator API tests — Docker+KVM backend.

All tests use FastAPI TestClient (no real Docker daemon needed for route shape
tests). Tests that actually create containers are skipped unless DOCKER_EMU_TEST=1.
"""

import os

import pytest


class TestEmulatorPrerequisites:
    def test_prerequisites_shape(self, client):
        r = client.get("/api/emulators/prerequisites")
        assert r.status_code == 200
        data = r.json()
        assert data["backend"] == "docker"
        assert isinstance(data["docker_available"], bool)
        assert isinstance(data["kvm_available"], bool)
        assert isinstance(data["adb_binary"], bool)

    def test_prerequisites_has_docker_info(self, client):
        r = client.get("/api/emulators/prerequisites")
        data = r.json()
        assert "image" in data
        assert "budtmo" in data["image"]


class TestEmulatorList:
    def test_list_empty(self, client):
        r = client.get("/api/emulators")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_list_running(self, client):
        r = client.get("/api/emulators/running")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_list_system_images(self, client):
        r = client.get("/api/emulators/system-images")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


class TestEmulatorCreate:
    def test_create_missing_name(self, client):
        r = client.post("/api/emulators", json={})
        assert r.status_code == 422

    def test_create_returns_ok_or_docker_error(self, client):
        """Create call reaches the backend; passes if Docker is up, skips if not."""
        import uuid

        name = f"ci-test-{uuid.uuid4().hex[:8]}"
        try:
            r = client.post("/api/emulators", json={"name": name})
            assert r.status_code in (200, 201)
            data = r.json()
            assert "ok" in data
            if data["ok"]:
                assert "serial" in data
                assert data["serial"].startswith("localhost:")
        finally:
            client.delete(f"/api/emulators/{name}")


class TestEmulatorLifecycle:
    """Full create→boot→stop→delete cycle. Requires DOCKER_EMU_TEST=1."""

    @pytest.fixture(autouse=True)
    def require_docker_test(self):
        if not os.environ.get("DOCKER_EMU_TEST"):
            pytest.skip("set DOCKER_EMU_TEST=1 to run live Docker emulator tests")

    def test_full_lifecycle(self, client):
        name = "pytest-emu-lifecycle"

        # Create
        r = client.post("/api/emulators", json={"name": name, "api_level": 30})
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True, f"create failed: {data}"
        serial = data["serial"]
        assert serial == "localhost:5555"

        # List — should appear
        r = client.get("/api/emulators")
        names = [e["name"] for e in r.json()]
        assert name in names

        # Boot status
        r = client.get(f"/api/emulators/{name}/boot-status")
        assert r.status_code == 200
        boot = r.json()
        assert "boot_completed" in boot

        # Stop
        r = client.post(f"/api/emulators/{name}/stop")
        assert r.status_code == 200
        assert r.json()["ok"] is True

        # Delete
        r = client.delete(f"/api/emulators/{name}")
        assert r.status_code == 200
        assert r.json()["ok"] is True

        # List — should be gone
        r = client.get("/api/emulators")
        names = [e["name"] for e in r.json()]
        assert name not in names


class TestEmulatorPool:
    def test_pool_status(self, client):
        r = client.get("/api/emulator-pool/status")
        assert r.status_code == 200

    def test_pool_resources(self, client):
        r = client.get("/api/emulator-pool/resources")
        assert r.status_code == 200


class TestEmulatorServiceUnit:
    """Unit tests for EmulatorManager and helpers — no HTTP, no Docker."""

    def test_check_prerequisites(self):
        from gitd.services.emulator_service import EmulatorManager

        m = EmulatorManager()
        result = m.check_prerequisites()
        assert result["backend"] == "docker"
        assert isinstance(result["docker_available"], bool)
        assert isinstance(result["kvm_available"], bool)

    def test_list_avds_returns_list(self):
        from gitd.services.emulator_service import EmulatorManager

        m = EmulatorManager()
        avds = m.list_avds()
        assert isinstance(avds, list)

    def test_list_running_returns_list(self):
        from gitd.services.emulator_service import EmulatorManager

        m = EmulatorManager()
        running = m.list_running()
        assert isinstance(running, list)

    def test_delete_nonexistent_graceful(self):
        from gitd.services.emulator_service import EmulatorManager

        m = EmulatorManager()
        result = m.delete("does-not-exist-xyz")
        assert "ok" in result
        assert result["ok"] is False

    def test_stop_nonexistent_graceful(self):
        from gitd.services.emulator_service import EmulatorManager

        m = EmulatorManager()
        result = m.stop("localhost:59999")
        assert "ok" in result

    def test_emulator_config_defaults(self):
        from gitd.services._emulator_helpers import EmulatorConfig

        c = EmulatorConfig(name="test")
        assert c.api_level == 30
        assert c.ram_mb == 2048
        assert c.arch == "x86_64"

    def test_has_docker_returns_bool(self):
        from gitd.services._emulator_helpers import _has_docker

        assert isinstance(_has_docker(), bool)

    def test_has_kvm_returns_bool(self):
        from gitd.services._emulator_helpers import _has_kvm

        assert isinstance(_has_kvm(), bool)

    def test_snapshot_returns_advisory(self):
        from gitd.services.emulator_service import EmulatorManager

        m = EmulatorManager()
        result = m.snapshot_save("localhost:5555", "test-snap")
        assert result["ok"] is False
        assert "not supported" in result["error"].lower()
