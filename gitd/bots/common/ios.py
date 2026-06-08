#!/usr/bin/env python3
"""iOS automation primitives backed by Appium XCUITest/WebDriverAgent.

The public methods mirror the small Android ``Device`` surface used by the
agent layer: screenshot, XML dump, tap, swipe, type, app launch, and simple XML
helpers.  The implementation talks directly to Appium's W3C WebDriver HTTP API
so the first iOS milestone does not need the Python Appium client package.
"""
from __future__ import annotations

import base64
import html
import json
import os
import re
import signal
import shlex
import subprocess
import threading
import time
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import requests

IOS_PREFIX = "ios:"

_CLICKABLE_TYPES = {
    "XCUIElementTypeButton",
    "XCUIElementTypeCell",
    "XCUIElementTypeLink",
    "XCUIElementTypeTextField",
    "XCUIElementTypeSecureTextField",
    "XCUIElementTypeSearchField",
    "XCUIElementTypeSwitch",
    "XCUIElementTypeSlider",
    "XCUIElementTypePickerWheel",
    "XCUIElementTypeSegmentedControl",
    "XCUIElementTypeTabBar",
    "XCUIElementTypeTabBarItem",
}

_SCROLLABLE_TYPES = {
    "XCUIElementTypeCollectionView",
    "XCUIElementTypeScrollView",
    "XCUIElementTypeTable",
    "XCUIElementTypeWebView",
}

_KNOWN_IOS_POPUPS = [
    {"detect": "Turn on notifications", "button": "Not now", "label": "Notification prompt"},
    {"detect": "Not now", "button": "Not now", "label": "Not now dialog"},
    {"detect": "Allow", "button": "Allow", "label": "Permission dialog"},
    {"detect": "Don\u2019t Allow", "button": "Don\u2019t Allow", "label": "Permission denial dialog"},
    {"detect": "Don't Allow", "button": "Don't Allow", "label": "Permission denial dialog"},
    {"detect": "Skip", "button": "Skip", "label": "Skip dialog"},
    {"detect": "Cancel", "button": "Cancel", "label": "Cancel dialog"},
    {"detect": "Close", "button": "Close", "label": "Close dialog"},
]
_DISMISS_WORDS = {"not now", "skip", "cancel", "dismiss", "later", "close", "done"}
_DISMISS_EXACT = {"cancel", "dismiss", "close", "done", "not now", "don't allow", "don\u2019t allow"}

_ELEMENT_ID_KEYS = (
    "element-6066-11e4-a52e-4f735466cecf",
    "ELEMENT",
)
_IOS_DEVICE_NAME_RE = re.compile(r"\b(iPhone|iPad|iPod)\b", re.I)
_IOS_HARDWARE_UDID_RE = re.compile(r"^(?:[A-F0-9]{40}|[A-F0-9]{8}-[A-F0-9]{16})$", re.I)
_IOS_SIMULATOR_UDID_RE = re.compile(
    r"^[A-F0-9]{8}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{12}$",
    re.I,
)
_MAC_HOST_NAME_RE = re.compile(r"\b(Mac|MacBook|iMac|Mac mini|Mac Studio|Laptop|Desktop)\b", re.I)
_REMOTE_XPC_REGISTRY_PORTS = (42314,)


class IOSBackendError(RuntimeError):
    """Raised when Appium/WDA cannot satisfy a requested iOS operation."""


class IOSSessionInvalid(IOSBackendError):
    """Raised when Appium reports a cached session is no longer valid."""


@dataclass(frozen=True)
class IOSSessionConfig:
    appium_url: str
    udid: str
    bundle_id: str
    browser_name: str
    device_name: str
    platform_version: str
    wda_url: str
    capability_items: tuple[tuple[str, Any], ...]


@dataclass(frozen=True)
class IOSDeviceConfig:
    udid: str
    appium_url: str = "http://127.0.0.1:4723"
    bundle_id: str = "com.apple.mobilesafari"
    browser_name: str = ""
    device_name: str = "iPhone"
    platform_version: str = ""
    wda_url: str = ""
    timeout: float = 120.0
    mjpeg_server_port: int = 9100
    mjpeg_screenshot_url: str = ""
    mjpeg_server_framerate: int = 0
    mjpeg_scaling_factor: float = 0.0
    mjpeg_server_screenshot_quality: int = 0
    mjpeg_fix_orientation: bool | None = None
    screenshot_quality: int = 0
    xcode_org_id: str = ""
    xcode_signing_id: str = ""
    updated_wda_bundle_id: str = ""
    derived_data_path: str = ""
    allow_provisioning_device_registration: bool | None = None
    show_xcode_log: bool | None = None
    use_prebuilt_wda: bool | None = None
    wda_launch_timeout: int = 0
    wda_connection_timeout: int = 0
    wda_startup_retries: int = 0
    wda_startup_retry_interval: int = 0
    known_apps: tuple[tuple[str, str], ...] = ()

    def capabilities(self) -> dict[str, Any]:
        caps: dict[str, Any] = {}
        string_caps = {
            "xcode_org_id": "appium:xcodeOrgId",
            "xcode_signing_id": "appium:xcodeSigningId",
            "updated_wda_bundle_id": "appium:updatedWDABundleId",
            "derived_data_path": "appium:derivedDataPath",
            "mjpeg_screenshot_url": "appium:mjpegScreenshotUrl",
        }
        int_caps = {
            "wda_launch_timeout": "appium:wdaLaunchTimeout",
            "wda_connection_timeout": "appium:wdaConnectionTimeout",
            "wda_startup_retries": "appium:wdaStartupRetries",
            "wda_startup_retry_interval": "appium:wdaStartupRetryInterval",
            "mjpeg_server_port": "appium:mjpegServerPort",
            "screenshot_quality": "appium:screenshotQuality",
        }
        bool_caps = {
            "allow_provisioning_device_registration": "appium:allowProvisioningDeviceRegistration",
            "show_xcode_log": "appium:showXcodeLog",
            "use_prebuilt_wda": "appium:usePrebuiltWDA",
        }
        for field_name, cap_name in string_caps.items():
            value = getattr(self, field_name)
            if value:
                caps[cap_name] = value
        for field_name, cap_name in int_caps.items():
            value = getattr(self, field_name)
            if value:
                caps[cap_name] = int(value)
        for field_name, cap_name in bool_caps.items():
            value = getattr(self, field_name)
            if value is not None:
                caps[cap_name] = bool(value)
        for setting_name, value in self.mjpeg_settings().items():
            caps[f"appium:settings[{setting_name}]"] = value
        return caps

    def mjpeg_settings(self) -> dict[str, Any]:
        settings: dict[str, Any] = {}
        if self.mjpeg_server_framerate:
            settings["mjpegServerFramerate"] = int(self.mjpeg_server_framerate)
        if self.mjpeg_scaling_factor:
            settings["mjpegScalingFactor"] = float(self.mjpeg_scaling_factor)
        if self.mjpeg_server_screenshot_quality:
            settings["mjpegServerScreenshotQuality"] = int(self.mjpeg_server_screenshot_quality)
        if self.mjpeg_fix_orientation is not None:
            settings["mjpegFixOrientation"] = bool(self.mjpeg_fix_orientation)
        return settings


@dataclass
class IOSDeviceStatus:
    device: str
    udid: str
    state: str
    message: str
    appium_url: str
    session_id: str = ""
    active_app: dict[str, Any] | None = None
    screen_size: dict[str, int] | None = None
    checks: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["platform"] = "ios"
        return data


_CONFIG_ENV_FIELDS = {
    "IOS_APPIUM_URL": "appium_url",
    "IOS_BUNDLE_ID": "bundle_id",
    "IOS_BROWSER_NAME": "browser_name",
    "IOS_DEVICE_NAME": "device_name",
    "IOS_PLATFORM_VERSION": "platform_version",
    "IOS_WDA_URL": "wda_url",
    "IOS_WEBDRIVERAGENT_URL": "wda_url",
    "IOS_APPIUM_TIMEOUT": "timeout",
    "IOS_MJPEG_SERVER_PORT": "mjpeg_server_port",
    "IOS_MJPEG_SCREENSHOT_URL": "mjpeg_screenshot_url",
    "IOS_MJPEG_SERVER_FRAMERATE": "mjpeg_server_framerate",
    "IOS_MJPEG_SCALING_FACTOR": "mjpeg_scaling_factor",
    "IOS_MJPEG_SERVER_SCREENSHOT_QUALITY": "mjpeg_server_screenshot_quality",
    "IOS_MJPEG_FIX_ORIENTATION": "mjpeg_fix_orientation",
    "IOS_SCREENSHOT_QUALITY": "screenshot_quality",
    "IOS_XCODE_ORG_ID": "xcode_org_id",
    "IOS_XCODE_SIGNING_ID": "xcode_signing_id",
    "IOS_UPDATED_WDA_BUNDLE_ID": "updated_wda_bundle_id",
    "IOS_DERIVED_DATA_PATH": "derived_data_path",
    "IOS_ALLOW_PROVISIONING_DEVICE_REGISTRATION": "allow_provisioning_device_registration",
    "IOS_SHOW_XCODE_LOG": "show_xcode_log",
    "IOS_USE_PREBUILT_WDA": "use_prebuilt_wda",
    "IOS_WDA_LAUNCH_TIMEOUT": "wda_launch_timeout",
    "IOS_WDA_CONNECTION_TIMEOUT": "wda_connection_timeout",
    "IOS_WDA_STARTUP_RETRIES": "wda_startup_retries",
    "IOS_WDA_STARTUP_RETRY_INTERVAL": "wda_startup_retry_interval",
    "IOS_KNOWN_APPS_JSON": "known_apps",
    "IOS_APPS_JSON": "known_apps",
}

_INT_CONFIG_FIELDS = {
    "mjpeg_server_port",
    "wda_launch_timeout",
    "wda_connection_timeout",
    "wda_startup_retries",
    "wda_startup_retry_interval",
    "mjpeg_server_framerate",
    "mjpeg_server_screenshot_quality",
    "screenshot_quality",
}
_FLOAT_CONFIG_FIELDS = {"timeout", "mjpeg_scaling_factor"}
_BOOL_CONFIG_FIELDS = {
    "allow_provisioning_device_registration",
    "show_xcode_log",
    "use_prebuilt_wda",
    "mjpeg_fix_orientation",
}

_BROWSER_CONTROL_TEXT = {
    "chrome",
    "address",
    "tabs",
    "tab switcher",
    "share",
    "menu",
    "reload",
    "back",
    "forward",
    "new tab",
    "done",
    "cancel",
    "search or type web address",
}

_BROWSER_FIRST_RUN_ACTIONS = {
    "accept",
    "accept & continue",
    "accept and continue",
    "agree",
    "continue",
    "done",
    "got it",
    "no thanks",
    "not now",
    "skip",
    "start browsing",
    "use without an account",
}


def _looks_like_address_bar_text(value: str) -> bool:
    label = re.sub(r"\s+", " ", str(value or "").strip().lower())
    if not label:
        return False
    if "address" in label or "url" in label or "web address" in label:
        return True
    return "search" in label and ("type" in label or "enter" in label or "web" in label)


_LOW_VALUE_ARTICLE_TERMS = {
    "advertisement",
    "cookie",
    "donate",
    "email",
    "newsletter",
    "notifications",
    "privacy",
    "profile",
    "sign in",
    "sign up",
    "subscribe",
    "terms",
}

_ARTICLE_URL_HINTS = (
    "article",
    "story",
    "news",
    "world",
    "politics",
    "business",
    "economy",
    "science",
    "health",
    "culture",
    "sports",
)

