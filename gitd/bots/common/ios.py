#!/usr/bin/env python3
"""iOS automation primitives backed by Appium XCUITest/WebDriverAgent.

The public methods mirror the small Android ``Device`` surface used by the
agent layer: screenshot, XML dump, tap, swipe, type, app launch, and simple XML
helpers.  The implementation talks directly to Appium's W3C WebDriver HTTP API
so the first iOS milestone does not need the Python Appium client package.
"""
from __future__ import annotations

import base64
import json
import html
import os
import re
import threading
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
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

_ELEMENT_ID_KEYS = (
    "element-6066-11e4-a52e-4f735466cecf",
    "ELEMENT",
)


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
        return caps


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
}

_INT_CONFIG_FIELDS = {
    "mjpeg_server_port",
    "wda_launch_timeout",
    "wda_connection_timeout",
    "wda_startup_retries",
    "wda_startup_retry_interval",
}
_FLOAT_CONFIG_FIELDS = {"timeout"}
_BOOL_CONFIG_FIELDS = {
    "allow_provisioning_device_registration",
    "show_xcode_log",
    "use_prebuilt_wda",
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
        return f"http://127.0.0.1:{self.mjpeg_server_port}"

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

    def open_url(self, url: str, delay=2.0):
        normalized_url = _normalize_url(url)
        try:
            self._request("POST", self._session_path("/url"), {"url": normalized_url})
            time.sleep(delay)
            return
        except IOSBackendError:
            pass

        if self._open_url_in_web_context(normalized_url, delay=delay):
            return
        self._open_url_via_address_bar(normalized_url, delay=delay)

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

    def _open_url_via_address_bar(self, url: str, delay=2.0) -> None:
        self.launch_app(self.bundle_id, delay=0.8)
        xml = self.dump_xml()
        node = self._find_address_bar_node(xml)
        if not node:
            raise IOSBackendError("Could not find an iOS browser address field for URL fallback")
        if not self.tap_node(node, delay=0.5):
            raise IOSBackendError("Could not tap iOS browser address field")
        try:
            self.press_key("COMMAND+A", delay=0.1)
        except IOSBackendError:
            pass
        self.type_text(url, delay=0.2)
        self.press_enter(delay=delay)

    def _find_address_bar_node(self, xml: str) -> str | None:
        for node in self.nodes(xml):
            text = (self.node_text(node) or "").lower()
            desc = (self.node_content_desc(node) or "").lower()
            rid = (self.node_rid(node) or "").lower()
            cls = _node_attr(node, "class").lower()
            combined = " ".join([text, desc, rid])
            if cls in {"xcuielementtypetextfield", "xcuielementtypesearchfield"} and (
                "address" in combined
                or "search" in combined
                or "url" in combined
                or "web address" in combined
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
        try:
            value = self._request("GET", self._session_path("/url"))
            if isinstance(value, str):
                return value
        except IOSBackendError:
            pass
        snapshot = self.web_text_snapshot(max_entries=1)
        if snapshot.get("url"):
            return str(snapshot["url"])
        for entry in self.visible_text_entries(include_controls=True):
            text = entry["text"]
            if "." in text and " " not in text and len(text) > 3:
                return text
        return ""

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
        last_xml = ""
        while time.time() <= deadline:
            last_xml = self.dump_xml()
            visible_text = "\n".join(e["text"] for e in visible_text_entries_from_xml(last_xml))
            if needle in visible_text.lower() or needle in last_xml.lower():
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
            entries = self.native_text_entries(include_controls=False, max_entries=300)
        titles: list[dict[str, Any]] = []
        seen: set[str] = set()
        for entry in entries:
            text = entry["text"].strip()
            if not _looks_like_article_title(text):
                continue
            key = re.sub(r"\W+", "", text.lower())
            if key in seen:
                continue
            seen.add(key)
            titles.append(
                {
                    "title": text,
                    "url": entry.get("url", ""),
                    "bounds": entry["bounds"],
                    "center": entry["center"],
                    "class": entry["class"],
                    "provenance": entry.get("provenance", "native"),
                }
            )
            if len(titles) >= max_items:
                break
        return titles

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

    # -- Android-compatible XML parsing helpers ---------------------------

    def bounds_center(self, bounds_str: str) -> tuple[int, int]:
        nums = list(map(int, re.findall(r"\d+", bounds_str)))
        return (nums[0] + nums[2]) // 2, (nums[1] + nums[3]) // 2

    def find_bounds(self, xml: str, *, text=None, content_desc=None, resource_id=None) -> str | None:
        if text:
            key, val = "text", text
        elif content_desc:
            key, val = "content-desc", content_desc
        elif resource_id:
            key, val = "resource-id", resource_id
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
    if "connection refused" in lower or "failed to establish" in lower or "timed out" in lower:
        return "appium_down", f"Appium is unreachable: {message}"
    if "code sign" in lower or "signing" in lower or "provision" in lower or "xcodebuild" in lower:
        return "wda_signing_failed", f"WebDriverAgent signing/provisioning failed: {message}"
    if "locked" in lower or "passcode" in lower or "not trusted" in lower or "trust" in lower:
        return "locked", f"Device is locked or not trusted: {message}"
    if "invalid session" in lower or "session not found" in lower or "no such driver" in lower:
        return "session_error", f"Appium session is invalid: {message}"
    if "could not create appium ios session" in lower:
        return "configured_unreachable", message
    return "session_error", message


def probe_ios_device(device: str, *, deep: bool = True) -> IOSDeviceStatus:
    return IOSDevice(device).probe(deep=deep)
