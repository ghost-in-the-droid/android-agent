"""
EmulatorPool — manage a pool of emulators for parallel automation.

Extracted from emulator_service.py. Uses EmulatorManager for lifecycle ops.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import psutil

from gitd.services._emulator_helpers import EmulatorConfig

if TYPE_CHECKING:
    from gitd.services.emulator_service import EmulatorManager

logger = logging.getLogger(__name__)


class EmulatorPool:
    """Manage a pool of emulators for parallel automation."""

    def __init__(self, manager: EmulatorManager, max_concurrent: int = 20):
        self.manager = manager
        self.max_concurrent = max_concurrent
        self._pool: dict[str, dict] = {}  # serial -> {name, status, current_job}
        self._lock = threading.Lock()

    def status(self) -> dict:
        """Pool status summary."""
        with self._lock:
            active = len(self._pool)
            idle = sum(1 for v in self._pool.values() if v["status"] == "idle")
            busy = sum(1 for v in self._pool.values() if v["status"] == "busy")
        resources = self.resource_usage()
        return {
            "active": active,
            "idle": idle,
            "busy": busy,
            "max_concurrent": self.max_concurrent,
            "emulators": list(self._pool.values()),
            "resources": resources,
        }

    def resource_usage(self) -> dict:
        """Current system resource usage."""
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage(str(Path.home()))
        return {
            "cpu_count": psutil.cpu_count(),
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "ram_total_gb": round(mem.total / (1024**3), 1),
            "ram_used_gb": round(mem.used / (1024**3), 1),
            "ram_available_gb": round(mem.available / (1024**3), 1),
            "disk_total_gb": round(disk.total / (1024**3), 1),
            "disk_free_gb": round(disk.free / (1024**3), 1),
        }

    def scale_up(self, count: int, config: EmulatorConfig) -> dict:
        """Start N emulators from a config template. Returns results."""
        with self._lock:
            current = len(self._pool)
        if current + count > self.max_concurrent:
            return {"ok": False, "error": f"Would exceed max_concurrent={self.max_concurrent} (current={current})"}

        results = []
        for i in range(count):
            name = f"pool_{current + i:03d}"
            cfg = EmulatorConfig(
                name=name,
                api_level=config.api_level,
                target=config.target,
                arch=config.arch,
                device_profile=config.device_profile,
                ram_mb=config.ram_mb,
                disk_mb=config.disk_mb,
                resolution=config.resolution,
                dpi=config.dpi,
                gpu=config.gpu,
                cores=config.cores,
                headless=True,  # pool emulators always headless
                snapshot=config.snapshot,
            )
            # Create AVD if needed
            existing_names = [a["name"] for a in self.manager.list_avds()]
            if name not in existing_names:
                create_result = self.manager.create(cfg)
                if not create_result.get("ok"):
                    results.append({"name": name, "ok": False, "error": create_result.get("error")})
                    continue

            # Start it
            start_result = self.manager.start(name, headless=True, gpu=cfg.gpu)
            if not start_result.get("ok"):
                results.append({"name": name, "ok": False, "error": start_result.get("error")})
                continue

            serial = start_result["serial"]
            with self._lock:
                self._pool[serial] = {
                    "serial": serial,
                    "name": name,
                    "status": "idle",
                    "current_job": None,
                    "pid": start_result.get("pid"),
                }
            results.append({"name": name, "serial": serial, "ok": True})

        return {"ok": True, "started": results}

    def scale_down(self, count: Optional[int] = None) -> dict:
        """Stop idle emulators. If count is None, stop all idle."""
        with self._lock:
            idle = [s for s, info in self._pool.items() if info["status"] == "idle"]
        to_stop = idle[:count] if count else idle

        stopped = []
        for serial in to_stop:
            self.manager.stop(serial)
            with self._lock:
                self._pool.pop(serial, None)
            stopped.append(serial)
        return {"ok": True, "stopped": stopped}

    def get_idle(self) -> Optional[str]:
        """Get an idle emulator serial."""
        with self._lock:
            for serial, info in self._pool.items():
                if info["status"] == "idle":
                    return serial
        return None

    def mark_busy(self, serial: str, job_id: str):
        """Mark emulator as busy with a job."""
        with self._lock:
            if serial in self._pool:
                self._pool[serial]["status"] = "busy"
                self._pool[serial]["current_job"] = job_id

    def mark_idle(self, serial: str):
        """Mark emulator as idle."""
        with self._lock:
            if serial in self._pool:
                self._pool[serial]["status"] = "idle"
                self._pool[serial]["current_job"] = None

    def stop_all(self) -> dict:
        """Stop all pool emulators."""
        with self._lock:
            serials = list(self._pool.keys())
        stopped = []
        for serial in serials:
            self.manager.stop(serial)
            stopped.append(serial)
        with self._lock:
            self._pool.clear()
        return {"ok": True, "stopped": stopped}