_COMMON_IOS_APPS: tuple[tuple[str, str], ...] = (
    ("Chrome", "com.google.chrome.ios"),
    ("Safari", "com.apple.mobilesafari"),
    ("Settings", "com.apple.Preferences"),
    ("Camera", "com.apple.camera"),
    ("Photos", "com.apple.mobileslideshow"),
    ("Messages", "com.apple.MobileSMS"),
    ("Phone", "com.apple.mobilephone"),
    ("Mail", "com.apple.mobilemail"),
    ("App Store", "com.apple.AppStore"),
    ("Gmail", "com.google.Gmail"),
    ("Google Maps", "com.google.Maps"),
    ("Google Photos", "com.google.photos"),
    ("YouTube", "com.google.ios.youtube"),
    ("TikTok", "com.zhiliaoapp.musically"),
    ("Instagram", "com.burbn.instagram"),
    ("Facebook", "com.facebook.Facebook"),
    ("Messenger", "com.facebook.Messenger"),
    ("WhatsApp", "net.whatsapp.WhatsApp"),
    ("X", "com.atebits.Tweetie2"),
    ("Reddit", "com.reddit.Reddit"),
    ("Spotify", "com.spotify.client"),
)

_IOS_APP_STATE_NAMES = {
    0: "not_installed",
    1: "not_running",
    2: "running_background_suspended",
    3: "running_background",
    4: "running_foreground",
}

_IOS_NOTIFICATION_SKIP_TEXT = {
    "clear",
    "clear all",
    "notification center",
    "notifications",
    "no notifications",
    "no older notifications",
    "scheduled summary",
    "today",
    "earlier",
}

_WEB_TEXT_JS = r"""
const maxEntries = arguments[0] || 300;
const clean = (value) => String(value || '').replace(/\s+/g, ' ').trim();
const visible = (el) => {
  const style = window.getComputedStyle(el);
  if (!style || style.visibility === 'hidden' || style.display === 'none') return false;
  const rect = el.getBoundingClientRect();
  if (rect.width <= 0 || rect.height <= 0) return false;
  if (rect.bottom < 0 || rect.right < 0) return false;
  if (rect.top > window.innerHeight || rect.left > window.innerWidth) return false;
  return true;
};
const nodes = Array.from(document.querySelectorAll(
  'article h1, article h2, article h3, h1, h2, h3, [role="heading"], a, p'
));
const seen = new Set();
const entries = [];
for (const el of nodes) {
  if (!visible(el)) continue;
  const text = clean(el.innerText || el.textContent);
  if (!text || text.length < 2) continue;
  const rect = el.getBoundingClientRect();
  const key = `${text}:${Math.round(rect.top)}:${Math.round(rect.left)}`;
  if (seen.has(key)) continue;
  seen.add(key);
  const anchor = el.closest('a') || (el.tagName === 'A' ? el : null);
  entries.push({
    text,
    tag: String(el.tagName || '').toLowerCase(),
    role: el.getAttribute('role') || '',
    href: anchor ? anchor.href || '' : '',
    bounds: {
      x1: Math.round(rect.left),
      y1: Math.round(rect.top),
      x2: Math.round(rect.right),
      y2: Math.round(rect.bottom),
    },
    provenance: 'web_context',
  });
  if (entries.length >= maxEntries) break;
}
return {
  url: window.location ? window.location.href : '',
  title: document.title || '',
  bodyText: document.body ? clean(document.body.innerText || document.body.textContent) : '',
  viewport: {width: window.innerWidth, height: window.innerHeight},
  entries,
};
"""


def strip_ios_prefix(device: str) -> str:
    return device[len(IOS_PREFIX) :] if device.startswith(IOS_PREFIX) else device


def is_ios_ref(device: str | None) -> bool:
    return bool(device and device.startswith(IOS_PREFIX))


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).lower() in {"1", "true", "yes"}


def _clean_config_value(field_name: str, value: Any) -> Any:
    if value in ("", None):
        return None
    if field_name == "known_apps":
        return _normalize_ios_app_inventory(value)
    if field_name in _BOOL_CONFIG_FIELDS:
        return _as_bool(value)
    if field_name in _INT_CONFIG_FIELDS:
        return _intish(value)
    if field_name in _FLOAT_CONFIG_FIELDS:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    return str(value)


def _looks_like_bundle_id(value: str) -> bool:
    return "." in value and not any(ch.isspace() for ch in value)


def _guess_ios_app_name(bundle_id: str) -> str:
    for name, known_bundle_id in _COMMON_IOS_APPS:
        if known_bundle_id == bundle_id:
            return name
    parts = [p for p in re.split(r"[.\-_]+", bundle_id) if p]
    ignored = {"ios", "iphone", "ipad", "client", "app", "mobile"}
    token = next((part for part in reversed(parts) if part.lower() not in ignored), bundle_id)
    if token.isupper():
        return token
    return token.replace("_", " ").replace("-", " ").title()


def _normalize_ios_app_inventory(value: Any) -> tuple[tuple[str, str], ...]:
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return ()
        if raw.startswith("{") or raw.startswith("["):
            try:
                value = json.loads(raw)
            except json.JSONDecodeError:
                return ()
        else:
            value = [item.strip() for item in raw.split(",") if item.strip()]

    rows: list[tuple[str, str]] = []
    if isinstance(value, dict):
        items = value.items()
        for raw_name, raw_bundle_id in items:
            if isinstance(raw_bundle_id, dict):
                name = str(raw_bundle_id.get("name") or raw_name or "").strip()
                bundle_id = str(
                    raw_bundle_id.get("bundle_id")
                    or raw_bundle_id.get("bundleId")
                    or raw_bundle_id.get("package")
                    or raw_bundle_id.get("app_package")
                    or raw_bundle_id.get("id")
                    or ""
                ).strip()
            else:
                left = str(raw_name or "").strip()
                right = str(raw_bundle_id or "").strip()
                if _looks_like_bundle_id(left) and not _looks_like_bundle_id(right):
                    name, bundle_id = right or _guess_ios_app_name(left), left
                else:
                    name, bundle_id = left, right
            if bundle_id:
                rows.append((name or _guess_ios_app_name(bundle_id), bundle_id))
    elif isinstance(value, list | tuple):
        for item in value:
            if isinstance(item, dict):
                bundle_id = str(
                    item.get("bundle_id")
                    or item.get("bundleId")
                    or item.get("package")
                    or item.get("app_package")
                    or item.get("id")
                    or ""
                ).strip()
                name = str(item.get("name") or item.get("label") or "").strip()
            else:
                bundle_id = str(item or "").strip()
                name = ""
            if bundle_id:
                rows.append((name or _guess_ios_app_name(bundle_id), bundle_id))

    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for name, bundle_id in rows:
        if bundle_id in seen:
            continue
        seen.add(bundle_id)
        out.append((name, bundle_id))
    return tuple(out)


def _skill_ios_app_inventory() -> tuple[tuple[str, str], ...]:
    """Return iOS bundle ids declared by local skill metadata."""
    try:
        import yaml
    except Exception:
        return ()

    skills_dir = Path(__file__).resolve().parents[2] / "skills"
    rows: list[tuple[str, str]] = []
    seen: set[str] = set()
    for meta_path in sorted(skills_dir.glob("*/skill.yaml")):
        try:
            meta = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        bundle_id = str(meta.get("ios_bundle_id") or "").strip()
        if not bundle_id or bundle_id in seen:
            continue
        raw_platforms = meta.get("platforms") or []
        platforms = raw_platforms if isinstance(raw_platforms, (list, tuple, set)) else [raw_platforms]
        explicit_platforms = {str(platform).strip().lower() for platform in platforms if str(platform).strip()}
        if explicit_platforms and "ios" not in explicit_platforms:
            continue
        seen.add(bundle_id)
        rows.append((_guess_ios_app_name(bundle_id), bundle_id))
    return tuple(rows)


def _load_ios_devices_blob() -> dict[str, Any]:
    raw = os.getenv("IOS_DEVICES_JSON", "").strip()
    if not raw and os.getenv("IOS_CONFIG_FILE"):
        try:
            with open(os.environ["IOS_CONFIG_FILE"], encoding="utf-8") as fh:
                raw = fh.read()
        except OSError:
            raw = ""
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if isinstance(data, dict) and isinstance(data.get("devices"), dict):
        return data["devices"]
    if isinstance(data, dict):
        return data
    return {}


def _host_device_config_for_udid(udid: str) -> dict[str, str]:
    if not (_IOS_HARDWARE_UDID_RE.match(udid) or _IOS_SIMULATOR_UDID_RE.match(udid)):
        return {}
    try:
        devices = discover_host_ios_devices(include_simulators=True)
    except Exception:
        return {}
    return next((item for item in devices if item.get("udid") == udid), {})


def _appium_url_is_loopback(appium_url: str) -> bool:
    parsed = urllib.parse.urlparse(appium_url)
    host = parsed.hostname or "127.0.0.1"
    return host in {"127.0.0.1", "localhost", "::1"}


def _requires_host_device_visibility(appium_url: str, udid: str) -> bool:
    return _appium_url_is_loopback(appium_url) and (
        _IOS_HARDWARE_UDID_RE.match(udid) is not None or _IOS_SIMULATOR_UDID_RE.match(udid) is not None
    )


def _ios_major_version(version: str) -> int:
    match = re.search(r"\d+", str(version or ""))
    return int(match.group(0)) if match else 0


def _remote_xpc_registry_ports() -> tuple[int, ...]:
    raw = os.getenv("IOS_REMOTE_XPC_REGISTRY_PORTS", "") or os.getenv("IOS_REMOTE_XPC_REGISTRY_PORT", "")
    if not raw.strip():
        return _REMOTE_XPC_REGISTRY_PORTS
    ports: list[int] = []
    seen: set[int] = set()
    for part in re.split(r"[,\s]+", raw):
        try:
            port = int(part)
        except ValueError:
            continue
        if 0 < port <= 65535 and port not in seen:
            seen.add(port)
            ports.append(port)
    return tuple(ports) or _REMOTE_XPC_REGISTRY_PORTS


def _remote_xpc_tunnel_start_timeout() -> float:
    raw = os.getenv("IOS_REMOTE_XPC_TUNNEL_START_TIMEOUT", "10")
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 10.0


