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
import os
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
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


def _env_capabilities() -> dict[str, Any]:
    capabilities: dict[str, Any] = {}

    string_caps = {
        "IOS_XCODE_ORG_ID": "appium:xcodeOrgId",
        "IOS_XCODE_SIGNING_ID": "appium:xcodeSigningId",
        "IOS_UPDATED_WDA_BUNDLE_ID": "appium:updatedWDABundleId",
        "IOS_DERIVED_DATA_PATH": "appium:derivedDataPath",
    }
    bool_caps = {
        "IOS_ALLOW_PROVISIONING_DEVICE_REGISTRATION": "appium:allowProvisioningDeviceRegistration",
        "IOS_SHOW_XCODE_LOG": "appium:showXcodeLog",
        "IOS_USE_PREBUILT_WDA": "appium:usePrebuiltWDA",
    }
    int_caps = {
        "IOS_WDA_LAUNCH_TIMEOUT": "appium:wdaLaunchTimeout",
        "IOS_WDA_CONNECTION_TIMEOUT": "appium:wdaConnectionTimeout",
        "IOS_WDA_STARTUP_RETRIES": "appium:wdaStartupRetries",
        "IOS_WDA_STARTUP_RETRY_INTERVAL": "appium:wdaStartupRetryInterval",
    }

    for env_name, cap_name in string_caps.items():
        value = os.getenv(env_name)
        if value:
            capabilities[cap_name] = value
    for env_name, cap_name in bool_caps.items():
        value = os.getenv(env_name)
        if value is not None:
            capabilities[cap_name] = _as_bool(value)
    for env_name, cap_name in int_caps.items():
        value = os.getenv(env_name)
        if value:
            capabilities[cap_name] = _intish(value)

    return capabilities


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
        self.appium_url = (appium_url or os.getenv("IOS_APPIUM_URL") or "http://127.0.0.1:4723").rstrip("/")
        self.bundle_id = bundle_id if bundle_id is not None else os.getenv("IOS_BUNDLE_ID", "com.apple.mobilesafari")
        self.browser_name = browser_name if browser_name is not None else os.getenv("IOS_BROWSER_NAME", "")
        self.device_name = os.getenv("IOS_DEVICE_NAME", "iPhone")
        self.platform_version = os.getenv("IOS_PLATFORM_VERSION", "")
        self.wda_url = os.getenv("IOS_WDA_URL") or os.getenv("IOS_WEBDRIVERAGENT_URL", "")
        self.timeout = float(timeout or os.getenv("IOS_APPIUM_TIMEOUT", "120"))
        self.appium_capabilities = _env_capabilities()
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

    def _request(self, method: str, path: str, payload: dict | None = None, timeout: float | None = None) -> Any:
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
            msg = value.get("message") if isinstance(value, dict) else resp.text
            raise IOSBackendError(f"Appium {method} {path} failed ({resp.status_code}): {msg}")
        if isinstance(value, dict) and value.get("error"):
            raise IOSBackendError(f"Appium {method} {path} failed: {value.get('message', value['error'])}")
        return value

    def _ensure_session(self) -> str:
        if self._session_id:
            return self._session_id
        cached = IOSDevice._sessions.get(self._config)
        if cached:
            self._session_id = cached
            return cached

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

    def _set_context(self, name: str) -> None:
        self._request("POST", self._session_path("/context"), {"name": name})

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
        self._request("POST", self._session_path("/url"), {"url": url})
        time.sleep(delay)

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
            IOSDevice._sessions.pop(self._config, None)
            self._session_id = None
            self._scale = None
            self._screen_size = None
            self._window_rect_cache = None

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
