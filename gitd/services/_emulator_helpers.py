"""
Shared helpers for emulator_service — Docker-based Android emulators,
ADB utilities, EmulatorConfig dataclass, and discovery/query functions.

Replaces the AVD/SDK-based backend with Docker+KVM via budtmo/docker-android.
"""

import logging
import platform
import shutil
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path

try:
    import docker as docker_sdk
except ImportError:
    docker_sdk = None  # type: ignore[assignment]

try:
    import psutil
except ImportError:
    psutil = None  # Not available on Android (C extension)

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

DOCKER_IMAGE = "budtmo/docker-android:emulator_11.0"
CONTAINER_LABEL = "ghost.type"
CONTAINER_LABEL_VALUE = "emulator"
CONTAINER_PORT = 5555  # internal ADB port inside every budtmo container
BASE_HOST_PORT = 5555  # first mapped host port; increments per instance

# ADB binary — still used to connect/run commands against containers
ADB_BIN: str = shutil.which("adb") or "adb"

# ── Legacy stubs kept so routers/pool don't need import changes ───────────────
# These names were imported by emulator_service.py; keep them resolvable.
AVD_HOME = Path.home() / ".android" / "avd"  # no-op in Docker mode
AVDMANAGER = Path("/dev/null")  # not used
EMULATOR_BIN = Path("/dev/null")  # not used
SDKMANAGER = Path("/dev/null")  # not used


# ── Docker client ─────────────────────────────────────────────────────────────


def _docker() -> "docker_sdk.DockerClient":
    """Return a connected Docker client (raises RuntimeError if unavailable)."""
    if docker_sdk is None:
        raise RuntimeError("docker Python SDK not installed. Run: pip install docker")
    return docker_sdk.from_env()


# ── Utility functions ─────────────────────────────────────────────────────────


def _has_cmdline_tools() -> bool:
    """Docker mode — no SDK cmdline-tools needed."""
    return False


def _has_emulator() -> bool:
    """Docker mode — no native emulator binary needed."""
    return False


def _has_docker() -> bool:
    """Check if Docker daemon is reachable."""
    try:
        _docker().ping()
        return True
    except Exception:
        return False


def _has_kvm() -> bool:
    return Path("/dev/kvm").exists()


def _run(cmd: list[str], timeout: int = 60, check: bool = True, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=check, **kw)


def _adb(serial: str, *args, timeout: int = 30) -> str:
    r = _run([ADB_BIN, "-s", serial, *args], timeout=timeout, check=False)
    return r.stdout.strip()


def _safe_int(val: str, default: int = 0) -> int:
    """Parse int from string, stripping size suffixes like 'M', 'G'."""
    val = val.strip()
    if not val:
        return default
    for suffix in ("MB", "GB", "KB", "M", "G", "K"):
        if val.upper().endswith(suffix):
            val = val[: -len(suffix)]
            break
    try:
        return int(val)
    except ValueError:
        return default


def is_emulator(serial: str) -> bool:
    return serial.startswith("emulator-") or "localhost:" in serial


def default_arch() -> str:
    if platform.machine().lower() in ("arm64", "aarch64"):
        return "arm64-v8a"
    return "x86_64"


# ── Config dataclass ──────────────────────────────────────────────────────────


@dataclass
class EmulatorConfig:
    name: str
    api_level: int = 30  # Android 11 (emulator_11.0 image)
    target: str = "google_apis_playstore"
    arch: str = ""  # auto-detected if empty
    device_profile: str = "Samsung Galaxy S10"  # passed as EMULATOR_DEVICE env var
    ram_mb: int = 2048
    disk_mb: int = 6144
    resolution: str = "1080x2400"
    dpi: int = 420
    gpu: str = "auto"  # kept for API compat; Docker uses swiftshader internally
    cores: int = 2
    headless: bool = False  # Docker is always headless
    snapshot: bool = True

    def __post_init__(self):
        if not self.arch:
            self.arch = default_arch()

    def system_image_pkg(self) -> str:
        """Legacy compat — not used in Docker mode."""
        api = f"android-{self.api_level}"
        return f"system-images;{api};{self.target};{self.arch}"

    def system_image_dir(self) -> Path:
        """Legacy compat — not used in Docker mode."""
        api = f"android-{self.api_level}"
        return Path("/dev/null") / "system-images" / api / self.target / self.arch


# ── Port allocation ───────────────────────────────────────────────────────────


def _used_host_ports() -> set[int]:
    """Collect host ports already in use by our emulator containers."""
    used: set[int] = set()
    try:
        client = _docker()
        for c in client.containers.list(filters={"label": f"{CONTAINER_LABEL}={CONTAINER_LABEL_VALUE}"}):
            ports = c.ports or {}
            # ports dict: {"5555/tcp": [{"HostIp": "0.0.0.0", "HostPort": "5556"}]}
            for bindings in ports.values():
                if bindings:
                    for b in bindings:
                        try:
                            used.add(int(b["HostPort"]))
                        except (KeyError, ValueError, TypeError):
                            pass
    except Exception:
        pass
    return used


