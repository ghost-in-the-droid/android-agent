"""
Emulator Service — lifecycle management (create/start/stop/delete/snapshots).

Discovery helpers live in _emulator_helpers; pool logic in _emulator_pool.
"""

import logging
import shutil
import subprocess
import threading
import time
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from gitd.services import _emulator_helpers as _eh
from gitd.services._emulator_helpers import (
    ADB_BIN,
    AVD_HOME,
    AVDMANAGER,
    EMULATOR_BIN,
    EmulatorConfig,  # noqa: F401 — re-exported for routers
    _adb,
    _has_cmdline_tools,
    _has_emulator,
    _run,
)
from gitd.services._emulator_pool import EmulatorPool

logger = logging.getLogger(__name__)


# ── EmulatorManager ──────────────────────────────────────────────────────────


class EmulatorManager:
    """Manage Android emulator lifecycle."""

    def __init__(self):
        self._procs: dict[str, subprocess.Popen] = {}  # serial -> Popen
        self._lock = threading.Lock()

    # ── Discovery (delegated to _emulator_helpers) ────────────────────────
    def check_prerequisites(self) -> dict:
        """Check what SDK tools are available."""
        return _eh.check_prerequisites()

    def list_system_images(self) -> list[dict]:
        """List installed system images by scanning the SDK directory."""
        return _eh.list_system_images()

    def install_system_image(self, api_level: int, target: str = "google_apis_playstore", arch: str = "x86_64") -> dict:
        """Download a system image via sdkmanager. Requires cmdline-tools."""
        return _eh.install_system_image(api_level, target, arch)

    def list_avds(self) -> list[dict]:
        """List all created AVDs by reading .ini files from AVD_HOME."""
        return _eh.list_avds(self.list_running())

    def list_running(self) -> list[dict]:
        """List running emulators with serials and AVD names."""
        return _eh.list_running(self._procs, self._lock)

    # ── Lifecycle ────────────────────────────────────────────────────────
    def create(self, config: EmulatorConfig) -> dict:
        """Create a new AVD. Requires cmdline-tools (avdmanager)."""
        if not _has_cmdline_tools():
            return {
                "ok": False,
                "error": (
                    "cmdline-tools not installed. Install with:\n"
                    f"  {EMULATOR_BIN.parent.parent}/cmdline-tools or download from "
                    "https://developer.android.com/studio#command-tools\n"
                    'Then: sdkmanager --install "cmdline-tools;latest"'
                ),
            }

        # Check system image exists
        if not config.system_image_dir().exists():
            return {"ok": False, "error": f"System image not found: {config.system_image_pkg()}. Install it first."}

        # Check if AVD already exists
        existing = [a["name"] for a in self.list_avds()]
        if config.name in existing:
            return {"ok": False, "error": f'AVD "{config.name}" already exists.'}

        cmd = [
            str(AVDMANAGER),
            "create",
            "avd",
            "-n",
            config.name,
            "-k",
            config.system_image_pkg(),
            "-d",
            config.device_profile,
            "--force",
        ]
        try:
            r = _run(cmd, timeout=60, input="no\n", check=False)
            if r.returncode != 0:
                return {"ok": False, "error": r.stderr[-500:] or r.stdout[-500:]}
        except (subprocess.SubprocessError, OSError) as e:
            return {"ok": False, "error": str(e)}

        # Patch config.ini with custom settings
        self._patch_avd_config(config)

        return {"ok": True, "name": config.name, "config": asdict(config)}

    def _patch_avd_config(self, config: EmulatorConfig):
        """Update AVD config.ini with our settings."""
        # Find the config.ini — check both naming conventions
        for avd_dir_name in [config.name, config.name.replace(" ", "_")]:
            config_ini = AVD_HOME / f"{avd_dir_name}.avd" / "config.ini"
            if config_ini.exists():
                break
        else:
            return

        text = config_ini.read_text()
        patches = {
            "hw.ramSize": str(config.ram_mb),
            "disk.dataPartition.size": f"{config.disk_mb}M",
            "hw.lcd.width": config.resolution.split("x")[0],
            "hw.lcd.height": config.resolution.split("x")[1],
            "hw.lcd.density": str(config.dpi),
            "hw.gpu.enabled": "yes",
            "hw.gpu.mode": config.gpu,
            "hw.cpu.ncore": str(config.cores),
        }
        lines = text.splitlines()
        existing_keys = set()
        new_lines = []
        for line in lines:
            if "=" in line:
                key = line.split("=", 1)[0].strip()
                if key in patches:
                    new_lines.append(f"{key}={patches[key]}")
                    existing_keys.add(key)
                    continue
            new_lines.append(line)
        # Add missing keys
        for k, v in patches.items():
            if k not in existing_keys:
                new_lines.append(f"{k}={v}")
        config_ini.write_text("\n".join(new_lines) + "\n")

    def delete(self, name: str) -> dict:
        """Delete an AVD."""
        # Stop it first if running
        running = {info["name"]: info["serial"] for info in self.list_running()}
        if name in running:
            self.stop(running[name])

        if _has_cmdline_tools():
            try:
                r = _run([str(AVDMANAGER), "delete", "avd", "-n", name], timeout=30, check=False)
                if r.returncode == 0:
                    return {"ok": True, "name": name}
                return {"ok": False, "error": r.stderr[-500:]}
            except (subprocess.SubprocessError, OSError) as e:
                return {"ok": False, "error": str(e)}
        else:
            # Manual deletion — remove .ini and .avd directory
            ini_file = AVD_HOME / f"{name}.ini"
            avd_dir = AVD_HOME / f"{name}.avd"
            deleted = []
            if ini_file.exists():
                ini_file.unlink()
                deleted.append(str(ini_file))
            if avd_dir.exists():
                shutil.rmtree(avd_dir)
                deleted.append(str(avd_dir))
            if deleted:
                return {"ok": True, "name": name, "deleted": deleted}
            return {"ok": False, "error": f'AVD "{name}" not found at {AVD_HOME}'}

    def start(
        self,
        name: str,
        headless: bool = False,
        gpu: str = "auto",
        cold_boot: bool = False,
        extra_args: list[str] = None,
    ) -> dict:
        """Start an emulator. Returns {serial, pid, port, name}.

        For headless mode, defaults to swiftshader_indirect GPU (more reliable).
        Use cold_boot=True to skip snapshot loading (fixes ADB offline issues).
        """
        if not _has_emulator():
            return {"ok": False, "error": f"Emulator binary not found at {EMULATOR_BIN}"}

        # Check AVD exists
        avd_names = [a["name"] for a in self.list_avds()]
        if name not in avd_names:
            return {"ok": False, "error": f'AVD "{name}" does not exist. Available: {avd_names}'}

        # Check if already running
        for info in self.list_running():
            if info["name"] == name:
                return {"ok": True, "already_running": True, **info}

        # Default to swiftshader for headless (host GPU needs display)
        effective_gpu = gpu
        if headless and gpu == "auto":
            effective_gpu = "swiftshader_indirect"

        port = self._next_available_port()
        cmd = [
            str(EMULATOR_BIN),
            "-avd",
            name,
            "-port",
            str(port),
            "-no-audio",
            "-no-boot-anim",
            "-gpu",
            effective_gpu,
        ]
        if headless:
            cmd.append("-no-window")
        if cold_boot:
            cmd.append("-no-snapshot-load")
        if extra_args:
            cmd.extend(extra_args)

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
        except (subprocess.SubprocessError, OSError) as e:
            return {"ok": False, "error": f"Failed to launch emulator: {e}"}

        serial = f"emulator-{port}"
        with self._lock:
            self._procs[serial] = proc

        # Wait for boot in background — return immediately with serial
        # Caller can poll /api/emulators/running or check boot status
        boot_thread = threading.Thread(
            target=self._wait_for_boot_and_setup,
            args=(serial, name, proc),
            daemon=True,
        )
        boot_thread.start()

        return {
            "ok": True,
            "serial": serial,
            "port": port,
            "pid": proc.pid,
            "name": name,
            "status": "booting",
        }

    def _wait_for_boot_and_setup(self, serial: str, name: str, proc: subprocess.Popen):
        """Wait for emulator to boot, then run automation setup."""
        try:
            self._wait_for_boot(serial, timeout=180)
            self.setup_for_automation(serial)
        except Exception as e:
            logger.error("%s (%s) boot/setup failed: %s", serial, name, e)

    def stop(self, serial: str) -> dict:
        """Stop an emulator gracefully."""
        try:
            _run([ADB_BIN, "-s", serial, "emu", "kill"], timeout=10, check=False)
        except (subprocess.SubprocessError, OSError):
            pass

        # Also terminate the process if we tracked it
        with self._lock:
            proc = self._procs.pop(serial, None)
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=10)
            except (subprocess.SubprocessError, OSError):
                proc.kill()

        # Give ADB time to deregister
        time.sleep(1)
        return {"ok": True, "serial": serial}

    def get_boot_status(self, serial: str) -> dict:
        """Check if an emulator has finished booting."""
        try:
            r = _run([ADB_BIN, "-s", serial, "shell", "getprop", "sys.boot_completed"], timeout=5, check=False)
            booted = r.stdout.strip() == "1"
            return {"serial": serial, "booted": booted}
        except (subprocess.SubprocessError, OSError):
            return {"serial": serial, "booted": False, "error": "not reachable"}

    # ── Setup ────────────────────────────────────────────────────────────
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
            # Stay awake while charging (emulator is always "charging")
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

    # ── Snapshots ────────────────────────────────────────────────────────
    def snapshot_save(self, serial: str, name: str = "automation_ready") -> dict:
        """Save emulator state snapshot."""
        try:
            _run([ADB_BIN, "-s", serial, "emu", "avd", "snapshot", "save", name], timeout=30, check=False)
            return {"ok": True, "serial": serial, "snapshot": name}
        except (subprocess.SubprocessError, OSError) as e:
            return {"ok": False, "error": str(e)}

    def snapshot_load(self, serial: str, name: str = "automation_ready") -> dict:
        """Restore emulator from snapshot."""
        try:
            _run([ADB_BIN, "-s", serial, "emu", "avd", "snapshot", "load", name], timeout=30, check=False)
            return {"ok": True, "serial": serial, "snapshot": name}
        except (subprocess.SubprocessError, OSError) as e:
            return {"ok": False, "error": str(e)}

    def list_snapshots(self, serial: str) -> dict:
        """List available snapshots for a running emulator."""
        try:
            r = _run([ADB_BIN, "-s", serial, "emu", "avd", "snapshot", "list"], timeout=10, check=False)
            return {"ok": True, "serial": serial, "output": r.stdout}
        except (subprocess.SubprocessError, OSError) as e:
            return {"ok": False, "error": str(e)}

    # ── Internals ────────────────────────────────────────────────────────
    def _next_available_port(self) -> int:
        """Find next free even port starting from 5554."""
        used_ports = set()
        for info in self.list_running():
            port_str = info["serial"].replace("emulator-", "")
            try:
                used_ports.add(int(port_str))
            except ValueError:
                pass
        port = 5554
        while port in used_ports:
            port += 2
        return port

    def _wait_for_boot(self, serial: str, timeout: int = 180):
        """Poll until device reports boot complete."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                r = _run([ADB_BIN, "-s", serial, "shell", "getprop", "sys.boot_completed"], timeout=5, check=False)
                if r.stdout.strip() == "1":
                    return True
            except (subprocess.SubprocessError, OSError):
                pass
            time.sleep(2)
        raise TimeoutError(f"{serial} did not boot within {timeout}s")


# ── Singletons ───────────────────────────────────────────────────────────────
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
