"""
Shared helpers for emulator_service — SDK paths, utility functions,
EmulatorConfig dataclass, and discovery/query functions.
"""

import configparser
import logging
import os
import platform
import shutil
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import psutil

logger = logging.getLogger(__name__)

# ── SDK paths ────────────────────────────────────────────────────────────────


def _detect_sdk_root() -> Path:
    """Auto-detect Android SDK root across platforms."""
    for var in ("ANDROID_SDK_ROOT", "ANDROID_HOME"):
        val = os.environ.get(var)
        if val and Path(val).exists():
            return Path(val)
    # macOS: Homebrew commandline-tools
    brew = Path("/opt/homebrew/share/android-commandlinetools")
    if brew.exists():
        return brew
    # macOS: Android Studio default
    mac_studio = Path.home() / "Library" / "Android" / "sdk"
    if mac_studio.exists():
        return mac_studio
    # Linux default
    linux = Path.home() / "Android" / "Sdk"
    if linux.exists():
        return linux
    return brew if platform.system() == "Darwin" else linux


SDK_ROOT = _detect_sdk_root()

EMULATOR_BIN = SDK_ROOT / "emulator" / "emulator"
ADB_BIN = shutil.which("adb") or str(SDK_ROOT / "platform-tools" / "adb")
SDKMANAGER = SDK_ROOT / "cmdline-tools" / "latest" / "bin" / "sdkmanager"
AVDMANAGER = SDK_ROOT / "cmdline-tools" / "latest" / "bin" / "avdmanager"
AVD_HOME = Path(os.environ.get("ANDROID_AVD_HOME", Path.home() / ".android" / "avd"))


# ── Utility functions ────────────────────────────────────────────────────────


def _has_cmdline_tools() -> bool:
    return AVDMANAGER.exists() and SDKMANAGER.exists()


def _has_emulator() -> bool:
    return EMULATOR_BIN.exists()


def _run(cmd: list[str], timeout: int = 60, check: bool = True, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=check, **kw)


def _adb(serial: str, *args, timeout: int = 30) -> str:
    r = _run([ADB_BIN, "-s", serial, *args], timeout=timeout, check=False)
    return r.stdout.strip()


def _safe_int(val: str, default: int = 0) -> int:
    """Parse int from string, stripping size suffixes like 'M', 'G', '2G'."""
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
    return serial.startswith("emulator-")


def default_arch() -> str:
    """Return the correct emulator arch for this platform."""
    if platform.machine().lower() in ("arm64", "aarch64"):
        return "arm64-v8a"
    return "x86_64"


# ── Config dataclass ─────────────────────────────────────────────────────────


@dataclass
class EmulatorConfig:
    name: str
    api_level: int = 35
    target: str = "google_apis_playstore"  # google_apis | google_apis_playstore | default
    arch: str = ""  # auto-detected if empty
    device_profile: str = "medium_phone"  # hardware profile name
    ram_mb: int = 2048
    disk_mb: int = 6144
    resolution: str = "1080x2400"
    dpi: int = 420
    gpu: str = "auto"  # auto | host | swiftshader_indirect | off
    cores: int = 2
    headless: bool = False
    snapshot: bool = True

    def __post_init__(self):
        if not self.arch:
            self.arch = default_arch()

    def system_image_pkg(self) -> str:
        api = f"android-{self.api_level}"
        return f"system-images;{api};{self.target};{self.arch}"

    def system_image_dir(self) -> Path:
        api = f"android-{self.api_level}"
        return SDK_ROOT / "system-images" / api / self.target / self.arch


# ── Discovery / query functions ──────────────────────────────────────────────
# These were originally EmulatorManager methods but have no dependency on
# instance state beyond _procs/_lock (which are passed in where needed).


def check_prerequisites() -> dict:
    """Check what SDK tools are available."""
    is_mac = platform.system() == "Darwin"
    hw_accel = True if is_mac else Path("/dev/kvm").exists()
    return {
        "sdk_root": str(SDK_ROOT),
        "sdk_exists": SDK_ROOT.exists(),
        "emulator_binary": EMULATOR_BIN.exists(),
        "adb_binary": shutil.which("adb") is not None or (SDK_ROOT / "platform-tools" / "adb").exists(),
        "cmdline_tools": _has_cmdline_tools(),
        "hw_accel": hw_accel,
        "hw_accel_type": "HVF" if is_mac else "KVM",
        "platform": platform.system(),
        "arch": default_arch(),
        "avd_home": str(AVD_HOME),
    }


def list_system_images() -> list[dict]:
    """List installed system images by scanning the SDK directory."""
    images = []
    si_dir = SDK_ROOT / "system-images"
    if not si_dir.exists():
        return images
    for api_dir in sorted(si_dir.iterdir()):
        if not api_dir.is_dir():
            continue
        for target_dir in sorted(api_dir.iterdir()):
            if not target_dir.is_dir():
                continue
            for arch_dir in sorted(target_dir.iterdir()):
                if not arch_dir.is_dir():
                    continue
                api_str = api_dir.name  # e.g. android-35
                api_level = api_str.replace("android-", "")
                images.append(
                    {
                        "api_level": api_level,
                        "target": target_dir.name,
                        "arch": arch_dir.name,
                        "package": f"system-images;{api_str};{target_dir.name};{arch_dir.name}",
                        "path": str(arch_dir),
                    }
                )
    return images