def _remote_xpc_tunnel_processes(udid: str) -> list[dict[str, Any]]:
    clean_udid = strip_ios_prefix(udid)
    try:
        output = subprocess.check_output(["ps", "-eo", "pid=,uid=,command="], text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return []
    rows: list[dict[str, Any]] = []
    for raw_line in output.splitlines():
        parts = raw_line.strip().split(None, 2)
        if len(parts) < 3:
            continue
        pid_raw, uid_raw, command = parts
        if "tunnel-creation" not in command or clean_udid not in command:
            continue
        try:
            pid = int(pid_raw)
            uid = int(uid_raw)
        except ValueError:
            continue
        rows.append({"pid": pid, "uid": uid, "command": command})
    return rows


def remote_xpc_manual_recovery(udid: str, tunnel: dict[str, Any] | None = None) -> dict[str, Any]:
    clean_udid = strip_ios_prefix(udid)
    processes = _remote_xpc_tunnel_processes(clean_udid)
    current_uid = os.getuid()
    foreign = [proc for proc in processes if proc["uid"] != current_uid]
    stale = foreign or processes
    registry_ports = tunnel.get("checked_ports") if isinstance(tunnel, dict) else None
    ports = registry_ports or list(_remote_xpc_registry_ports())
    registry_port = ports[0] if ports else _REMOTE_XPC_REGISTRY_PORTS[0]
    verify_url = f"http://127.0.0.1:{registry_port}/remotexpc/tunnels/{clean_udid}"
    steps: list[str] = []
    if stale:
        prefix = "Stop the stale process ids with sudo" if foreign else "Stop the stale process ids"
        steps.append(f"{prefix}: {', '.join(str(proc['pid']) for proc in stale)}")
    else:
        steps.append("Stop any stale XCUITest tunnel process for this device.")
    kill_command = ""
    if stale:
        kill_prefix = "sudo kill" if foreign else "kill"
        kill_command = f"{kill_prefix} {' '.join(str(proc['pid']) for proc in stale)}"
    start_command = f"sudo appium driver run xcuitest tunnel-creation --udid {clean_udid}"
    verify_command = f"curl -s {verify_url}"
    steps.extend(
        [
            f"Run: {start_command}",
            f"Verify: {verify_url}",
        ]
    )
    return {
        "code": "restart_remote_xpc_tunnel",
        "state": "remote_xpc_tunnel_unavailable",
        "summary": "Stop the stale XCUITest tunnel process with sudo, then start a fresh tunnel.",
        "steps": steps,
        "processes": processes,
        "foreign_processes": foreign,
        "verify_url": verify_url,
        "registry_port": registry_port,
        "commands": [cmd for cmd in [kill_command, start_command, verify_command] if cmd],
        "kill_command": kill_command,
        "start_command": start_command,
        "verify_command": verify_command,
    }


def _parse_devicectl_details(output: str) -> dict[str, str]:
    fields = {
        "identifier": "identifier",
        "name": "name",
        "osVersionNumber": "os_version",
        "bootState": "boot_state",
        "developerModeStatus": "developer_mode",
        "pairingState": "pairing_state",
        "transportType": "transport_type",
        "tunnelState": "tunnel_state",
        "tunnelIPAddress": "tunnel_ip_address",
        "tunnelTransportProtocol": "tunnel_transport_protocol",
    }
    details: dict[str, str] = {}
    for raw_line in output.splitlines():
        line = raw_line.strip().lstrip("•").strip()
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        field = fields.get(key.strip())
        if field and value.strip():
            details[field] = value.strip()
    return details


def devicectl_device_details(udid: str) -> dict[str, str]:
    try:
        output = subprocess.check_output(
            ["xcrun", "devicectl", "device", "info", "details", "--device", strip_ios_prefix(udid)],
            stderr=subprocess.STDOUT,
            timeout=10,
            text=True,
        )
    except (OSError, subprocess.SubprocessError) as e:
        return {"error": str(e)}
    return _parse_devicectl_details(output)


def remote_xpc_tunnel_status(udid: str, *, platform_version: str = "", host: dict | None = None) -> dict[str, Any]:
    host = host if host is not None else _host_device_config_for_udid(udid)
    platform_version = platform_version or host.get("platform_version", "")
    required = host.get("source") == "host" and _ios_major_version(platform_version) >= 18
    registry_ports = _remote_xpc_registry_ports()
    status: dict[str, Any] = {
        "required": required,
        "state": "not_required",
        "ok": True,
        "checked_ports": list(registry_ports),
        "registry": {},
        "devicectl": {},
    }
    if not required:
        return status

    registry: dict[str, Any] = {}
    for port in registry_ports:
        url = f"http://127.0.0.1:{port}/remotexpc/tunnels/{strip_ios_prefix(udid)}"
        try:
            resp = requests.request("GET", url, timeout=1)
            registry = {"port": port, "status_code": resp.status_code, "url": url}
            if resp.status_code < 400:
                try:
                    body = resp.json()
                except ValueError:
                    body = {}
                if isinstance(body, dict):
                    registry.update(body)
                break
        except requests.RequestException as e:
            registry = {"port": port, "url": url, "error": str(e)}
    status["registry"] = registry

    if registry.get("status") != "OK":
        status.update(
            {
                "ok": False,
                "state": "missing",
                "message": "RemoteXPC tunnel registry is missing the device entry.",
            }
        )
        return status

    devicectl = devicectl_device_details(udid)
    status["devicectl"] = devicectl
    registry_address = str(registry.get("address") or "")
    current_address = str(devicectl.get("tunnel_ip_address") or "")
    if registry_address and current_address and registry_address != current_address:
        status.update(
            {
                "ok": False,
                "state": "stale",
                "message": "RemoteXPC tunnel registry points at a stale tunnel address.",
                "registry_address": registry_address,
                "current_address": current_address,
                "devicectl_connected": devicectl.get("tunnel_state") == "connected",
                "stale_reason": "registry_address_mismatch",
            }
        )
        return status

    status.update({"state": "available", "ok": True})
    return status


def _config_dict_for_udid(udid: str) -> dict[str, Any]:
    clean_udid = strip_ios_prefix(udid)
    cfg: dict[str, Any] = {"udid": clean_udid}
    for env_name, field_name in _CONFIG_ENV_FIELDS.items():
        if env_name in os.environ:
            value = _clean_config_value(field_name, os.getenv(env_name))
            if value is not None:
                cfg[field_name] = value

    for key, raw_value in _load_ios_devices_blob().items():
        if strip_ios_prefix(str(key)) != clean_udid or not isinstance(raw_value, dict):
            continue
        for raw_field, raw_value_item in raw_value.items():
            field_name = _CONFIG_ENV_FIELDS.get(raw_field, raw_field)
            if field_name not in IOSDeviceConfig.__dataclass_fields__ or field_name == "udid":
                continue
            value = _clean_config_value(field_name, raw_value_item)
            if value is not None:
                cfg[field_name] = value

    host = _host_device_config_for_udid(clean_udid)
    if host.get("name") and not cfg.get("device_name"):
        cfg["device_name"] = host["name"]
    if host.get("platform_version") and not cfg.get("platform_version"):
        cfg["platform_version"] = host["platform_version"]
    return cfg


def ios_config_for_udid(udid: str) -> IOSDeviceConfig:
    return IOSDeviceConfig(**_config_dict_for_udid(udid))


def configured_ios_udids() -> list[str]:
    values: list[str] = []
    single = os.getenv("IOS_DEVICE_UDID", "").strip()
    if single:
        values.append(single)
    multi = os.getenv("IOS_DEVICE_UDIDS", "").strip()
    if multi:
        values.extend(v.strip() for v in multi.split(",") if v.strip())
    values.extend(str(k) for k in _load_ios_devices_blob().keys())

    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        udid = strip_ios_prefix(value)
        if udid and udid not in seen:
            seen.add(udid)
            out.append(udid)
    return out


def _xctrace_line_device(line: str, section: str) -> dict[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("=="):
        return None
    groups = re.findall(r"\(([^()]*)\)", stripped)
    if len(groups) < 2:
        return None
    state = ""
    udid = groups[-1].strip()
    if section == "simulators" and groups[-1] in {"Booted", "Shutdown", "Creating", "Shutting Down"}:
        state = groups[-1]
        udid = groups[-2].strip()
    if section == "simulators" and state != "Booted":
        return None
    if not udid or "unavailable" in stripped.lower():
        return None
    name = stripped.split(" (", 1)[0].strip()
    if section == "devices":
        if _MAC_HOST_NAME_RE.search(name):
            return None
        if not (_IOS_DEVICE_NAME_RE.search(name) or _IOS_HARDWARE_UDID_RE.match(udid)):
            return None
    elif not _IOS_DEVICE_NAME_RE.search(name):
        return None
    version = groups[0].strip()
    return {
        "udid": strip_ios_prefix(udid),
        "name": name,
        "platform_version": version,
        "source": "simulator" if section == "simulators" else "host",
        "state": state or "connected",
    }


def _parse_xctrace_devices(output: str, *, include_simulators: bool = True) -> list[dict[str, str]]:
    section = ""
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if line == "== Devices ==":
            section = "devices"
            continue
        if line == "== Simulators ==":
            section = "simulators"
            continue
        if line.startswith("=="):
            section = ""
            continue
        if section == "simulators" and not include_simulators:
            continue
        if section not in {"devices", "simulators"}:
            continue
        item = _xctrace_line_device(line, section)
        if not item or item["udid"] in seen:
            continue
        seen.add(item["udid"])
        rows.append(item)
    return rows


def discover_host_ios_devices(*, include_simulators: bool = True) -> list[dict[str, str]]:
    """Discover connected iOS devices and booted simulators through Xcode tools.

    Discovery is best-effort: hosts without Xcode/xcrun simply return no rows.
    Explicit IOS_DEVICE_UDID/IOS_DEVICES_JSON config remains the source for
    Appium details such as ports and signing capabilities.
    """
    try:
        output = subprocess.check_output(
            ["xcrun", "xctrace", "list", "devices"],
            stderr=subprocess.DEVNULL,
            timeout=5,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    return _parse_xctrace_devices(output, include_simulators=include_simulators)


def known_ios_udids(*, include_host: bool = True, include_simulators: bool = True) -> list[str]:
    values = configured_ios_udids()
    if include_host:
        values.extend(device["udid"] for device in discover_host_ios_devices(include_simulators=include_simulators))
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        udid = strip_ios_prefix(value)
        if udid and udid not in seen:
            seen.add(udid)
            out.append(udid)
    return out


def _env_capabilities() -> dict[str, Any]:
    udid = os.getenv("IOS_DEVICE_UDID", "")
    return ios_config_for_udid(udid).capabilities() if udid else {}


def _intish(value: str | float | int | None) -> int:
    try:
        return int(round(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _png_size(data: bytes) -> tuple[int, int] | None:
    if len(data) >= 24 and data[:8] == b"\x89PNG\r\n\x1a\n":
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    return None


def _safe_attr(value: Any) -> str:
    return "" if value is None else str(value)


def _label_for_ios_node(node: ET.Element) -> tuple[str, str, str]:
    """Return Android-shaped text/content-desc/resource-id values."""
    value = _safe_attr(node.get("value")).strip()
    label = _safe_attr(node.get("label")).strip()
    name = _safe_attr(node.get("name")).strip()
    node_type = _safe_attr(node.get("type") or node.tag).strip()

    text = value or label or name
    if node_type in _SCROLLABLE_TYPES and text == node_type:
        text = ""
    desc = label or name
    rid = name
    return text, desc, rid


def _node_bounds(node: ET.Element, scale_x: float, scale_y: float) -> tuple[str, str, bool]:
    x = float(node.get("x") or 0)
    y = float(node.get("y") or 0)
    w = float(node.get("width") or 0)
    h = float(node.get("height") or 0)
    if w <= 0 or h <= 0:
        return "[0,0][0,0]", "[0,0][0,0]", False

    px1 = _intish(x * scale_x)
    py1 = _intish(y * scale_y)
    px2 = _intish((x + w) * scale_x)
    py2 = _intish((y + h) * scale_y)
    point_bounds = f"[{_intish(x)},{_intish(y)}][{_intish(x + w)},{_intish(y + h)}]"
    return f"[{px1},{py1}][{px2},{py2}]", point_bounds, True


def normalize_wda_xml(source_xml: str, scale_x: float = 1.0, scale_y: float = 1.0) -> str:
    """Convert Appium/WDA XML into Android uiautomator-shaped XML."""
    if not source_xml:
        return ""
    try:
        src_root = ET.fromstring(source_xml)
    except ET.ParseError:
        return source_xml

    root = ET.Element("hierarchy", {"rotation": "0", "platform": "ios"})

    def walk(src: ET.Element, dst_parent: ET.Element, index: int = 0):
        node_type = _safe_attr(src.get("type") or src.tag)
        text, desc, rid = _label_for_ios_node(src)
        bounds, point_bounds, has_bounds = _node_bounds(src, scale_x, scale_y)
        visible = src.get("visible")
        enabled = src.get("enabled")
        clickable = (
            has_bounds
            and node_type in _CLICKABLE_TYPES
            and (visible is None or _as_bool(visible))
            and (enabled is None or _as_bool(enabled))
        )
        scrollable = has_bounds and node_type in _SCROLLABLE_TYPES

        dst = ET.SubElement(
            dst_parent,
            "node",
            {
                "index": str(index),
                "text": text,
                "resource-id": rid,
                "class": node_type,
                "content-desc": desc,
                "clickable": str(clickable).lower(),
                "scrollable": str(scrollable).lower(),
                "enabled": str(enabled if enabled is not None else "").lower(),
                "visible": str(visible if visible is not None else "").lower(),
                "bounds": bounds,
                "ios-point-bounds": point_bounds,
            },
        )
        for child_index, child in enumerate(list(src)):
            walk(child, dst, child_index)

    top_nodes = list(src_root) if src_root.tag == "AppiumAUT" else [src_root]
    for child_index, child in enumerate(top_nodes):
        walk(child, root, child_index)

    return '<?xml version="1.0" encoding="UTF-8"?>' + ET.tostring(root, encoding="unicode")


def ios_xml_to_elements(xml: str, interactive_only: bool = True) -> list[dict]:
    """Parse normalized iOS XML into the same element list shape as Android."""
    normalized = normalize_wda_xml(xml) if "<hierarchy" not in xml else xml
    try:
        root = ET.fromstring(normalized)
    except ET.ParseError:
        return []

    elements: list[dict] = []
    for node in root.iter("node"):
        text = node.get("text", "") or ""
        desc = node.get("content-desc", "") or ""
        rid = node.get("resource-id", "") or ""
        cls = (node.get("class", "") or "").split(".")[-1]
        clickable = node.get("clickable", "") == "true"
        scrollable = node.get("scrollable", "") == "true"
        if interactive_only and not clickable and not scrollable and not text and not desc:
            continue
        bounds = IOSDevice.node_bounds_static(ET.tostring(node, encoding="unicode"))
        if not bounds:
            continue
        x1, y1, x2, y2 = bounds
        elements.append(
            {
                "idx": len(elements),
                "text": text,
                "content_desc": desc,
                "resource_id": rid.split("/")[-1] if "/" in rid else rid,
                "class": cls,
                "bounds": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
                "center": {"x": (x1 + x2) // 2, "y": (y1 + y2) // 2},
                "clickable": clickable,
                "scrollable": scrollable,
            }
        )
    return elements


class IOSDevice:
    """One iOS device/simulator controlled through Appium XCUITest."""

    _sessions: dict[IOSSessionConfig, str] = {}
    _sessions_lock = threading.RLock()

    def __init__(
        self,
        serial: str,
        *,
        appium_url: str | None = None,
        bundle_id: str | None = None,
        browser_name: str | None = None,
        timeout: float | None = None,
    ):
        self.serial = serial if serial.startswith(IOS_PREFIX) else f"{IOS_PREFIX}{serial}"
        self.udid = strip_ios_prefix(serial)
        self.config = ios_config_for_udid(self.udid)
        self.appium_url = (appium_url or self.config.appium_url).rstrip("/")
        self.bundle_id = bundle_id if bundle_id is not None else self.config.bundle_id
        self.browser_name = browser_name if browser_name is not None else self.config.browser_name
        self.device_name = self.config.device_name
        self.platform_version = self.config.platform_version
        self.wda_url = self.config.wda_url
        self.timeout = float(timeout if timeout is not None else self.config.timeout)
        self.mjpeg_server_port = self.config.mjpeg_server_port
        self.mjpeg_screenshot_url = self.config.mjpeg_screenshot_url
        self.mjpeg_server_framerate = self.config.mjpeg_server_framerate
        self.mjpeg_scaling_factor = self.config.mjpeg_scaling_factor
        self.mjpeg_server_screenshot_quality = self.config.mjpeg_server_screenshot_quality
        self.mjpeg_fix_orientation = self.config.mjpeg_fix_orientation
        self.screenshot_quality = self.config.screenshot_quality
        self.appium_capabilities = self.config.capabilities()
        self._session_id: str | None = None
        self._scale: tuple[float, float] | None = None
        self._screen_size: tuple[int, int] | None = None
        self._window_rect_cache: dict | None = None

    @property
    def platform(self) -> str:
        return "ios"

    @property
    def _config(self) -> IOSSessionConfig:
        return IOSSessionConfig(
            self.appium_url,
            self.udid,
            self.bundle_id,
            self.browser_name,
            self.device_name,
            self.platform_version,
            self.wda_url,
            tuple(sorted(self.appium_capabilities.items())),
        )

    def _url(self, path: str) -> str:
        return self.appium_url + path

    @staticmethod
    def _invalid_session_message(status_code: int, value: Any, text: str = "") -> bool:
        message = ""
        if isinstance(value, dict):
            message = f"{value.get('error', '')} {value.get('message', '')}"
        else:
            message = str(value or "")
        message = f"{message} {text}".lower()
        return status_code in {404, 410} and (
            "invalid session" in message
            or "session not found" in message
            or "no such driver" in message
            or "does not exist" in message
        )

    def _evict_session(self, session_id: str | None = None) -> None:
        with IOSDevice._sessions_lock:
            sid = session_id or self._session_id
            if sid and IOSDevice._sessions.get(self._config) == sid:
                IOSDevice._sessions.pop(self._config, None)
            if self._session_id == sid or session_id is None:
                self._session_id = None
            self._scale = None
            self._screen_size = None
            self._window_rect_cache = None

    def _clear_instance_session(self) -> None:
        self._session_id = None
        self._scale = None
        self._screen_size = None
        self._window_rect_cache = None

    def set_target_app(self, *, bundle_id: str | None = None, browser_name: str | None = None) -> None:
        """Switch the Appium session target without reusing the wrong session.

        A bundle-id override is a concrete app target, so it intentionally clears
        any configured ``browserName`` capability.  Existing class-level cached
        sessions for the old target are left intact for other IOSDevice objects.
        """
        new_bundle_id = self.bundle_id if bundle_id is None else bundle_id
        new_browser_name = self.browser_name if browser_name is None and bundle_id is None else (browser_name or "")
        if new_bundle_id == self.bundle_id and new_browser_name == self.browser_name:
            return
        with IOSDevice._sessions_lock:
            self.bundle_id = new_bundle_id
            self.browser_name = new_browser_name
            self._clear_instance_session()

    def _rewrite_session_path(self, path: str, new_session_id: str) -> str:
        return re.sub(r"^/session/[^/]+", f"/session/{new_session_id}", path, count=1)

    def _request(
        self,
        method: str,
        path: str,
        payload: dict | None = None,
        timeout: float | None = None,
        *,
        retry_stale_session: bool = True,
    ) -> Any:
        try:
            resp = requests.request(
                method,
                self._url(path),
                json=payload,
                timeout=timeout or self.timeout,
            )
        except requests.RequestException as e:
            raise IOSBackendError(f"Appium request failed: {e}") from e

        try:
            data = resp.json()
        except ValueError:
            data = {}

        value = data.get("value", data)
        if resp.status_code >= 400:
            if retry_stale_session and path.startswith("/session/") and method.upper() != "DELETE":
                if self._invalid_session_message(resp.status_code, value, resp.text):
                    self._evict_session()
                    new_path = self._rewrite_session_path(path, self._ensure_session())
                    return self._request(method, new_path, payload, timeout, retry_stale_session=False)
            msg = value.get("message") if isinstance(value, dict) else resp.text
            raise IOSBackendError(f"Appium {method} {path} failed ({resp.status_code}): {msg}")
        if isinstance(value, dict) and value.get("error"):
            raise IOSBackendError(f"Appium {method} {path} failed: {value.get('message', value['error'])}")
        return value

    def _validate_session_id(self, session_id: str) -> bool:
        try:
            resp = requests.request(
                "GET",
                self._url(f"/session/{session_id}/window/rect"),
                timeout=min(5, self.timeout),
            )
        except requests.RequestException:
            return False
        try:
            data = resp.json()
        except ValueError:
            data = {}
        value = data.get("value", data)
        if self._invalid_session_message(resp.status_code, value, resp.text):
            return False
        return resp.status_code < 400

    def _ensure_session(self) -> str:
        with IOSDevice._sessions_lock:
            if self._session_id:
                return self._session_id
            cached = IOSDevice._sessions.get(self._config)
            if cached:
                if self._validate_session_id(cached):
                    self._session_id = cached
                    return cached
                self._evict_session(cached)

            always_match: dict[str, Any] = {
                "platformName": "iOS",
                "appium:automationName": "XCUITest",
                "appium:udid": self.udid,
                "appium:deviceName": self.device_name,
                "appium:noReset": True,
                "appium:newCommandTimeout": 300,
            }
            if self.platform_version:
                always_match["appium:platformVersion"] = self.platform_version
            if self.wda_url:
                always_match["appium:webDriverAgentUrl"] = self.wda_url
            if self.browser_name:
                always_match["browserName"] = self.browser_name
            elif self.bundle_id:
                always_match["appium:bundleId"] = self.bundle_id
            always_match.update(self.appium_capabilities)

            try:
                resp = requests.request(
                    "POST",
                    self._url("/session"),
                    json={"capabilities": {"alwaysMatch": always_match, "firstMatch": [{}]}},
                    timeout=self.timeout,
                )
            except requests.RequestException as e:
                raise IOSBackendError(f"Could not create Appium iOS session: {e}") from e
            try:
                data = resp.json()
            except ValueError as e:
                raise IOSBackendError(f"Appium did not return JSON for session creation: {resp.text[:200]}") from e
            if resp.status_code >= 400:
                value = data.get("value", {})
                msg = value.get("message") if isinstance(value, dict) else resp.text
                raise IOSBackendError(f"Could not create Appium iOS session ({resp.status_code}): {msg}")

            value = data.get("value", {})
            sid = data.get("sessionId") or value.get("sessionId")
            if not sid:
                raise IOSBackendError(f"Appium session response did not include sessionId: {data}")
            self._session_id = sid
            IOSDevice._sessions[self._config] = sid
            return sid

    def _session_path(self, suffix: str) -> str:
        return f"/session/{self._ensure_session()}{suffix}"

    def _execute_mobile(self, command: str, args: dict | None = None) -> Any:
        return self._request("POST", self._session_path("/execute/sync"), {"script": command, "args": [args or {}]})

    def _execute_script(self, script: str, args: list[Any] | None = None) -> Any:
        return self._request("POST", self._session_path("/execute/sync"), {"script": script, "args": args or []})

    def _set_context(self, name: str) -> None:
        self._request("POST", self._session_path("/context"), {"name": name})

    def get_contexts(self) -> list[str]:
        value = self._request("GET", self._session_path("/contexts"))
        return [str(v) for v in value] if isinstance(value, list) else []

    def get_web_contexts(self) -> list[str]:
        return [ctx for ctx in self.get_contexts() if ctx.upper().startswith("WEBVIEW")]

    def _return_to_native_context(self) -> None:
        try:
            self._set_context("NATIVE_APP")
        except IOSBackendError:
            pass

    def _window_rect(self) -> dict:
        if self._window_rect_cache is None:
            value = self._request("GET", self._session_path("/window/rect"))
            self._window_rect_cache = value if isinstance(value, dict) else {}
        return self._window_rect_cache

    def _coordinate_scale(self) -> tuple[float, float]:
        if self._scale is not None:
            return self._scale
        try:
            raw = self.take_screenshot()
            size = _png_size(raw)
            rect = self._window_rect()
            if size and rect.get("width") and rect.get("height"):
                self._screen_size = size
                self._scale = (size[0] / float(rect["width"]), size[1] / float(rect["height"]))
                return self._scale
        except Exception:
            pass
        self._scale = (1.0, 1.0)
        return self._scale

    def _to_wda_point(self, x: int | float, y: int | float) -> tuple[int, int]:
        sx, sy = self._coordinate_scale()
        return _intish(float(x) / sx), _intish(float(y) / sy)

    @property
    def mjpeg_url(self) -> str:
        if self.mjpeg_screenshot_url:
            return self.mjpeg_screenshot_url
        parsed = urllib.parse.urlparse(self.appium_url)
        scheme = parsed.scheme or "http"
        host = parsed.hostname or "127.0.0.1"
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        return f"{scheme}://{host}:{self.mjpeg_server_port}"

    @property
    def mjpeg_settings(self) -> dict[str, Any]:
        return self.config.mjpeg_settings()

    # -- Device operations -------------------------------------------------

    def take_screenshot(self) -> bytes:
        value = self._request("GET", self._session_path("/screenshot"), timeout=max(self.timeout, 60))
        if not isinstance(value, str):
            raise IOSBackendError("Appium screenshot response was not base64 text")
        return base64.b64decode(value)

    def dump_xml(self) -> str:
        try:
            self._set_context("NATIVE_APP")
        except IOSBackendError:
            pass
        value = self._request("GET", self._session_path("/source"), timeout=max(self.timeout, 60))
        source = value if isinstance(value, str) else str(value or "")
        sx, sy = self._coordinate_scale()
        return normalize_wda_xml(source, sx, sy)

    def dump_ui(self) -> list[dict]:
        return ios_xml_to_elements(self.dump_xml())

    def get_screen_size(self) -> tuple[int, int]:
        if self._screen_size:
            return self._screen_size
        try:
            raw = self.take_screenshot()
            size = _png_size(raw)
            if size:
                self._screen_size = size
                return size
        except Exception:
            pass
        rect = self._window_rect()
        return _intish(rect.get("width")), _intish(rect.get("height"))

    def tap(self, x, y, delay=0.6):
        px, py = self._to_wda_point(x, y)
        payload = {
            "actions": [
                {
                    "type": "pointer",
                    "id": "finger1",
                    "parameters": {"pointerType": "touch"},
                    "actions": [
                        {"type": "pointerMove", "duration": 0, "x": px, "y": py, "origin": "viewport"},
                        {"type": "pointerDown", "button": 0},
                        {"type": "pause", "duration": 50},
                        {"type": "pointerUp", "button": 0},
                    ],
                }
            ]
        }
        self._request("POST", self._session_path("/actions"), payload)
        time.sleep(delay)

    def swipe(self, x1, y1, x2, y2, ms=500, delay=0.5):
        px1, py1 = self._to_wda_point(x1, y1)
        px2, py2 = self._to_wda_point(x2, y2)
        payload = {
            "actions": [
                {
                    "type": "pointer",
                    "id": "finger1",
                    "parameters": {"pointerType": "touch"},
                    "actions": [
                        {"type": "pointerMove", "duration": 0, "x": px1, "y": py1, "origin": "viewport"},
                        {"type": "pointerDown", "button": 0},
                        {"type": "pointerMove", "duration": int(ms), "x": px2, "y": py2, "origin": "viewport"},
                        {"type": "pointerUp", "button": 0},
                    ],
                }
            ]
        }
        self._request("POST", self._session_path("/actions"), payload)
        time.sleep(delay)

    def long_press(self, x, y, duration_ms=1000, delay=0.5):
        px, py = self._to_wda_point(x, y)
        payload = {
            "actions": [
                {
                    "type": "pointer",
                    "id": "finger1",
                    "parameters": {"pointerType": "touch"},
                    "actions": [
                        {"type": "pointerMove", "duration": 0, "x": px, "y": py, "origin": "viewport"},
                        {"type": "pointerDown", "button": 0},
                        {"type": "pause", "duration": int(duration_ms)},
                        {"type": "pointerUp", "button": 0},
                    ],
                }
            ]
        }
        self._request("POST", self._session_path("/actions"), payload)
        time.sleep(delay)

    def type_text(self, text: str, delay=0.3):
        payload = {"text": text, "value": list(text)}
        try:
            self._request("POST", self._session_path("/keys"), payload)
        except IOSBackendError:
            active = self._request("GET", self._session_path("/element/active"))
            elem_id = _element_id(active)
            if not elem_id:
                raise
            self._request("POST", self._session_path(f"/element/{elem_id}/value"), payload)
        time.sleep(delay)

    def _clear_active_element(self) -> bool:
        try:
            active = self._request("GET", self._session_path("/element/active"))
            elem_id = _element_id(active)
            if not elem_id:
                return False
            self._request("POST", self._session_path(f"/element/{elem_id}/clear"), {})
            return True
        except IOSBackendError:
            return False

    def back(self, delay=1.0):
        try:
            self._request("POST", self._session_path("/back"), {})
        except IOSBackendError:
            self.press_key("HOME", delay=delay)
        time.sleep(delay)

    def browser_back(self, delay=1.0):
        try:
            self._request("POST", self._session_path("/back"), {})
        except IOSBackendError:
            self._tap_browser_back_fallback(delay=delay)
            return
        time.sleep(delay)

    def press_enter(self, delay=0.5):
        self.press_key("ENTER", delay=delay)

    def press_key(self, key: str, delay=0.5):
        normalized = key.replace("KEYCODE_", "").upper()
        if normalized in {"HOME", "HOMEPAGE"}:
            self._execute_mobile("mobile: pressButton", {"name": "home"})
        elif normalized in {"ENTER", "RETURN"}:
            self._request("POST", self._session_path("/keys"), {"text": "\n", "value": ["\n"]})
        elif normalized in {"BACK", "ESCAPE"}:
            self.back(delay=0)
        else:
            raise IOSBackendError(f"iOS key '{key}' is not supported through WDA")
        time.sleep(delay)

    def launch_app(self, bundle_id: str | None = None, delay=2.0) -> str:
        target = bundle_id or self.bundle_id
        if not target:
            raise IOSBackendError("No iOS bundle id supplied")
        self._ensure_session()
        try:
            self._execute_mobile("mobile: launchApp", {"bundleId": target})
        except IOSBackendError:
            self._execute_mobile("mobile: activateApp", {"bundleId": target})
        time.sleep(delay)
        return target

    def terminate_app(self, bundle_id: str, delay=0.5) -> str:
        self._execute_mobile("mobile: terminateApp", {"bundleId": bundle_id})
        time.sleep(delay)
        return bundle_id

    def _candidate_apps(self) -> list[dict[str, str]]:
        candidates: list[dict[str, str]] = []
        seen: set[str] = set()

        def add(name: str, bundle_id: str, source: str) -> None:
            if not bundle_id or bundle_id in seen:
                return
            seen.add(bundle_id)
            candidates.append(
                {
                    "name": name or _guess_ios_app_name(bundle_id),
                    "package": bundle_id,
                    "bundle_id": bundle_id,
                    "platform": "ios",
                    "source": source,
                }
            )

        for name, bundle_id in self.config.known_apps:
            add(name, bundle_id, "configured")
        add(_guess_ios_app_name(self.bundle_id), self.bundle_id, "default")
        for name, bundle_id in _skill_ios_app_inventory():
            add(name, bundle_id, "skill")
        for name, bundle_id in _COMMON_IOS_APPS:
            add(name, bundle_id, "common")
        return candidates

    def app_state(self, bundle_id: str) -> int:
        value = self._execute_mobile("mobile: queryAppState", {"bundleId": bundle_id})
        if isinstance(value, dict):
            value = value.get("state", value.get("appState", value.get("value", 0)))
        return _intish(value)

    def is_app_installed(self, bundle_id: str) -> bool:
        return self.app_state(bundle_id) > 0

    def list_apps(self, query: str = "", *, verify: bool = True) -> list[dict[str, Any]]:
        """Return known iOS apps, verifying installation through Appium when possible.

        iOS does not expose Android-style arbitrary package enumeration to a host
        controller.  This method combines user-configured bundle IDs and common
        bundle IDs, then uses Appium's queryAppState extension to filter installed
        apps when WDA is available.
        """
        needle = (query or "").strip().lower()
        apps: list[dict[str, Any]] = []
        verification_error = ""

        for candidate in self._candidate_apps():
            searchable = " ".join([candidate["name"], candidate["package"], candidate["bundle_id"]]).lower()
            if needle and needle not in searchable:
                continue

            app = dict(candidate)
            app["verified"] = False
            app["installed"] = None

            if verify:
                if verification_error:
                    app["verification_error"] = verification_error
                else:
                    try:
                        state = self.app_state(candidate["bundle_id"])
                        if state <= 0:
                            continue
                        app["verified"] = True
                        app["installed"] = True
                        app["app_state"] = state
                        app["app_state_name"] = _IOS_APP_STATE_NAMES.get(state, "unknown")
                    except Exception as e:
                        verification_error = str(e)
                        app["verification_error"] = verification_error
            apps.append(app)

        source_order = {"configured": 0, "default": 1, "skill": 2, "common": 3}
        apps.sort(key=lambda item: (source_order.get(str(item.get("source")), 9), str(item.get("name", "")).lower()))
        return apps

    def _tap_labeled_control(self, targets: tuple[str, ...], *, xml: str | None = None, delay=0.8) -> bool:
        target_patterns = [re.compile(rf"\b{re.escape(target.lower())}\b") for target in targets if target]
        if not target_patterns:
            return False
        xml = xml or self.dump_xml()
        for node in self.nodes(xml):
            labels = [
                self.node_text(node).lower(),
                self.node_content_desc(node).lower(),
                self.node_rid(node).lower(),
            ]
            combined = " ".join(label for label in labels if label)
            if any(pattern.search(combined) for pattern in target_patterns):
                if self.tap_node(node, delay=delay):
                    return True
        return False

    def open_camera(self, mode: str = "photo", timer_s: int = 0, delay=1.5) -> dict[str, Any]:
        normalized_mode = (mode or "photo").lower()
        if normalized_mode not in {"photo", "video", "selfie", "selfie_video"}:
            normalized_mode = "photo"

        self.launch_app("com.apple.camera", delay=delay)

        needs_video = normalized_mode in {"video", "selfie_video"}
        needs_front = normalized_mode in {"selfie", "selfie_video"}
        selected_mode = True
        switched_camera = False
        timer_set = False
        selected_timer = 0

        if needs_video:
            selected_mode = self._tap_labeled_control(("video",), delay=0.6)
        elif normalized_mode in {"photo", "selfie"}:
            self._tap_labeled_control(("photo",), delay=0.4)

        if needs_front:
            switched_camera = self._tap_labeled_control(
                ("switch camera", "camera chooser", "flip camera", "front camera"),
                delay=0.8,
            )

        if timer_s > 0:
            selected_timer = 3 if int(timer_s) <= 3 else 10
            if self._tap_labeled_control(("timer",), delay=0.5):
                timer_set = self._tap_labeled_control(
                    (f"{selected_timer}s", f"{selected_timer} s", f"{selected_timer} seconds", str(selected_timer)),
                    delay=0.5,
                )

        return {
            "platform": "ios",
            "bundle_id": "com.apple.camera",
            "mode": normalized_mode,
            "opened": True,
            "selected_mode": selected_mode,
            "switched_camera": switched_camera if needs_front else None,
            "timer_s": selected_timer,
            "timer_set": timer_set if selected_timer else None,
        }

    def clipboard_get(self) -> str:
        value = self._request(
            "POST",
            self._session_path("/appium/device/get_clipboard"),
            {"contentType": "plaintext"},
        )
        if not value:
            return ""
        if isinstance(value, str):
            try:
                return base64.b64decode(value, validate=True).decode("utf-8")
            except Exception:
                return value
        return str(value)

    def clipboard_set(self, text: str) -> bool:
        content = base64.b64encode(text.encode("utf-8")).decode("ascii")
        self._request(
            "POST",
            self._session_path("/appium/device/set_clipboard"),
            {
                "content": content,
                "contentType": "plaintext",
                "label": "Ghost in the Droid",
            },
        )
        return True

    def paste_text(self, text: str, delay=0.3) -> bool:
        self.clipboard_set(text)
        self.type_text(text, delay=delay)
        return True

    def open_url(self, url: str, delay=2.0) -> dict[str, Any]:
        normalized_url = _normalize_url(url)
        errors: list[dict[str, str]] = []
        try:
            self._request("POST", self._session_path("/url"), {"url": normalized_url})
            status = self.wait_for_url(normalized_url, timeout=delay)
            status["method"] = "webdriver_url"
            if status.get("ok"):
                return status
            errors.append(
                {
                    "method": "webdriver_url",
                    "state": str(status.get("state") or ""),
                    "error": str(status.get("error") or "URL navigation was not verified"),
                }
            )
        except IOSBackendError as exc:
            errors.append({"method": "webdriver_url", "error": str(exc)})

        if self._open_url_in_web_context(normalized_url, delay=delay):
            status = self.wait_for_url(normalized_url, timeout=delay)
            status["method"] = "web_context"
            status["errors"] = errors
            if status.get("ok"):
                return status
            errors.append(
                {
                    "method": "web_context",
                    "state": str(status.get("state") or ""),
                    "error": str(status.get("error") or "URL navigation was not verified"),
                }
            )
        address_method = self._open_url_via_address_bar(normalized_url, delay=delay)
        status = self.wait_for_url(normalized_url, timeout=delay)
        status["method"] = "address_bar"
        if address_method:
            status["address_bar_source"] = address_method
        status["errors"] = errors
        return status

    def _open_url_in_web_context(self, url: str, delay=2.0) -> bool:
        try:
            for ctx in self.get_web_contexts():
                self._set_context(ctx)
                self._request("POST", self._session_path("/url"), {"url": url})
                time.sleep(delay)
                self._return_to_native_context()
                return True
        except IOSBackendError:
            self._return_to_native_context()
        return False

    def _open_url_via_address_bar(self, url: str, delay=2.0) -> str:
        self.launch_app(self.bundle_id, delay=0.8)
        self._dismiss_browser_first_run_prompts()
        xml = self.dump_xml()
        node = self._find_address_bar_node(xml)
        if node:
            if not self.tap_node(node, delay=0.5):
                raise IOSBackendError("Could not tap iOS browser address field")
            method = "address_bar_xml"
        elif self._tap_address_bar_from_ocr(delay=0.5):
            method = "address_bar_ocr"
        else:
            raise IOSBackendError("Could not find an iOS browser address field for URL fallback")
        self._clear_active_element()
        self.type_text(url, delay=0.2)
        self.press_enter(delay=delay)
        return method

    def _tap_address_bar_from_ocr(self, delay=0.5) -> bool:
        try:
            from gitd.services.device_context import ocr_screen

            entries = ocr_screen(self.serial)
        except Exception:
            return False
        for entry in entries:
            if not _looks_like_address_bar_text(str(entry.get("text") or "")):
                continue
            try:
                conf = float(entry.get("conf") or 0)
            except (TypeError, ValueError):
                conf = 0
            if conf and conf < 0.35:
                continue
            x = _intish(entry.get("x")) + max(1, _intish(entry.get("w"))) // 2
            y = _intish(entry.get("y")) + max(1, _intish(entry.get("h"))) // 2
            self.tap(x, y, delay=delay)
            return True
        return False

    def _dismiss_browser_first_run_prompts(self, max_rounds: int = 3) -> int:
        tapped = 0
        for _ in range(max(0, int(max_rounds))):
            xml = self.dump_xml()
            node = self._find_browser_prompt_action_node(xml)
            if not node:
                break
            if not self.tap_node(node, delay=0.6):
                break
            tapped += 1
        return tapped

    def _find_browser_prompt_action_node(self, xml: str) -> str | None:
        for node in self.nodes(xml):
            label = re.sub(
                r"\s+",
                " ",
                f"{self.node_text(node)} {self.node_content_desc(node)} {self.node_rid(node)}",
            ).strip().lower()
            if not label:
                continue
            cls = _node_attr(node, "class").lower()
            if cls not in {"xcuielementtypebutton", "xcuielementtypestatictext"}:
                continue
            if any(action in label for action in _BROWSER_FIRST_RUN_ACTIONS):
                return node
        return None

    def _find_address_bar_node(self, xml: str) -> str | None:
        for node in self.nodes(xml):
            text = (self.node_text(node) or "").lower()
            desc = (self.node_content_desc(node) or "").lower()
            rid = (self.node_rid(node) or "").lower()
            cls = _node_attr(node, "class").lower()
            combined = " ".join([text, desc, rid])
            if cls in {"xcuielementtypetextfield", "xcuielementtypesearchfield"} and _looks_like_address_bar_text(
                combined
            ):
                return node
        return None

    def _tap_browser_back_fallback(self, delay=1.0) -> None:
        xml = self.dump_xml()
        for node in self.nodes(xml):
            label = f"{self.node_text(node)} {self.node_content_desc(node)} {self.node_rid(node)}".lower()
            if "back" in label:
                if self.tap_node(node, delay=delay):
                    return
        raise IOSBackendError("Could not find browser back control")

    def get_current_url(self) -> str:
        current = self._current_url_from_webdriver()
        if current:
            return current
        snapshot = self.web_text_snapshot(max_entries=1)
        if snapshot.get("url"):
            return str(snapshot["url"])
        return self._current_url_from_native_text()

    def _current_url_from_webdriver(self) -> str:
        try:
            value = self._request("GET", self._session_path("/url"))
            if isinstance(value, str):
                return value.strip()
        except IOSBackendError:
            pass
        return ""

    def _current_url_from_native_text(self) -> str:
        for entry in self.visible_text_entries(include_controls=True):
            text = entry["text"]
            if "." in text and " " not in text and len(text) > 3:
                return text
        return ""

    def wait_for_url(self, expected_url: str, timeout=8.0, interval=0.5) -> dict[str, Any]:
        expected = _normalize_url(expected_url)
        deadline = time.time() + max(0.0, float(timeout))
        last_url = ""
        last_error = ""
        saw_page_text = False
        while True:
            try:
                current = self._current_url_from_webdriver()
                if current:
                    last_url = current
                    if _urls_match(current, expected):
                        return {"ok": True, "expected_url": expected, "url": current, "state": "url_matched"}
                snapshot = self.web_text_snapshot(max_entries=12)
                snapshot_url = str(snapshot.get("url") or "").strip() if isinstance(snapshot, dict) else ""
                if snapshot_url:
                    last_url = snapshot_url
                    if _urls_match(snapshot_url, expected):
                        return {"ok": True, "expected_url": expected, "url": snapshot_url, "state": "url_matched"}
                entries = snapshot.get("entries") if isinstance(snapshot, dict) else []
                body_text = str(snapshot.get("bodyText") or "").strip() if isinstance(snapshot, dict) else ""
                saw_page_text = bool(body_text or entries)
                if saw_page_text and not last_url:
                    return {
                        "ok": True,
                        "expected_url": expected,
                        "url": "",
                        "state": "page_text_available",
                        "verified_url": False,
                    }
            except Exception as exc:
                last_error = str(exc)
            if time.time() >= deadline:
                break
            time.sleep(interval)
        return {
            "ok": False,
            "expected_url": expected,
            "url": last_url,
            "state": "timeout",
            "verified_url": False,
            "page_text_available": saw_page_text,
            "error": last_error,
        }

    def web_text_snapshot(self, max_entries: int = 300) -> dict[str, Any]:
        """Return visible DOM text when Appium exposes a WebView context."""
        for ctx in self.get_web_contexts():
            try:
                self._set_context(ctx)
                value = self._execute_script(_WEB_TEXT_JS, [max_entries])
                if isinstance(value, dict):
                    value["context"] = ctx
                    return value
            except IOSBackendError:
                continue
            finally:
                self._return_to_native_context()
        return {}

    def web_text_entries(self, max_entries: int = 300) -> list[dict[str, Any]]:
        snapshot = self.web_text_snapshot(max_entries=max_entries)
        entries = snapshot.get("entries") if isinstance(snapshot, dict) else None
        if not isinstance(entries, list):
            return []
        out: list[dict[str, Any]] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            text = str(entry.get("text") or "").strip()
            if not text:
                continue
            bounds = entry.get("bounds") if isinstance(entry.get("bounds"), dict) else {}
            x1 = _intish(bounds.get("x1"))
            y1 = _intish(bounds.get("y1"))
            x2 = _intish(bounds.get("x2"))
            y2 = _intish(bounds.get("y2"))
            out.append(
                {
                    "text": text,
                    "bounds": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
                    "center": {"x": (x1 + x2) // 2, "y": (y1 + y2) // 2},
                    "class": entry.get("tag", ""),
                    "resource_id": "",
                    "content_desc": "",
                    "provenance": "web_context",
                    "url": str(entry.get("href") or ""),
                    "role": str(entry.get("role") or ""),
                }
            )
        return out

    def native_text_entries(self, *, include_controls: bool = False, max_entries: int = 300) -> list[dict[str, Any]]:
        return visible_text_entries_from_xml(
            self.dump_xml(),
            screen_size=self.get_screen_size(),
            include_controls=include_controls,
            max_entries=max_entries,
        )

    def wait_for_text(self, text: str, timeout=12, interval=1.0) -> str:
        needle = text.lower()
        deadline = time.time() + timeout
        while time.time() <= deadline:
            try:
                visible_text = self.extract_visible_text(max_lines=300)
            except Exception:
                last_xml = self.dump_xml()
                visible_text = "\n".join(e["text"] for e in visible_text_entries_from_xml(last_xml))
                if needle in last_xml.lower():
                    return visible_text
            if needle in visible_text.lower():
                return visible_text
            time.sleep(interval)
        raise TimeoutError(f"Timed out ({timeout}s) waiting for visible text: {text!r}")

    def visible_text_entries(self, *, include_controls: bool = False, max_entries: int = 300) -> list[dict[str, Any]]:
        web_entries = self.web_text_entries(max_entries=max_entries)
        if web_entries:
            if include_controls:
                return web_entries[:max_entries]
            return [e for e in web_entries if not _looks_like_browser_control(e["text"])][:max_entries]
        return self.native_text_entries(include_controls=include_controls, max_entries=max_entries)

    def extract_visible_text(self, *, include_controls: bool = False, max_lines: int = 200) -> str:
        lines = [entry["text"] for entry in self.visible_text_entries(include_controls=include_controls)]
        return "\n".join(lines[:max_lines])

    def extract_articles(self, max_items: int = 5) -> list[dict[str, Any]]:
        web_entries = self.web_text_entries(max_entries=300)
        entries = [entry for entry in web_entries if entry.get("url")]
        if not entries:
            entries = web_entries or self.native_text_entries(include_controls=False, max_entries=300)
        candidates: dict[str, tuple[int, dict[str, Any]]] = {}
        for entry in entries:
            text = entry["text"].strip()
            if not _looks_like_article_title(text):
                continue
            candidate = {
                "title": text,
                "url": entry.get("url", ""),
                "bounds": entry["bounds"],
                "center": entry["center"],
                "class": entry["class"],
                "provenance": entry.get("provenance", "native"),
            }
            score = _article_candidate_score({**entry, **candidate})
            key = _article_candidate_key(candidate)
            existing = candidates.get(key)
            if not existing or score > existing[0]:
                candidates[key] = (score, candidate)

        ranked = sorted(
            candidates.values(),
            key=lambda item: (
                -item[0],
                item[1]["bounds"]["y1"],
                item[1]["bounds"]["x1"],
                item[1]["title"].lower(),
            ),
        )
        return [candidate for _, candidate in ranked[:max_items]]

    def open_notifications(self, delay=1.0) -> bool:
        width, height = self.get_screen_size()
        x = max(1, width // 2)
        self.swipe(x, max(1, int(height * 0.02)), x, int(height * 0.62), ms=650, delay=delay)
        return True

    def close_notifications(self, delay=0.5) -> bool:
        width, height = self.get_screen_size()
        x = max(1, width // 2)
        self.swipe(x, int(height * 0.78), x, int(height * 0.08), ms=450, delay=delay)
        return True

    def get_notifications(self) -> list[dict[str, Any]]:
        self.open_notifications(delay=0.8)
        lines: list[str] = []
        seen: set[str] = set()
        for entry in self.native_text_entries(include_controls=True, max_entries=120):
            text = re.sub(r"\s+", " ", str(entry.get("text") or "")).strip()
            if not text:
                continue
            key = text.lower()
            if key in _IOS_NOTIFICATION_SKIP_TEXT or key in seen:
                continue
            seen.add(key)
            lines.append(text)

        notifications: list[dict[str, Any]] = []
        for idx in range(0, len(lines), 2):
            notifications.append(
                {
                    "package": "",
                    "title": lines[idx],
                    "text": lines[idx + 1] if idx + 1 < len(lines) else "",
                    "time": "",
                    "platform": "ios",
                    "source": "notification_center",
                }
            )
        return notifications

    def clear_notifications(self, delay=0.8) -> bool:
        self.open_notifications(delay=0.5)
        xml = self.dump_xml()
        for node in self.nodes(xml):
            parts = [self.node_text(node), self.node_content_desc(node), self.node_rid(node)]
            labels = {part.strip().lower() for part in parts if part.strip()}
            label = " ".join(parts).strip().lower()
            if labels & {"clear", "clear all"} or "clear all" in label:
                if not self.tap_node(node, delay=delay):
                    continue
                try:
                    updated_xml = self.dump_xml()
                    for confirm_node in self.nodes(updated_xml):
                        confirm_parts = [
                            self.node_text(confirm_node),
                            self.node_content_desc(confirm_node),
                            self.node_rid(confirm_node),
                        ]
                        confirm_labels = {part.strip().lower() for part in confirm_parts if part.strip()}
                        confirm = " ".join(confirm_parts).strip().lower()
                        if confirm_labels & {"clear", "clear all"} or "clear all" in confirm:
                            self.tap_node(confirm_node, delay=delay)
                            break
                except Exception:
                    pass
                return True
        return False

    def get_phone_state(self) -> dict:
        rect = self._window_rect()
        state = {
            "platform": "ios",
            "device": self.serial,
            "udid": self.udid,
            "appiumUrl": self.appium_url,
            "sessionId": self._session_id or IOSDevice._sessions.get(self._config),
            "bundleId": self.bundle_id,
            "screenSize": {"width": self.get_screen_size()[0], "height": self.get_screen_size()[1]},
            "windowRect": rect,
        }
        try:
            active = self._execute_mobile("mobile: activeAppInfo", {})
            if isinstance(active, dict):
                state["activeApp"] = active
                state["packageName"] = active.get("bundleId", "")
                state["currentApp"] = active.get("name", active.get("bundleId", ""))
        except Exception:
            pass
        return state

    def probe(self, *, deep: bool = True) -> IOSDeviceStatus:
        checks: dict[str, Any] = {}
        try:
            resp = requests.request("GET", self._url("/status"), timeout=min(5, self.timeout))
            checks["appium_status_code"] = resp.status_code
            if resp.status_code >= 400:
                return IOSDeviceStatus(
                    self.serial,
                    self.udid,
                    "appium_down",
                    f"Appium status returned {resp.status_code}",
                    self.appium_url,
                    checks=checks,
                )
        except requests.RequestException as e:
            return IOSDeviceStatus(
                self.serial,
                self.udid,
                "appium_down",
                f"Appium is unreachable: {e}",
                self.appium_url,
                checks=checks,
            )

        host_device = _host_device_config_for_udid(self.udid)
        if _requires_host_device_visibility(self.appium_url, self.udid) and not host_device:
            checks["host_device"] = {
                "visible": False,
                "source": "xcrun xctrace list devices",
            }
            return IOSDeviceStatus(
                self.serial,
                self.udid,
                "configured_unreachable",
                "Configured iOS device is not visible to local Xcode device discovery.",
                self.appium_url,
                self._session_id or IOSDevice._sessions.get(self._config, ""),
                checks=checks,
            )
        if host_device:
            checks["host_device"] = host_device

        tunnel = remote_xpc_tunnel_status(
            self.udid,
            platform_version=self.platform_version,
            host=host_device,
        )
        if tunnel.get("required"):
            checks["remote_xpc_tunnel"] = tunnel
        if tunnel.get("required") and not tunnel.get("ok"):
            return IOSDeviceStatus(
                self.serial,
                self.udid,
                "remote_xpc_tunnel_unavailable",
                str(tunnel.get("message") or "RemoteXPC tunnel is unavailable"),
                self.appium_url,
                self._session_id or IOSDevice._sessions.get(self._config, ""),
                checks=checks,
            )

        if not deep:
            return IOSDeviceStatus(
                self.serial,
                self.udid,
                "available",
                "Appium is reachable",
                self.appium_url,
                self._session_id or IOSDevice._sessions.get(self._config, ""),
                checks=checks,
            )

        try:
            state = self.get_phone_state()
            checks["active_app"] = state.get("activeApp") or {}
            screenshot = self.take_screenshot()
            checks["screenshot_bytes"] = len(screenshot)
            xml = self.dump_xml()
            checks["source_bytes"] = len(xml)
            return IOSDeviceStatus(
                self.serial,
                self.udid,
                "available",
                "iOS Appium/WDA session is usable",
                self.appium_url,
                self._session_id or IOSDevice._sessions.get(self._config, ""),
                active_app=state.get("activeApp"),
                screen_size=state.get("screenSize"),
                checks=checks,
            )
        except Exception as e:
            state, message = classify_ios_error(e)
            checks["error"] = str(e)
            return IOSDeviceStatus(
                self.serial,
                self.udid,
                state,
                message,
                self.appium_url,
                self._session_id or IOSDevice._sessions.get(self._config, ""),
                checks=checks,
            )

    def get_app_version(self, package: str) -> str:
        return "unknown"

    def dismiss_popups(self, xml: str | None = None, popups: list[dict] | None = None) -> bool:
        """Dismiss known iOS prompts from normalized WDA XML.

        Skill-specific popup detectors use the same {"detect", "button"} shape
        as Android.  The generic fallback only taps compact, visible controls
        with dismissal-like labels to avoid tapping article/content text.
        """
        if xml is None:
            xml = self.dump_xml()
        if not xml:
            return False

        popup_list = popups if popups is not None else _KNOWN_IOS_POPUPS
        for popup in popup_list:
            detect = str(popup.get("detect", "")).strip()
            if detect and detect not in xml:
                continue
            if popup.get("method") == "back":
                self.back(delay=1.0)
                return True
            button = str(popup.get("button", "")).strip()
            if not button:
                continue
            matches = self.find_nodes(xml, text=button)
            matches.sort(key=lambda node: (self.node_bounds(node) or (0, 0, 0, 0))[1])
            for node in matches:
                if self.tap_node(node, delay=1.0):
                    return True

        for node in self.nodes(xml):
            label = f"{self.node_text(node)} {self.node_content_desc(node)}".strip().lower()
            if not label:
                continue
            bounds = self.node_bounds(node)
            if not bounds:
                continue
            width = bounds[2] - bounds[0]
            height = bounds[3] - bounds[1]
            if width > 500 or height > 120:
                continue
            cls = _node_attr(node, "class")
            clickable = 'clickable="true"' in node
            if not clickable and cls not in {"XCUIElementTypeButton", "XCUIElementTypeStaticText"}:
                continue
            words = set(label.split())
            if label in _DISMISS_EXACT or label in _DISMISS_WORDS or words & _DISMISS_WORDS:
                return self.tap_node(node, delay=1.0)
        return False

    def close(self):
        if not self._session_id:
            return
        try:
            self._request("DELETE", f"/session/{self._session_id}", {})
        finally:
            self._evict_session()

    def reset_session(self):
        sid = self._session_id or IOSDevice._sessions.get(self._config)
        if sid:
            try:
                self._request("DELETE", f"/session/{sid}", {}, retry_stale_session=False)
            except Exception:
                pass
        self._evict_session(sid)

    def start_appium_server(self) -> dict[str, Any]:
        parsed = urllib.parse.urlparse(self.appium_url)
        scheme = parsed.scheme or "http"
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or (443 if scheme == "https" else 4723)
        if scheme != "http" or host not in {"127.0.0.1", "localhost", "::1"}:
            return {
                "ok": False,
                "platform": "ios",
                "issue": "start_appium",
                "manual_action_required": True,
                "message": "Configured Appium URL is not a local HTTP server Ghost can start safely.",
                "appium_url": self.appium_url,
                "recovery": {
                    "code": "start_appium",
                    "state": "appium_down",
                    "summary": "Start Appium at the configured URL.",
                    "steps": [
                        f"Start Appium so {self.appium_url} responds to /status.",
                        "Verify IOS_APPIUM_URL points to the running server.",
                        f"Re-run /api/phone/health/{self.serial}.",
                    ],
                },
            }
        try:
            resp = requests.request("GET", self._url("/status"), timeout=1)
            if resp.status_code < 400:
                return {
                    "ok": True,
                    "platform": "ios",
                    "issue": "start_appium",
                    "message": "Appium is already running.",
                    "appium_url": self.appium_url,
                    "status_code": resp.status_code,
                }
        except requests.RequestException:
            pass

        try:
            command = shlex.split(os.getenv("IOS_APPIUM_COMMAND", "appium"))
        except ValueError as e:
            return {
                "ok": False,
                "platform": "ios",
                "issue": "start_appium",
                "manual_action_required": True,
                "message": f"IOS_APPIUM_COMMAND is not parseable: {e}",
                "appium_url": self.appium_url,
            }
        if not command:
            return {
                "ok": False,
                "platform": "ios",
                "issue": "start_appium",
                "manual_action_required": True,
                "message": "IOS_APPIUM_COMMAND is empty.",
                "appium_url": self.appium_url,
            }
        bind_host = "127.0.0.1" if host == "localhost" else host
        command = [*command, "--address", bind_host, "--port", str(port), "--log-level", "info"]
        log_path = os.getenv("IOS_APPIUM_LOG", f"/tmp/gitd-appium-{port}.log")
        try:
            log_fh = open(log_path, "a", encoding="utf-8")
            try:
                proc = subprocess.Popen(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=log_fh,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            finally:
                log_fh.close()
        except OSError as e:
            return {
                "ok": False,
                "platform": "ios",
                "issue": "start_appium",
                "manual_action_required": True,
                "message": f"Could not start Appium: {e}",
                "command": command,
                "log_path": log_path,
                "appium_url": self.appium_url,
            }

        status_code = 0
        reachable = False
        last_error = ""
        for _ in range(20):
            try:
                resp = requests.request("GET", self._url("/status"), timeout=1)
                status_code = resp.status_code
                if resp.status_code < 400:
                    reachable = True
                    break
            except requests.RequestException as e:
                last_error = str(e)
            time.sleep(0.25)
        return {
            "ok": reachable,
            "platform": "ios",
            "issue": "start_appium",
            "message": "Appium started." if reachable else "Appium start command was launched but /status is not reachable yet.",
            "pid": proc.pid,
            "command": command,
            "log_path": log_path,
            "appium_url": self.appium_url,
            "status_code": status_code,
            "error": "" if reachable else last_error,
        }

    def restart_remote_xpc_tunnel(self) -> dict[str, Any]:
        tunnel_before = remote_xpc_tunnel_status(
            self.udid,
            platform_version=self.platform_version,
            host=_host_device_config_for_udid(self.udid),
        )
        processes = _remote_xpc_tunnel_processes(self.udid)
        current_uid = os.getuid()
        foreign = [proc for proc in processes if proc["uid"] != current_uid]
        if foreign:
            recovery = remote_xpc_manual_recovery(self.udid, tunnel_before)
            return {
                "ok": False,
                "platform": "ios",
                "issue": "restart_remote_xpc_tunnel",
                "manual_action_required": True,
                "message": "Existing XCUITest tunnel process is owned by another user and cannot be restarted here.",
                "processes": processes,
                "tunnel": tunnel_before,
                "recovery": recovery,
            }

        killed: list[dict[str, Any]] = []
        kill_errors: list[dict[str, Any]] = []
        for proc in processes:
            try:
                os.kill(proc["pid"], signal.SIGTERM)
                killed.append(proc)
            except OSError as e:
                kill_errors.append({**proc, "error": str(e)})
        if kill_errors:
            return {
                "ok": False,
                "platform": "ios",
                "issue": "restart_remote_xpc_tunnel",
                "manual_action_required": True,
                "message": "Could not stop existing XCUITest tunnel process.",
                "processes": processes,
                "killed": killed,
                "errors": kill_errors,
                "tunnel": tunnel_before,
                "recovery": remote_xpc_manual_recovery(self.udid, tunnel_before),
            }

        registry_port = _remote_xpc_registry_ports()[0]
        command = ["appium", "driver", "run", "xcuitest", "tunnel-creation", "--udid", self.udid]
        if registry_port != _REMOTE_XPC_REGISTRY_PORTS[0]:
            command.extend(["--tunnel-registry-port", str(registry_port)])
        log_path = os.getenv("IOS_REMOTE_XPC_TUNNEL_LOG", f"/tmp/gitd-xcuitest-tunnel-{self.udid}.log")
        try:
            log_fh = open(log_path, "a", encoding="utf-8")
            try:
                proc = subprocess.Popen(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=log_fh,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            finally:
                log_fh.close()
        except OSError as e:
            return {
                "ok": False,
                "platform": "ios",
                "issue": "restart_remote_xpc_tunnel",
                "manual_action_required": True,
                "message": f"Could not start XCUITest tunnel process: {e}",
                "command": command,
                "log_path": log_path,
                "tunnel": tunnel_before,
            }

        wait_timeout = _remote_xpc_tunnel_start_timeout()
        deadline = time.time() + wait_timeout
        tunnel_after: dict[str, Any] = {}
        attempts = 0
        while True:
            attempts += 1
            tunnel_after = remote_xpc_tunnel_status(
                self.udid,
                platform_version=self.platform_version,
                host=_host_device_config_for_udid(self.udid),
            )
            if tunnel_after.get("ok"):
                return {
                    "ok": True,
                    "platform": "ios",
                    "issue": "restart_remote_xpc_tunnel",
                    "message": "XCUITest RemoteXPC tunnel is available.",
                    "pid": proc.pid,
                    "command": command,
                    "log_path": log_path,
                    "killed": killed,
                    "tunnel_before": tunnel_before,
                    "tunnel_after": tunnel_after,
                    "attempts": attempts,
                }
            if time.time() >= deadline:
                break
            time.sleep(0.5)

        return {
            "ok": False,
            "platform": "ios",
            "issue": "restart_remote_xpc_tunnel",
            "message": "XCUITest RemoteXPC tunnel restart started but did not become available before timeout.",
            "manual_action_required": True,
            "pid": proc.pid,
            "command": command,
            "log_path": log_path,
            "killed": killed,
            "tunnel_before": tunnel_before,
            "tunnel_after": tunnel_after,
            "attempts": attempts,
            "recovery": remote_xpc_manual_recovery(self.udid, tunnel_after or tunnel_before),
        }

    # -- Android-compatible XML parsing helpers ---------------------------

    def bounds_center(self, bounds_str: str) -> tuple[int, int]:
        nums = list(map(int, re.findall(r"\d+", bounds_str)))
        return (nums[0] + nums[2]) // 2, (nums[1] + nums[3]) // 2

    def find_bounds(self, xml: str, *, text=None, content_desc=None, resource_id=None, class_name=None) -> str | None:
        if text:
            key, val = "text", text
        elif content_desc:
            key, val = "content-desc", content_desc
        elif resource_id:
            key, val = "resource-id", resource_id
        elif class_name:
            key, val = "class", class_name
        else:
            return None
        m = re.search(rf'<node[^>]*{key}="{re.escape(val)}"[^>]*>', xml)
        if m:
            bm = re.search(r'bounds="([^"]+)"', m.group())
            return bm.group(1) if bm else None
        return None

    def tap_text(self, xml: str, text: str, fallback_xy=None, delay=0.8) -> bool:
        b = self.find_bounds(xml, text=text)
        if b:
            self.tap(*self.bounds_center(b), delay)
            return True
        if fallback_xy:
            self.tap(*fallback_xy, delay)
            return True
        raise RuntimeError(f"Could not find '{text}' on screen")

    def wait_for(self, text: str, timeout=12, interval=1.0) -> str:
        for _ in range(int(timeout / interval) + 1):
            xml = self.dump_xml()
            if text in xml:
                return xml
            time.sleep(interval)
        raise TimeoutError(f"Timed out ({timeout}s) waiting for: {text!r}")

    def nodes(self, xml: str) -> list[str]:
        return re.findall(r"<node[^>]+/?>", xml)

    def node_text(self, node: str) -> str:
        m = re.search(r'\btext="([^"]*)"', node)
        return html.unescape(m.group(1).strip()) if m else ""

    def node_content_desc(self, node: str) -> str:
        m = re.search(r'content-desc="([^"]*)"', node)
        return html.unescape(m.group(1).strip()) if m else ""

    def node_rid(self, node: str) -> str:
        m = re.search(r'resource-id="([^"]*)"', node)
        return html.unescape(m.group(1)) if m else ""

    @staticmethod
    def node_bounds_static(node: str) -> tuple[int, int, int, int] | None:
        m = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', node)
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))) if m else None

    def node_bounds(self, node: str) -> tuple[int, int, int, int] | None:
        return self.node_bounds_static(node)

    def node_center(self, b: tuple) -> tuple[int, int]:
        return (b[0] + b[2]) // 2, (b[1] + b[3]) // 2

    def find_nodes(self, xml: str, rid: str | None = None, text: str | None = None) -> list[str]:
        out = []
        for node in self.nodes(xml):
            if rid and self.node_rid(node) != rid:
                continue
            if text and text.lower() not in (self.node_text(node) + self.node_content_desc(node)).lower():
                continue
            out.append(node)
        return out

    def tap_node(self, node: str, delay=0.8) -> bool:
        b = self.node_bounds(node)
        if b:
            self.tap(*self.node_center(b), delay)
            return True
        return False


def _element_id(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    for key in _ELEMENT_ID_KEYS:
        if value.get(key):
            return str(value[key])
    return ""


def _node_attr(node: str, attr: str) -> str:
    m = re.search(rf'\b{re.escape(attr)}="([^"]*)"', node)
    return html.unescape(m.group(1).strip()) if m else ""


def _normalize_url(url: str) -> str:
    cleaned = url.strip()
    if cleaned and "://" not in cleaned:
        cleaned = "https://" + cleaned
    return cleaned


def _host_without_www(hostname: str) -> str:
    host = hostname.lower().strip(".")
    return host[4:] if host.startswith("www.") else host


def _urls_match(current_url: str, expected_url: str) -> bool:
    current = _normalize_url(current_url)
    expected = _normalize_url(expected_url)
    try:
        current_parts = urllib.parse.urlparse(current)
        expected_parts = urllib.parse.urlparse(expected)
    except Exception:
        return False
    current_host = _host_without_www(current_parts.hostname or "")
    expected_host = _host_without_www(expected_parts.hostname or "")
    if not current_host or not expected_host or current_host != expected_host:
        return False

    current_path = (current_parts.path or "/").rstrip("/") or "/"
    expected_path = (expected_parts.path or "/").rstrip("/") or "/"
    if current_path != expected_path:
        return False

    expected_query = urllib.parse.parse_qs(expected_parts.query, keep_blank_values=True)
    if expected_query:
        current_query = urllib.parse.parse_qs(current_parts.query, keep_blank_values=True)
        for key, values in expected_query.items():
            if key not in current_query:
                return False
            for value in values:
                if value not in current_query[key]:
                    return False
    return True


def _looks_like_browser_control(text: str) -> bool:
    cleaned = text.strip().lower()
    if not cleaned:
        return True
    if cleaned in _BROWSER_CONTROL_TEXT:
        return True
    if cleaned.startswith("tab ") or cleaned.endswith(" tabs"):
        return True
    return False


def _looks_like_article_title(text: str) -> bool:
    cleaned = text.strip()
    if len(cleaned) < 18:
        return False
    lower = cleaned.lower()
    if _looks_like_browser_control(cleaned):
        return False
    if lower.startswith(("http://", "https://", "www.")):
        return False
    if lower in {"home", "menu", "sections", "search", "sponsor message"}:
        return False
    words = re.findall(r"[A-Za-z0-9]+", cleaned)
    return len(words) >= 4


def _article_url_score(url: str) -> int:
    if not url:
        return 0
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        return -10
    if parsed.scheme and parsed.scheme not in {"http", "https"}:
        return -20

    path = (parsed.path or "/").lower()
    query = (parsed.query or "").lower()
    score = 20
    if path in {"", "/"}:
        score -= 18
    if any(hint in path for hint in _ARTICLE_URL_HINTS):
        score += 16
    if re.search(r"/(?:20\d{2}|\d{4,}|[a-z]+-\d+)", path):
        score += 12
    if query:
        score -= 4
    if any(term.replace(" ", "-") in path for term in _LOW_VALUE_ARTICLE_TERMS):
        score -= 30
    return score


def _article_candidate_score(entry: dict[str, Any]) -> int:
    text = re.sub(r"\s+", " ", str(entry.get("text") or "")).strip()
    lower = text.lower()
    bounds = entry.get("bounds") if isinstance(entry.get("bounds"), dict) else {}
    y1 = _intish(bounds.get("y1"))
    tag = str(entry.get("class") or "").lower()
    role = str(entry.get("role") or "").lower()
    url = str(entry.get("url") or "")

    words = re.findall(r"[A-Za-z0-9]+", text)
    score = min(len(words), 12)
    score += _article_url_score(url)
    if entry.get("provenance") == "web_context":
        score += 8
    if tag in {"h1", "h2", "h3"} or role == "heading":
        score += 12
    if tag == "a" and url:
        score += 8
    if 35 <= y1 <= 1200:
        score += max(0, 12 - y1 // 160)
    if len(text) > 180:
        score -= 10
    if any(term in lower for term in _LOW_VALUE_ARTICLE_TERMS):
        score -= 35
    return score


def _article_candidate_key(entry: dict[str, Any]) -> str:
    url = str(entry.get("url") or "").strip()
    if url:
        parsed = urllib.parse.urlparse(url)
        return f"url:{parsed.netloc.lower()}{parsed.path.rstrip('/').lower()}"
    text = re.sub(r"\W+", "", str(entry.get("title") or entry.get("text") or "").lower())
    return f"text:{text}"


def visible_text_entries_from_xml(
    xml: str,
    *,
    screen_size: tuple[int, int] | None = None,
    include_controls: bool = False,
    max_entries: int = 300,
) -> list[dict[str, Any]]:
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return []
    max_w, max_h = screen_size or (0, 0)
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for node in root.iter("node"):
        visible = (node.get("visible") or "").lower()
        if visible == "false":
            continue
        text = (node.get("text") or node.get("content-desc") or "").strip()
        if not text:
            continue
        if not include_controls and _looks_like_browser_control(text):
            continue
        bounds = IOSDevice.node_bounds_static(ET.tostring(node, encoding="unicode"))
        if not bounds:
            continue
        x1, y1, x2, y2 = bounds
        if x2 <= x1 or y2 <= y1:
            continue
        if max_w and (x2 < 0 or x1 > max_w):
            continue
        if max_h and (y2 < 0 or y1 > max_h):
            continue
        key = f"{text}\0{x1}:{y1}:{x2}:{y2}"
        if key in seen:
            continue
        seen.add(key)
        entries.append(
            {
                "text": text,
                "bounds": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
                "center": {"x": (x1 + x2) // 2, "y": (y1 + y2) // 2},
                "class": node.get("class", ""),
                "resource_id": node.get("resource-id", ""),
                "content_desc": node.get("content-desc", ""),
                "provenance": "native",
            }
        )
        if len(entries) >= max_entries:
            break
    entries.sort(key=lambda e: (e["bounds"]["y1"], e["bounds"]["x1"], e["text"]))
    return entries


def classify_ios_error(exc: Exception) -> tuple[str, str]:
    message = str(exc)
    lower = message.lower()
    if (
        "unlock" in lower
        or "locked" in lower
        or "passcode" in lower
        or "not trusted" in lower
        or "trust this computer" in lower
        or "developer mode" in lower
        or "ui automation" in lower
    ):
        return "locked", f"Device is locked, not trusted, or blocked by iOS automation permissions: {message}"
    if (
        "remote xpc" in lower
        or "remotexpc" in lower
        or "could not find the expected device" in lower
    ):
        return "remote_xpc_tunnel_unavailable", f"RemoteXPC tunnel or usbmux device listing is unavailable: {message}"
    if "connection refused" in lower or "failed to establish" in lower or "timed out" in lower:
        return "appium_down", f"Appium is unreachable: {message}"
    if "code sign" in lower or "signing" in lower or "provision" in lower or "xcodebuild" in lower:
        return "wda_signing_failed", f"WebDriverAgent signing/provisioning failed: {message}"
    if "invalid session" in lower or "session not found" in lower or "no such driver" in lower:
        return "session_error", f"Appium session is invalid: {message}"
    if "could not create appium ios session" in lower:
        return "configured_unreachable", message
    return "session_error", message


def probe_ios_device(device: str, *, deep: bool = True) -> IOSDeviceStatus:
    return IOSDevice(device).probe(deep=deep)
