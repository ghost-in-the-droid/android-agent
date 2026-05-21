"""
Emulator Service — Docker+KVM lifecycle management (create/start/stop/delete/snapshots).

Replaces the native Android SDK AVD backend with budtmo/docker-android containers.
Discovery helpers live in _emulator_helpers; pool logic in _emulator_pool.
"""

import logging
import subprocess
import threading
import time
from dataclasses import asdict
from pathlib import Path
from typing import Optional

import gitd.services._emulator_helpers as _eh
from gitd.services._emulator_helpers import (
    ADB_BIN,
    DOCKER_IMAGE,
    EmulatorConfig,  # noqa: F401 — re-exported for routers
    _adb,
    _docker,
    _has_docker,
    _has_kvm,
    _run,
    next_available_port,
)
from gitd.services._emulator_pool import EmulatorPool

logger = logging.getLogger(__name__)

# ── EmulatorManager ───────────────────────────────────────────────────────────


class EmulatorManager:
    """Manage Android emulator lifecycle via Docker+KVM."""

    def __init__(self):
        # _procs kept for API compatibility — unused in Docker mode
        self._procs: dict = {}
        self._lock = threading.Lock()

    # ── Discovery ─────────────────────────────────────────────────────────

    def check_prerequisites(self) -> dict:
        """Check Docker + KVM availability."""
        return _eh.check_prerequisites()

    def list_system_images(self) -> list[dict]:
        """Return available Docker-based Android images."""
        return _eh.list_system_images()

    def install_system_image(self, api_level: int, target: str = "google_apis_playstore", arch: str = "") -> dict:
        """Pull the Docker emulator image."""
        return _eh.install_system_image(api_level, target, arch)

    def list_avds(self) -> list[dict]:
        """List all ghost-labelled emulator containers."""
        return _eh.list_avds(self.list_running())

    def list_running(self) -> list[dict]:
        """List running emulator containers reachable via ADB."""
        return _eh.list_running(self._procs, self._lock)

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def create(self, config: EmulatorConfig) -> dict:
        """Create (and start) a Docker-based Android emulator container.

        In Docker mode 'create' == 'create + start' because containers don't
        have the AVD-vs-running distinction.  The container is started
        immediately; boot polling happens in a background thread.
        """
        if not _has_docker():
            return {
                "ok": False,
                "error": "Docker daemon not reachable. Make sure Docker is running.",
            }
        if not _has_kvm():
            return {
                "ok": False,
                "error": "/dev/kvm not found. KVM must be enabled for hardware-accelerated emulation.",
            }

        # Check for name collision
        existing = [a["name"] for a in self.list_avds()]
        if config.name in existing:
            return {"ok": False, "error": f'Emulator "{config.name}" already exists.'}

        with self._lock:
            used_ports = _eh._used_host_ports()
        host_port = next_available_port(used_ports)

        try:
            client = _docker()
            container = client.containers.run(
                DOCKER_IMAGE,
                detach=True,
                name=config.name,
                devices=["/dev/kvm:/dev/kvm"],
                environment={
                    "EMULATOR_DEVICE": config.device_profile,
                    "WEB_VNC": "false",
                },
                ports={f"{_eh.CONTAINER_PORT}/tcp": host_port},
                labels={
                    _eh.CONTAINER_LABEL: _eh.CONTAINER_LABEL_VALUE,
                    "ghost.name": config.name,
                    "ghost.device_profile": config.device_profile,
                    "ghost.api_level": str(config.api_level),
                },
            )
        except Exception as e:
            return {"ok": False, "error": f"Docker run failed: {e}"}

        serial = f"localhost:{host_port}"

        # Boot watcher in background
        boot_thread = threading.Thread(
            target=self._wait_for_boot_and_setup,
            args=(serial, config.name),
            daemon=True,
        )
        boot_thread.start()

        return {
            "ok": True,
            "name": config.name,
            "container_id": container.short_id,
            "serial": serial,
            "host_port": host_port,
            "status": "booting",
            "config": asdict(config),
        }

    def _wait_for_boot_and_setup(self, serial: str, name: str):
        """Connect ADB and wait for boot, then run automation setup."""
        # Give the container a moment to initialise its QEMU process
        time.sleep(10)
        try:
            # Connect ADB to the TCP endpoint
            _run([ADB_BIN, "connect", serial], timeout=15, check=False)
            self._wait_for_boot(serial, timeout=240)
            self.setup_for_automation(serial)
            logger.info("Emulator %s (%s) is ready", name, serial)
        except Exception as e:
            logger.error("Emulator %s (%s) boot/setup failed: %s", name, serial, e)

    def delete(self, name: str) -> dict:
        """Stop and remove a Docker emulator container."""
        # Disconnect ADB first if it was connected
        for info in self.list_running():
            if info["name"] == name and info.get("serial"):
                try:
                    _run([ADB_BIN, "disconnect", info["serial"]], timeout=5, check=False)
                except Exception:
                    pass

        try:
            client = _docker()
            container = client.containers.get(name)
            container.remove(force=True)
            return {"ok": True, "name": name}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def start(
        self,
        name: str,
        headless: bool = False,
        gpu: str = "auto",
        cold_boot: bool = False,
        extra_args: list[str] | None = None,
    ) -> dict:
        """Start a stopped Docker emulator container.

        If the container doesn't exist yet, returns an error directing the
        caller to use create() first.  In Docker mode headless/gpu/extra_args
        are accepted for API compatibility but are no-ops.
        """
        if not _has_docker():
            return {"ok": False, "error": "Docker daemon not reachable."}

        try:
            client = _docker()
            container = client.containers.get(name)
        except Exception:
            return {
                "ok": False,
                "error": (f'Container "{name}" not found. Use POST /api/emulators to create it first.'),
            }

        if container.status == "running":
            info = _eh._container_to_info(container)
            return {"ok": True, "already_running": True, **info}

        # Re-start a stopped container
        try:
            container.start()
            container.reload()
        except Exception as e:
            return {"ok": False, "error": f"Failed to start container: {e}"}

        info = _eh._container_to_info(container)
        serial = info.get("serial")
        if serial:
            boot_thread = threading.Thread(
                target=self._wait_for_boot_and_setup,
                args=(serial, name),
                daemon=True,
            )
            boot_thread.start()

        return {
            "ok": True,
            "name": name,
            "serial": serial,
            "host_port": info.get("host_port"),
            "status": "booting",
        }

    def stop(self, serial: str) -> dict:
        """Stop a running emulator by its ADB serial (localhost:PORT).

        Disconnects ADB and stops (but does not remove) the container so it
        can be restarted quickly.
        """
        try:
            _run([ADB_BIN, "disconnect", serial], timeout=5, check=False)
        except Exception:
            pass

        # Find the container by matching host port
        try:
            host_port = int(serial.split(":")[-1])
        except ValueError:
            return {"ok": False, "error": f"Cannot parse port from serial: {serial}"}

        try:
            client = _docker()
            containers = client.containers.list(filters={"label": f"{_eh.CONTAINER_LABEL}={_eh.CONTAINER_LABEL_VALUE}"})
            for c in containers:
                for bindings in (c.ports or {}).values():
                    if bindings and any(int(b.get("HostPort", -1)) == host_port for b in bindings):
                        c.stop(timeout=15)
                        return {"ok": True, "serial": serial, "container": c.name}
        except Exception as e:
            return {"ok": False, "error": str(e)}

        return {"ok": False, "error": f"No running container found for serial {serial}"}

    def get_boot_status(self, serial: str) -> dict:
        """Check if an emulator has finished booting."""
        try:
            r = _run([ADB_BIN, "-s", serial, "shell", "getprop", "sys.boot_completed"], timeout=5, check=False)
            booted = r.stdout.strip() == "1"
            return {"serial": serial, "booted": booted}
        except (subprocess.SubprocessError, OSError):
            return {"serial": serial, "booted": False, "error": "not reachable"}

    # ── Setup ──────────────────────────────────────────────────────────────

    def setup_for_automation(self, serial: str) -> dict:
        """Configure emulator for automation after boot."""
        commands = [
            # Disable animations
            ("shell", "settings", "put", "global", "window_animation_scale", "0"),
            ("shell", "settings", "put", "global", "transition_animation_scale", "0"),
            ("shell", "settings", "put", "global", "animator_duration_scale", "0"),
            # Lock portrait
            ("shell", "settings", "put", "system", "accelerometer_rotation", "0"),
            # Max screen timeout
            ("shell", "settings", "put", "system", "screen_off_timeout", "2147483647"),
            # Stay awake while charging (container is always "charging")
            ("shell", "settings", "put", "global", "stay_on_while_plugged_in", "3"),
        ]
        results = []
        for cmd in commands:
            r = _adb(serial, *cmd)
            results.append(r)
        return {"ok": True, "serial": serial, "applied": len(commands)}

    def install_apk(self, serial: str, apk_path: str) -> dict:
        """Install an APK on emulator."""
        if not Path(apk_path).exists():
            return {"ok": False, "error": f"APK not found: {apk_path}"}
        try:
            r = _run([ADB_BIN, "-s", serial, "install", "-r", "-g", apk_path], timeout=120)
            return {"ok": True, "output": r.stdout[-200:]}
        except subprocess.CalledProcessError as e:
            return {"ok": False, "error": e.stderr[-300:]}

    # ── Snapshots ──────────────────────────────────────────────────────────
    # budtmo/docker-android doesn't support AVD snapshots; these return
    # informative messages rather than hard errors so the API surface is intact.

    def snapshot_save(self, serial: str, name: str = "automation_ready") -> dict:
        """Snapshot not supported in Docker mode — returns advisory message."""
        return {
            "ok": False,
            "serial": serial,
            "snapshot": name,
            "error": "Snapshots are not supported in Docker emulator mode.",
        }

    def snapshot_load(self, serial: str, name: str = "automation_ready") -> dict:
        """Snapshot not supported in Docker mode — returns advisory message."""
        return {
            "ok": False,
            "serial": serial,
            "snapshot": name,
            "error": "Snapshots are not supported in Docker emulator mode.",
        }

    def list_snapshots(self, serial: str) -> dict:
        """Snapshot not supported in Docker mode."""
        return {
            "ok": False,
            "serial": serial,
            "output": "",
            "error": "Snapshots are not supported in Docker emulator mode.",
        }

    # ── Internals ──────────────────────────────────────────────────────────

    def _next_available_port(self) -> int:
        """Find next free host port for a new container."""
        with self._lock:
            used = _eh._used_host_ports()
        return next_available_port(used)

    def _wait_for_boot(self, serial: str, timeout: int = 240):
        """Poll until device reports boot complete."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                r = _run([ADB_BIN, "-s", serial, "shell", "getprop", "sys.boot_completed"], timeout=5, check=False)
                if r.stdout.strip() == "1":
                    return True
            except Exception:
                pass
            time.sleep(3)
        raise TimeoutError(f"{serial} did not boot within {timeout}s")


# ── Singletons ────────────────────────────────────────────────────────────────
_manager: Optional[EmulatorManager] = None
_pool: Optional[EmulatorPool] = None


def get_manager() -> EmulatorManager:
    global _manager
    if _manager is None:
        _manager = EmulatorManager()
    return _manager


def get_pool() -> EmulatorPool:
    global _pool
    if _pool is None:
        _pool = EmulatorPool(get_manager())
    return _pool