def next_available_port(used_ports: set[int] | None = None) -> int:
    """Find the next free host port starting from BASE_HOST_PORT."""
    if used_ports is None:
        used_ports = _used_host_ports()
    port = BASE_HOST_PORT
    while port in used_ports:
        port += 1
    return port


# ── Container helpers ─────────────────────────────────────────────────────────


def _container_to_info(c) -> dict:
    """Convert a Docker container object to the canonical emulator info dict."""
    labels = c.labels or {}
    ports = c.ports or {}

    host_port = None
    for bindings in ports.values():
        if bindings:
            for b in bindings:
                try:
                    host_port = int(b["HostPort"])
                    break
                except (KeyError, ValueError, TypeError):
                    pass
        if host_port:
            break

    serial = f"localhost:{host_port}" if host_port else None
    status = c.status  # running / exited / created / ...

    return {
        "name": labels.get("ghost.name", c.name),
        "container_id": c.short_id,
        "container_name": c.name,
        "host_port": host_port,
        "serial": serial,
        "status": "running" if status == "running" else status,
        "device_profile": labels.get("ghost.device_profile", ""),
        "api_level": int(labels.get("ghost.api_level", 30)),
    }


# ── Discovery / query functions ───────────────────────────────────────────────


def check_prerequisites() -> dict:
    """Check Docker + KVM availability (replaces SDK prerequisites check)."""
    docker_ok = _has_docker()
    kvm_ok = _has_kvm()
    adb_ok = bool(shutil.which("adb"))
    return {
        "backend": "docker",
        "docker_available": docker_ok,
        "kvm_available": kvm_ok,
        "adb_binary": adb_ok,
        "hw_accel": kvm_ok,
        "hw_accel_type": "KVM",
        "platform": platform.system(),
        "arch": default_arch(),
        "image": DOCKER_IMAGE,
        # Legacy fields (kept so existing frontend/clients don't break)
        "sdk_root": "N/A (docker mode)",
        "sdk_exists": False,
        "emulator_binary": False,
        "cmdline_tools": False,
        "avd_home": "N/A (docker mode)",
    }


def list_system_images() -> list[dict]:
    """In Docker mode, return the single bundled image as a pseudo-entry."""
    return [
        {
            "api_level": "30",
            "target": "google_apis_playstore",
            "arch": default_arch(),
            "package": DOCKER_IMAGE,
            "path": f"docker://{DOCKER_IMAGE}",
            "note": "Docker image — no SDK system images needed",
        }
    ]


def install_system_image(api_level: int, target: str = "google_apis_playstore", arch: str = "") -> dict:
    """In Docker mode, 'install' means pull the image."""
    try:
        client = _docker()
        client.images.pull(DOCKER_IMAGE)
        return {"ok": True, "package": DOCKER_IMAGE, "output": f"Pulled {DOCKER_IMAGE}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def list_avds(running_list: list[dict]) -> list[dict]:
    """List all ghost-labelled emulator containers (running + stopped)."""
    try:
        client = _docker()
        containers = client.containers.list(
            all=True,
            filters={"label": f"{CONTAINER_LABEL}={CONTAINER_LABEL_VALUE}"},
        )
    except Exception as e:
        logger.warning("list_avds: Docker error: %s", e)
        return []

    running_by_name = {r["name"]: r for r in running_list}
    avds = []
    for c in containers:
        info = _container_to_info(c)
        run_info = running_by_name.get(info["name"])
        if run_info:
            info["status"] = "running" if run_info.get("adb_state") == "device" else "booting"
            info["serial"] = run_info["serial"]
        avds.append(info)
    return avds


def list_running(procs: dict, lock: threading.Lock) -> list[dict]:
    """List running emulator containers that ADB can reach."""
    try:
        client = _docker()
        containers = client.containers.list(
            filters={"label": f"{CONTAINER_LABEL}={CONTAINER_LABEL_VALUE}", "status": "running"}
        )
    except Exception as e:
        logger.warning("list_running: Docker error: %s", e)
        return []

    running = []
    for c in containers:
        info = _container_to_info(c)
        serial = info.get("serial")
        if not serial:
            continue
        # Check ADB state
        try:
            r = _run([ADB_BIN, "-s", serial, "get-state"], timeout=5, check=False)
            adb_state = "device" if r.stdout.strip() == "device" else "offline"
        except Exception:
            adb_state = "offline"

        running.append(
            {
                "serial": serial,
                "name": info["name"],
                "host_port": info.get("host_port"),
                "pid": None,  # no native PID — it's a container
                "adb_state": adb_state,
                "container_id": info.get("container_id"),
            }
        )
    return running