def install_system_image(api_level: int, target: str = "google_apis_playstore", arch: str = "") -> dict:
    """Download a system image via sdkmanager. Requires cmdline-tools."""
    if not arch:
        arch = default_arch()
    if not _has_cmdline_tools():
        return {
            "ok": False,
            "error": 'cmdline-tools not installed. Run: sdkmanager --install "cmdline-tools;latest"',
        }
    pkg = f"system-images;android-{api_level};{target};{arch}"
    try:
        r = _run([str(SDKMANAGER), "--install", pkg], timeout=600)
        return {"ok": True, "package": pkg, "output": r.stdout[-500:]}
    except subprocess.CalledProcessError as e:
        return {"ok": False, "error": e.stderr[-500:]}


def list_avds(running_list: list[dict]) -> list[dict]:
    """List all created AVDs by reading .ini files from AVD_HOME.

    Args:
        running_list: output from list_running(), used to annotate status.
    """
    avds = []
    if not AVD_HOME.exists():
        return avds

    running = {info["name"]: info for info in running_list}

    for ini_file in sorted(AVD_HOME.glob("*.ini")):
        if ini_file.suffix != ".ini":
            continue
        name_from_file = ini_file.stem

        cfg = configparser.ConfigParser()
        cfg.read_string("[root]\n" + ini_file.read_text())
        avd_path_str = cfg.get("root", "path", fallback="")
        avd_path = Path(avd_path_str) if avd_path_str else None

        avd_info = {
            "name": name_from_file,
            "path": avd_path_str,
            "target": cfg.get("root", "target", fallback=""),
        }

        config_ini = avd_path / "config.ini" if avd_path else None
        if config_ini and config_ini.exists():
            lines = config_ini.read_text().splitlines()
            kv = {}
            for line in lines:
                if "=" in line:
                    k, v = line.split("=", 1)
                    kv[k.strip()] = v.strip()
            avd_info.update(
                {
                    "display_name": kv.get("avd.ini.displayname", name_from_file),
                    "api_level": kv.get("image.sysdir.1", "").split("/")[1].replace("android-", "")
                    if "image.sysdir.1" in kv
                    else "",
                    "target_flavor": kv.get("tag.display", ""),
                    "abi": kv.get("abi.type", ""),
                    "resolution": f"{kv.get('hw.lcd.width', '?')}x{kv.get('hw.lcd.height', '?')}",
                    "dpi": _safe_int(kv.get("hw.lcd.density", "0")),
                    "ram_mb": _safe_int(kv.get("hw.ramSize", "0")),
                    "disk": kv.get("disk.dataPartition.size", ""),
                    "gpu_mode": kv.get("hw.gpu.mode", ""),
                    "cores": _safe_int(kv.get("hw.cpu.ncore", "0")),
                    "playstore": kv.get("PlayStore.enabled", "false").lower() == "true",
                }
            )

        run_info = running.get(name_from_file)
        if run_info:
            adb_state = run_info.get("adb_state", "device")
            avd_info["status"] = "running" if adb_state == "device" else "booting"
            avd_info["serial"] = run_info["serial"]
            avd_info["pid"] = run_info.get("pid")
        else:
            avd_info["status"] = "stopped"
            avd_info["serial"] = None
            avd_info["pid"] = None

        avds.append(avd_info)
    return avds


def list_running(procs: dict, lock: threading.Lock) -> list[dict]:
    """List running emulators with serials and AVD names."""
    try:
        r = _run([ADB_BIN, "devices"], timeout=10, check=False)
    except (subprocess.SubprocessError, OSError):
        return []
    running = []
    for line in r.stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[0].startswith("emulator-") and parts[1] in ("device", "offline"):
            serial = parts[0]
            adb_state = parts[1]
            avd_name = "unknown"
            if adb_state == "device":
                name_out = _adb(serial, "emu", "avd", "name", timeout=5)
                avd_name = name_out.splitlines()[0].strip() if name_out else "unknown"
            pid = None
            with lock:
                proc = procs.get(serial)
                if proc and proc.poll() is None:
                    pid = proc.pid
            if pid is None:
                pid = find_emulator_pid(serial)
            running.append(
                {
                    "serial": serial,
                    "name": avd_name,
                    "pid": pid,
                    "adb_state": adb_state,
                }
            )
    return running


def find_emulator_pid(serial: str) -> Optional[int]:
    """Find PID of emulator process by matching port."""
    port = serial.replace("emulator-", "")
    try:
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            cmdline = proc.info.get("cmdline") or []
            if any("emulator" in str(c) for c in cmdline) and "-port" in cmdline:
                try:
                    port_idx = cmdline.index("-port")
                    if cmdline[port_idx + 1] == port:
                        return proc.info["pid"]
                except (ValueError, IndexError):
                    continue
    except Exception:
        pass
    return None
