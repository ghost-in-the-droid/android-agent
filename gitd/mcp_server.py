#!/usr/bin/env python3
"""MCP Server - expose mobile automation as tools for any LLM agent.

Usage:
  stdio:  python3 -m gitd.mcp_server
  HTTP:   python3 -m gitd.mcp_server  (port 8002)
"""

import importlib
import json
import re
import subprocess
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gitd.bots.common.adb import Device
from gitd.bots.common.device import (
    get_device,
    is_ios_ref,
    list_configured_ios_devices,
    list_connected_device_refs,
)
from gitd.services.agent_tools import SAFE_DEVICE_TOOLS
from gitd.services.tool_platforms import platform_error_text, supports_platform
from gitd.skills.platforms import (
    skill_platform_error_text,
    skill_platform_summary,
    skill_supports_device,
)

mcp = FastMCP(
    "android-agent",
    stateless_http=True,
    json_response=True,
    host="127.0.0.1",
    port=8002,
    streamable_http_path="/mcp",
)


def _ios_unsupported(tool_name: str) -> str:
    return platform_error_text(tool_name, "ios")


def _device_platform(device: str) -> str:
    return "ios" if is_ios_ref(device) else "android"


def _platform_unsupported(tool_name: str, device: str) -> str:
    return platform_error_text(tool_name, _device_platform(device))


def _load_skill_metadata(skill: str) -> dict:
    import yaml

    meta_path = Path(__file__).parent / "skills" / skill / "skill.yaml"
    if not meta_path.exists():
        return {}
    return yaml.safe_load(meta_path.read_text()) or {}


def _ios_device_details_by_serial() -> dict[str, dict]:
    try:
        return {item["serial"]: item for item in list_configured_ios_devices(deep_probe=False)}
    except Exception:
        return {}


def _format_ios_device(serial: str, details: dict | None) -> str:
    if not details:
        return f"{serial} (iOS via Appium/WDA)"

    label = details.get("model") or details.get("device_name") or "iOS device"
    parts = [label, "iOS"]

    status = details.get("status")
    if status:
        parts.append(f"status={status}")

    source = details.get("source")
    host_state = details.get("host_state")
    if source and host_state:
        parts.append(f"host={source}/{host_state}")
    elif source:
        parts.append(f"source={source}")

    appium_url = details.get("appium_url")
    if appium_url:
        parts.append(f"appium={appium_url}")

    message = details.get("status_message")
    if message:
        parts.append(f"hint={message}")

    return f"{serial} ({'; '.join(parts)})"


# ── Tier 1: Device Control ────────────────────────────────────────────────


@mcp.tool()
def list_devices() -> str:
    """List connected Android ADB devices and configured iOS Appium devices.
    Call this first to get the device serial you need for other tools."""
    devices = list_connected_device_refs()
    if not devices:
        return (
            "No devices connected. Check ADB authorization, connect an iPhone visible to xcrun/xctrace, "
            "or set IOS_DEVICE_UDID for iOS."
        )
    ios_details = _ios_device_details_by_serial()
    result = []
    for serial in devices:
        if is_ios_ref(serial):
            result.append(_format_ios_device(serial, ios_details.get(serial)))
            continue
        else:
            try:
                model = Device(serial).adb("shell", "getprop", "ro.product.model", timeout=3).strip()
            except Exception:
                model = "unknown"
        result.append(f"{serial} ({model})")
    return "\n".join(result)


@mcp.tool()
def screenshot(device: str) -> str:
    """Take a screenshot of the device screen. Returns a base64-encoded JPEG.
    Use this to SEE what's on screen before deciding what to tap.

    Routes through the shared compressed screenshot path (half-resolution JPEG,
    cross-platform) instead of a raw full-res PNG: a raw PNG base64 string
    overflows the MCP tool-result token cap on content-heavy screens, so the
    client falls back to text/OCR and never sees the pixels. The downscale cuts
    the payload ~4-8x so most screens stay under the cap. (The lasting fix is
    returning an MCP image-content block; tracked as feature #8.)"""
    from gitd.services.device_context import screenshot as _screenshot
    return _screenshot(device)["image"]


@mcp.tool()
def get_elements(device: str, interactive_only: bool = True) -> str:
    """Get all UI elements on the current screen as a JSON array.
    Each element has: idx, text, content_desc, resource_id, class, bounds, center, clickable, scrollable.
    Use element idx with tap_element(). Call this to understand the screen layout before acting."""
    from gitd.services.device_context import get_interactive_elements
    return json.dumps(get_interactive_elements(device, interactive_only=interactive_only), indent=2)


@mcp.tool()
def tap(device: str, x: int, y: int) -> str:
    """Tap at exact pixel coordinates (x, y) on the device screen."""
    get_device(device).tap(x, y)
    return f"Tapped ({x}, {y})"


@mcp.tool()
def tap_element(device: str, idx: int) -> str:
    """Tap a UI element by its index from get_elements().
    Call get_elements() first to see what's on screen and get element indices."""
    from gitd.services.device_context import get_interactive_elements
    elements = get_interactive_elements(device)

    if idx < 0 or idx >= len(elements):
        return f"Error: element idx {idx} out of range (0-{len(elements) - 1})"

    center = elements[idx]["center"]
    cx, cy = center["x"], center["y"]
    get_device(device).tap(cx, cy)
    return f"Tapped element #{idx} at ({cx}, {cy})"


@mcp.tool()
def swipe(device: str, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 500) -> str:
    """Swipe from (x1,y1) to (x2,y2). Use for scrolling, pulling down notifications, etc.
    Common patterns: scroll down = swipe(dev, 540, 1400, 540, 600)
                     scroll up   = swipe(dev, 540, 600, 540, 1400)"""
    get_device(device).swipe(x1, y1, x2, y2, ms=duration_ms)
    return f"Swiped ({x1},{y1}) -> ({x2},{y2}) in {duration_ms}ms"


@mcp.tool()
def type_text(device: str, text: str) -> str:
    """Type text into the currently focused input field.
    Tap an input field first to focus it. Spaces are supported.
    Non-ASCII input is transliterated to the closest ASCII (adb input text is
    ASCII-only); for full-fidelity emoji/CJK use type_unicode() instead."""
    if is_ios_ref(device):
        get_device(device).type_text(text)
        return f"Typed: {text}"
    from gitd.bots.common.adb import ascii_typeable, input_text_arg

    typed = ascii_typeable(text)
    Device(device).adb("shell", "input", "text", input_text_arg(typed))
    if typed != text:
        return f"Typed (transliterated non-ASCII): {text!r} -> {typed!r}"
    return f"Typed: {typed}"


@mcp.tool()
def type_unicode(device: str, text: str) -> str:
    """Type unicode text into the focused field.
    Android uses ADBKeyboard when configured; iOS uses WDA text entry.
    Use type_text() for plain ASCII."""
    if is_ios_ref(device):
        get_device(device).type_text(text)
    else:
        Device(device).type_unicode(text)
    return f"Typed (unicode): {text}"


@mcp.tool()
def press_back(device: str) -> str:
    """Press Back on Android or the best available iOS browser/navigation back action."""
    get_device(device).back()
    return "Pressed Back"


@mcp.tool()
def press_home(device: str) -> str:
    """Press the platform Home button. Returns to the home screen."""
    if is_ios_ref(device):
        get_device(device).press_key("HOME")
    else:
        Device(device).adb("shell", "input", "keyevent", "KEYCODE_HOME")
    return "Pressed Home"


@mcp.tool()
def press_key(device: str, key: str) -> str:
    """Send a platform key event.
    Android accepts KEYCODE_* names, with the KEYCODE_ prefix added automatically.
    iOS supports WDA-backed HOME, ENTER/RETURN, and BACK/ESCAPE."""
    if is_ios_ref(device):
        get_device(device).press_key(key)
        return f"Sent {key}"
    from gitd.bots.common.adb import normalize_keycode

    key = normalize_keycode(key)
    Device(device).adb("shell", "input", "keyevent", key)
    return f"Sent {key}"


@mcp.tool()
def launch_app(device: str, package: str, fresh: bool = False) -> str:
    """Launch an app by Android package name or iOS bundle id. Use search_apps() to find it.

    Args:
        device: ADB serial or ios:<udid>.
        package: App package name or iOS bundle id, e.g. "com.android.chrome" or "com.google.chrome.ios".
        fresh: If True, force-stop the app first (cold start, clears in-memory
            state — back stack, unsaved drafts, login flow position, etc.).
            If False (default), reuses any existing background instance (warm
            start — resumes wherever the user left off).
            Use fresh=True for benchmarks, fresh start of a flow, or when the
            current app state would interfere with the task.
    """
    from gitd.services.agent_tools import execute_tool
    return execute_tool("launch_app", {"device": device, "package": package, "fresh": fresh})


@mcp.tool()
def force_stop(device: str, package: str) -> str:
    """Force-stop an Android package or terminate an iOS bundle id."""
    from gitd.services.agent_tools import execute_tool

    return execute_tool("force_stop", {"device": device, "package": package})


@mcp.tool()
def app_state(device: str, package: str) -> str:
    """Check whether an Android package or iOS bundle id is installed, running, or foreground."""
    from gitd.services.device_context import app_state as _app_state

    return json.dumps(_app_state(device, package), indent=2)


@mcp.tool()
def open_camera(device: str, mode: str = "photo", timer_s: int = 0) -> str:
    """Open the platform camera app in a specific mode.

    Android uses launcher/UI automation; iOS uses the Camera bundle and WDA UI
    controls. No package or bundle id is required.

    Args:
        device: ADB serial or ios:<udid>.
        mode: One of:
            "photo"        — rear camera, photo mode (default)
            "video"        — rear camera, video/record mode
            "selfie"       — front camera, photo mode
            "selfie_video" — front camera, video mode
        timer_s: Self-timer delay in seconds. Supported: 0 (off), 2, 3, 5, 10.
                 Uses UI automation — snaps to the closest value the device supports
                 (ASUS: 3s/10s, Samsung: 2s/5s/10s). 0 = no timer (default).
    """
    from gitd.services.agent_tools import execute_tool
    return execute_tool("open_camera", {"device": device, "mode": mode, "timer_s": timer_s})


@mcp.tool()
def speak_text(device: str, text: str, rate: float = 1.0) -> str:
    """Make the phone speak text aloud using its built-in TTS engine.

    Works whether the agent runs on the phone or on a PC — the call always
    goes through the Ghost portal app running on the device.

    Args:
        device: ADB serial. This tool is Android-only.
        text:   Text to speak.
        rate:   Speech rate multiplier (0.5 = slow, 1.0 = normal, 1.5 = fast).
    """
    if is_ios_ref(device):
        return _ios_unsupported("speak_text")
    from gitd.services.device_context import speak_text as _speak
    return _speak(device, text, rate)


@mcp.tool()
def search_apps(device: str, query: str) -> str:
    """Search installed apps by name. Case-insensitive. Returns Android packages or iOS bundle ids.
    Example: search_apps('tiktok') → [{"name": "TikTok", "package": "com.zhiliaoapp.musically"}]"""
    from gitd.services.agent_tools import execute_tool
    return execute_tool("search_apps", {"device": device, "query": query})


@mcp.tool()
def list_apps(device: str) -> str:
    """List installed apps with human-readable names and package names or bundle ids.
    iOS is limited to configured/common bundle ids verified through Appium."""
    from gitd.services.agent_tools import execute_tool
    return execute_tool("list_apps", {"device": device})


@mcp.tool()
def list_packages(device: str) -> str:
    """List raw Android package names or iOS bundle ids. Prefer list_apps() for display names."""
    from gitd.services.agent_tools import execute_tool

    return execute_tool("list_packages", {"device": device})


@mcp.tool()
def long_press(device: str, x: int, y: int, duration_ms: int = 1000) -> str:
    """Long press at coordinates. Use for context menus, drag initiation, etc."""
    get_device(device).long_press(x, y, duration_ms=duration_ms)
    return f"Long pressed ({x}, {y}) for {duration_ms}ms"


@mcp.tool()
def get_phone_state(device: str) -> str:
    """Get current app, activity, keyboard state, and focused element.
    Quick way to check what app/screen the device is on without parsing full elements."""
    from gitd.services.device_context import get_phone_state as _get_state
    return json.dumps(_get_state(device), indent=2)


@mcp.tool()
def device_health(device: str) -> str:
    """Run a comprehensive device health check.
    iOS includes Appium/WDA status, active session details, and recovery steps."""
    from gitd.services.device_context import device_health as _device_health
    return json.dumps(_device_health(device), indent=2)


@mcp.tool()
def fix_device_health(device: str, issue: str) -> str:
    """Apply a recovery action returned by device_health.recommended_fix."""
    from gitd.services.device_context import fix_device_health as _fix_device_health

    return json.dumps(_fix_device_health(device, issue), indent=2)


# ── Tier 1.5: Context Extraction ────────────────────────────────────────


@mcp.tool()
def get_screen_tree(device: str) -> str:
    """Get an LLM-friendly indented UI hierarchy of the current screen.
    Each node shows: [idx] ClassName "label" [clickable] [x1,y1][x2,y2].
    Use this to understand screen layout and pick which element to tap.
    Much more readable than raw XML — prefer this over get_elements() for planning."""
    from gitd.services.device_context import get_screen_tree as _tree
    return _tree(device)


@mcp.tool()
def get_screen_xml(device: str) -> str:
    """Get the raw normalized UI XML dump from the device.
    Android returns uiautomator XML; iOS returns normalized Appium/WDA XML.
    Use get_screen_tree() instead for a readable summary.
    Use this only when you need exact attribute values or the full hierarchy."""
    from gitd.services.device_context import get_screen_xml as _xml
    return _xml(device)


@mcp.tool()
def screenshot_annotated(device: str) -> str:
    """Take a screenshot with numbered element labels overlaid on interactive elements.
    The numbers correspond to element indices from get_elements().
    Use this when you want to SEE the screen with elements visually labelled.
    Returns base64-encoded PNG."""
    from gitd.services.device_context import screenshot_annotated as _ss
    result = _ss(device)
    return result.get("image", "")


@mcp.tool()
def screenshot_cropped(device: str, x1: int, y1: int, x2: int, y2: int) -> str:
    """Take a screenshot of a specific region of the screen.
    Coordinates are in device pixels. Use this to zoom in on a specific area
    (e.g., a form field, a notification, a chart). Returns base64-encoded JPEG."""
    from gitd.services.device_context import screenshot_cropped as _crop
    result = _crop(device, x1, y1, x2, y2)
    return result.get("image", "")


@mcp.tool()
def start_screen_recording(device: str, filename: str = "") -> str:
    """Start recording the device screen.

    iOS uses WDA MJPEG captured through ffmpeg. Android uses adb screenrecord.
    """
    from gitd.services.phone_recording import start_recording

    return json.dumps(start_recording(device, filename=filename), indent=2)


@mcp.tool()
def stop_screen_recording(device: str) -> str:
    """Stop a running device screen recording and save the MP4."""
    from gitd.services.phone_recording import stop_recording

    return json.dumps(stop_recording(device), indent=2)


@mcp.tool()
def screen_recording_status(device: str) -> str:
    """Return active screen recording status for a device."""
    from gitd.services.phone_recording import recording_status

    return json.dumps(recording_status(device), indent=2)


@mcp.tool()
def get_stream_info(device: str, mode: str = "mjpeg", fps: int = 5, quality: int = 8) -> str:
    """Return effective stream metadata without opening the stream.

    iOS reports WDA MJPEG URL/settings, screenshot fallback, and unsupported
    Portal/WebRTC actions. Android reports Portal/H264/screencap metadata.
    """
    from gitd.routers.streaming import phone_stream_info

    return json.dumps(phone_stream_info(device=device, mode=mode, fps=fps, quality=quality), indent=2)


@mcp.tool()
def ocr_screen(device: str) -> str:
    """OCR the entire device screen using RapidOCR. Returns all visible text with positions.
    Use this when UI elements are rendered as images/canvas (e.g., analytics dashboards,
    games, WebViews) where get_elements() returns no text.
    Returns JSON array of {text, conf, x, y, w, h} sorted top-to-bottom."""
    from gitd.services.device_context import ocr_screen as _ocr
    return json.dumps(_ocr(device), indent=2)


@mcp.tool()
def ocr_region(device: str, x1: int, y1: int, x2: int, y2: int) -> str:
    """OCR a specific region of the screen. Coordinates in device pixels.
    More accurate than full-screen OCR for targeted text extraction.
    Returns JSON array of {text, conf, x, y, w, h} relative to the crop region."""
    from gitd.services.device_context import ocr_region as _ocr
    return json.dumps(_ocr(device, x1, y1, x2, y2), indent=2)


@mcp.tool()
def classify_screen(device: str) -> str:
    """Classify the current screen: what app, what type of screen (home, search, profile,
    settings, dialog, error, loading), keyboard state. No LLM needed — uses XML heuristics.
    Use this for quick state checks before deciding what action to take."""
    from gitd.services.device_context import classify_screen as _cls
    return json.dumps(_cls(device), indent=2)


@mcp.tool()
def toggle_overlay(device: str, visible: bool = True) -> str:
    """Toggle the numbered element overlay on the device screen.
    When on, interactive elements get visible numbered labels that match get_elements() indices.
    Useful for visual debugging or when sending screenshots to a vision model."""
    if is_ios_ref(device):
        return _ios_unsupported("toggle_overlay")
    from gitd.services.device_context import toggle_overlay as _toggle
    ok = _toggle(device, visible)
    return f"Overlay {'enabled' if visible else 'disabled'}" if ok else "Failed — Portal not available"


@mcp.tool()
def clipboard_get(device: str) -> str:
    """Get the current clipboard text from the device."""
    from gitd.services.device_context import clipboard_get as _get
    return _get(device) or "(empty)"


@mcp.tool()
def clipboard_set(device: str, text: str) -> str:
    """Set clipboard text on the device. Use with press_key(PASTE) to paste into fields."""
    from gitd.services.device_context import clipboard_set as _set
    return "Clipboard set" if _set(device, text) else "Failed"


@mcp.tool()
def paste_text(device: str, text: str) -> str:
    """Set clipboard text and immediately paste it into the currently focused field.
    Equivalent to clipboard_set + press_key(PASTE) in one call.
    Tap the target input field first to focus it, then call this."""
    if is_ios_ref(device):
        get_device(device).paste_text(text)
        return f"Inserted text on iOS: {text[:60]}{'...' if len(text) > 60 else ''}"
    from gitd.bots.common.adb import Device
    from gitd.services.device_context import clipboard_set as _set
    if not _set(device, text):
        return "Failed to set clipboard"
    Device(device).adb("shell", "input", "keyevent", "KEYCODE_PASTE")
    return f"Pasted: {text[:60]}{'…' if len(text) > 60 else ''}"


@mcp.tool()
def get_notifications(device: str) -> str:
    """Get active notifications. Returns JSON array of {package, title, text}."""
    from gitd.services.device_context import get_notifications as _notif
    return json.dumps(_notif(device), indent=2)


@mcp.tool()
def open_notifications(device: str) -> str:
    """Pull down the notification shade or iOS Notification Center."""
    from gitd.services.device_context import open_notifications as _open
    if not _open(device):
        return "Failed"
    return "Notification Center opened" if is_ios_ref(device) else "Notification shade opened"


@mcp.tool()
def clear_notifications(device: str) -> str:
    """Dismiss visible notifications when the platform exposes a clear control."""
    from gitd.services.device_context import clear_notifications as _clear
    return "Notifications cleared" if _clear(device) else "Failed"


@mcp.tool()
def web_search(device: str, query: str, engine: str = "google", bundle_id: str = "") -> str:
    """Open a web search in whatever browser is on the device.

    Faster than: launch Chrome → tap address bar → type → submit. Useful when
    the user asks "search for X" or you need to look up info that's not on the
    current screen. Picks the first installed browser from a fallback chain
    (Chrome → Firefox → Samsung Internet → Edge → Brave → Opera → Vivaldi →
    DuckDuckGo Browser → system default), so it works even if Chrome is missing.

    Args:
        device: ADB serial or ios:<udid>.
        query: Free-text search terms (don't pre-escape — handled here).
        engine: "google" (default), "ddg" / "duckduckgo", "bing", or "brave".
        bundle_id: Optional iOS browser bundle id override, e.g. com.google.chrome.ios.
    """
    if is_ios_ref(device):
        from gitd.services.browser import dumps
        from gitd.services.browser import web_search as _web_search

        return dumps(_web_search(device, query, engine=engine, bundle_id=bundle_id or None))
    from gitd.services.web_search import open_search
    return open_search(device, query, engine=engine)


@mcp.tool()
def open_url(device: str, url: str, bundle_id: str = "") -> str:
    """Open a URL in the platform browser.

    On iOS this uses Appium/WDA and defaults to the configured browser bundle
    id, usually com.google.chrome.ios or com.apple.mobilesafari.
    """
    from gitd.services.browser import dumps
    from gitd.services.browser import open_url as _open_url

    return dumps(_open_url(device, url, bundle_id=bundle_id or None))


@mcp.tool()
def browser_back(device: str) -> str:
    """Navigate back in the current browser/app context."""
    from gitd.services.browser import browser_back as _browser_back
    from gitd.services.browser import dumps

    return dumps(_browser_back(device))


@mcp.tool()
def get_current_url(device: str) -> str:
    """Get the current browser URL when the platform exposes it."""
    if not supports_platform("get_current_url", _device_platform(device)):
        return _platform_unsupported("get_current_url", device)
    from gitd.services.browser import dumps
    from gitd.services.browser import get_current_url as _get_current_url

    return dumps(_get_current_url(device))


@mcp.tool()
def wait_for_text(device: str, text: str, timeout: float = 12.0) -> str:
    """Wait until text appears on screen and return visible text context."""
    from gitd.services.browser import dumps
    from gitd.services.browser import wait_for_text as _wait_for_text

    return dumps(_wait_for_text(device, text, timeout=timeout))


@mcp.tool()
def extract_visible_text(device: str, max_lines: int = 200, include_controls: bool = False) -> str:
    """Extract visible text from the current screen with browser chrome filtered by default."""
    from gitd.services.browser import dumps
    from gitd.services.browser import extract_visible_text as _extract_visible_text

    return dumps(_extract_visible_text(device, max_lines=max_lines, include_controls=include_controls))


@mcp.tool()
def extract_articles(device: str, max_items: int = 5) -> str:
    """Extract likely visible article/headline candidates from the current browser page."""
    from gitd.services.browser import dumps
    from gitd.services.browser import extract_articles as _extract_articles

    return dumps(_extract_articles(device, max_items=max_items))


@mcp.tool()
def read_news(
    device: str,
    url: str = "https://text.npr.org/",
    max_headlines: int = 5,
    max_articles: int = 3,
    bundle_id: str = "",
    wait_s: float = 2.0,
    save_screenshots: bool = False,
) -> str:
    """Open a news page and return structured headlines plus article snippets.

    This is the iOS Chrome/WebDriver smoke workflow exposed as a single tool.
    """
    if not supports_platform("read_news", _device_platform(device)):
        return _platform_unsupported("read_news", device)
    from gitd.services.browser import dumps
    from gitd.services.browser import read_news as _read_news

    return dumps(
        _read_news(
            device,
            url,
            max_headlines=max_headlines,
            max_articles=max_articles,
            bundle_id=bundle_id or None,
            wait_s=wait_s,
            save_screenshots=save_screenshots,
        )
    )


@mcp.tool()
def launch_intent(device: str, action: str = "", data: str = "",
                  package: str = "", extras: str = "{}") -> str:
    """Launch a full Android intent. More powerful than launch_app().
    Examples:
      Open a URL: action="android.intent.action.VIEW" data="https://google.com"
      Open Settings: package="com.android.settings"
      Share text: action="android.intent.action.SEND" extras='{"android.intent.extra.TEXT": "hello"}'"""
    if is_ios_ref(device):
        return _ios_unsupported("launch_intent")
    from gitd.services.device_context import launch_intent as _intent
    parsed_extras = json.loads(extras) if extras and extras != "{}" else None
    return _intent(device, action=action, data=data, package=package, extras=parsed_extras)


@mcp.tool()
def find_on_screen(device: str, text: str) -> str:
    """Find specific text on the screen and return its location.
    Searches XML elements first (fast), falls back to OCR if not found.
    Use this to check if a button, label, or message is visible.
    Returns JSON with {text, x, y, w, h, method} or null if not found."""
    from gitd.services.device_context import find_on_screen as _find
    result = _find(device, text)
    return json.dumps(result, indent=2) if result else "Not found"


# ── Tier 2: Skill Workflows ─────────────────────────────────────────────


@mcp.tool()
def list_skills(device: str = "", supported_only: bool = False) -> str:
    """List all installed mobile automation skills with their actions, workflows, and platform support.
    Use this to discover what high-level automations are available.
    Prefer using run_workflow() over raw tap/swipe when a skill exists for the task."""
    import yaml

    skills_dir = Path(__file__).parent / "skills"
    result = []
    for d in sorted(skills_dir.iterdir()):
        meta_path = d / "skill.yaml"
        if d.is_dir() and meta_path.exists() and not d.name.startswith("__"):
            meta = yaml.safe_load(meta_path.read_text()) or {}
            platform_summary = skill_platform_summary(meta)
            supported = skill_supports_device(meta, device) if device else None
            if supported_only and supported is False:
                continue
            info = {
                "name": meta.get("name", d.name),
                "app_package": platform_summary["app_package"],
                "android_package": platform_summary["android_package"],
                "ios_bundle_id": platform_summary["ios_bundle_id"],
                "platforms": platform_summary["platforms"],
                "supports_android": platform_summary["supports_android"],
                "supports_ios": platform_summary["supports_ios"],
                "platform_limitations": platform_summary["platform_limitations"],
                "default_params": meta.get("default_params", {}),
                "description": meta.get("description", ""),
            }
            if supported is not None:
                info["supported_on_device"] = supported
            # Try loading runtime actions/workflows
            try:
                mod = importlib.import_module(f"gitd.skills.{d.name}")
                s = mod.load()
                info["actions"] = s.list_actions()
                info["workflows"] = s.list_workflows()
            except Exception:
                # Check for recorded skill
                rec = d / "workflows" / "recorded.json"
                if rec.exists():
                    steps = json.loads(rec.read_text())
                    info["actions"] = [
                        f"step_{i + 1}: {s.get('description', s.get('action', ''))}" for i, s in enumerate(steps)
                    ]
                    info["workflows"] = ["recorded"]
                else:
                    info["actions"] = meta.get("exports", {}).get("actions", [])
                    info["workflows"] = meta.get("exports", {}).get("workflows", [])
            result.append(info)
    return json.dumps(result, indent=2)


@mcp.tool()
def run_workflow(device: str, skill: str, workflow: str, params: str = "{}") -> str:
    """Run an installed skill workflow on the device.

    Call list_skills() first to see available skills and workflows.

    Examples:
      run_workflow("SERIAL", "tiktok", "upload_video", '{"video_path": "/tmp/video.mp4"}')
      run_workflow("SERIAL", "send_gmail_email", "recorded", '{"subject": "Hello", "body": "Test"}')

    params is a JSON string of keyword arguments for the workflow."""
    meta = _load_skill_metadata(skill)
    if not skill_supports_device(meta, device):
        return skill_platform_error_text(skill, meta, device)
    parsed_params = json.loads(params)
    runner = Path(__file__).parent / "skills" / "_run_skill.py"
    result = subprocess.run(
        [
            sys.executable,
            "-u",
            str(runner),
            "--skill",
            skill,
            "--workflow",
            workflow,
            "--device",
            device,
            "--params",
            json.dumps(parsed_params),
        ],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=str(Path(__file__).parent.parent),
    )
    output = result.stdout.strip()
    if result.returncode != 0:
        output += f"\nSTDERR: {result.stderr.strip()}" if result.stderr else ""
        return f"FAILED (exit {result.returncode}):\n{output}"
    return f"SUCCESS:\n{output}"


@mcp.tool()
def run_action(device: str, skill: str, action: str, params: str = "{}") -> str:
    """Run a single skill action on the device.

    Call list_skills() first to see available actions.

    Examples:
      run_action("SERIAL", "tiktok", "open_app", '{}')
      run_action("SERIAL", "tiktok", "type_and_search", '{"query": "cats"}')"""
    meta = _load_skill_metadata(skill)
    if not skill_supports_device(meta, device):
        return skill_platform_error_text(skill, meta, device)
    parsed_params = json.loads(params)
    runner = Path(__file__).parent / "skills" / "_run_skill.py"
    result = subprocess.run(
        [
            sys.executable,
            "-u",
            str(runner),
            "--skill",
            skill,
            "--action",
            action,
            "--device",
            device,
            "--params",
            json.dumps(parsed_params),
        ],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(Path(__file__).parent.parent),
    )
    output = result.stdout.strip()
    if result.returncode != 0:
        output += f"\nSTDERR: {result.stderr.strip()}" if result.stderr else ""
        return f"FAILED (exit {result.returncode}):\n{output}"
    return f"SUCCESS:\n{output}"


# ── Batch flow ──────────────────────────────────────────────────────────
# Execute a whole sequence of tool calls in ONE MCP round-trip. Today every
# action is its own round-trip, so the LLM re-sends the schema + a screenshot +
# history per step; batching collapses that into one call with a single final
# screenshot — the token/latency win.

MAX_FLOW_STEPS = 50

# ALLOW-list of tools permitted inside a batched flow. A batch is exactly where
# an injected instruction would smuggle arbitrary execution, so run_flow is
# fail-CLOSED: only explicitly-vetted read/UI tools may run. Anything not on the
# list — a dangerous tool (shell, run_skill) OR any tool added to execute_tool
# in the future — is refused. Shared with the framework adapters (one source of
# truth, so the two can't drift): gitd.services.agent_tools.SAFE_DEVICE_TOOLS.
FLOW_ALLOWED_TOOLS = SAFE_DEVICE_TOOLS


def _run_flow(device: str, steps: object) -> dict:
    """Core of run_flow (kept import-light + side-effect-free to unit test).

    Validates the whole batch first (shape + allow-list), then executes each
    step, aborting on the first error. Returns a consolidated dict with per-step
    results and ONE final screenshot.

    Dispatches via _execute_tool_inner (not the wrapped execute_tool): the
    wrapper appends a fresh screen tree and sleeps 0.5s after every UI action,
    which for a 50-step flow would add ~25s of latency and 50 inflated results —
    exactly the per-step overhead batching exists to remove. We take one final
    screenshot for the whole batch instead.
    """
    from gitd.services.agent_tools import _execute_tool_inner, get_screenshot_b64

    if not isinstance(steps, list):
        return {"error": "steps must be a JSON list of {tool, args} objects"}
    if not steps:
        return {"error": "steps is empty"}
    if len(steps) > MAX_FLOW_STEPS:
        return {"error": f"too many steps ({len(steps)} > {MAX_FLOW_STEPS})"}

    # Fail closed: validate EVERY step before running ANY of them, so a flow
    # that hides a disallowed action after some benign steps executes nothing.
    for i, step in enumerate(steps):
        if not isinstance(step, dict) or "tool" not in step:
            return {"error": f"step {i} must be an object with a 'tool' field"}
        if step["tool"] not in FLOW_ALLOWED_TOOLS:
            return {
                "error": f"step {i}: tool '{step['tool']}' is not allowed inside run_flow (injection guard)",
                "blocked": step["tool"],
            }

    results = []
    stopped_early = False
    for i, step in enumerate(steps):
        tool = step["tool"]
        args = dict(step.get("args") or {})
        args.setdefault("device", device)
        try:
            out = _execute_tool_inner(tool, args)
            results.append({"step": i, "tool": tool, "ok": True, "result": str(out)[:800]})
        except Exception as e:
            results.append({"step": i, "tool": tool, "ok": False, "error": f"{type(e).__name__}: {e}"[:800]})
            stopped_early = True
            break  # phase 1: abort on first error (on_error/if_not_found is phase 2)

    final_screenshot = ""
    try:
        final_screenshot = get_screenshot_b64(device) or ""
    except Exception:
        pass

    return {
        "steps_total": len(steps),
        "steps_run": len(results),
        "stopped_early": stopped_early,
        "results": results,
        "final_screenshot": final_screenshot,  # ONE shot for the whole batch
    }


@mcp.tool()
def run_flow(device: str, steps: str) -> str:
    """Run an ordered batch of tool calls server-side in ONE round-trip.

    `steps` is a JSON list of {"tool": "<name>", "args": {...}} — the same tool
    names execute_tool exposes (tap, tap_element, type_text, launch_app, etc.).
    Steps run in order and stop at the first error. Returns a JSON object with
    per-step results and a SINGLE final screenshot (not one per step) — far
    fewer tokens/round-trips than calling each tool separately. Steps do NOT
    auto-settle between UI actions; if a step needs the screen to update before
    the next one reads it, insert an explicit {"tool":"wait","args":{...}} step.

    Example:
      run_flow("SERIAL", '[{"tool":"launch_app","args":{"package":"com.android.settings"}},
                           {"tool":"find_on_screen","args":{"text":"Wi-Fi"}},
                           {"tool":"tap","args":{"x":540,"y":300}}]')

    Security: fail-closed allow-list — only vetted read/UI tools may run inside
    a flow. Anything else (raw `shell`, `run_skill`, or any unknown tool) makes
    the whole flow be refused before any step runs, since a batch is exactly
    where an injected instruction would smuggle a shell command. Max 50 steps.
    """
    try:
        parsed = json.loads(steps)
    except (ValueError, TypeError) as e:
        return json.dumps({"error": f"steps must be valid JSON: {e}"})
    return json.dumps(_run_flow(device, parsed))


# ── Crash reports ────────────────────────────────────────────────────────
# Read app crashes/ANRs from the logcat `crash` buffer — works WITHOUT root
# (unlike /data/tombstones or /data/anr, which need it). Parser is a pure
# function so it's unit-testable against captured logcat text.

_CRASH_TS_RE = re.compile(r"^(\d\d-\d\d \d\d:\d\d:\d\d\.\d+)")


def _run_logcat_crash(device: str, timeout: int = 10) -> str:
    """Dump the crash + events ring buffers (`-d` = dump and exit).

    Reads the `crash` buffer (Java FATAL EXCEPTIONs) AND the `events` buffer,
    which is where ANRs land as `am_anr` events — the crash buffer has none.

    Raises on any adb failure so callers surface a real error instead of a
    phantom "no crashes": an offline/unauthorized device makes adb exit nonzero
    with empty stdout, which would otherwise parse to zero crashes and read as
    "the app is fine".
    """
    try:
        r = subprocess.run(
            ["adb", "-s", device, "logcat", "-b", "crash", "-b", "events", "-d"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as e:
        raise RuntimeError("adb not found on PATH") from e
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"adb logcat timed out after {timeout}s (device unresponsive?)") from e
    if r.returncode != 0:
        raise RuntimeError(f"adb exited {r.returncode}: {(r.stderr or '').strip() or 'device offline/unauthorized?'}")
    return r.stdout


def _parse_crashes(logcat_text: str) -> list[dict]:
    """Parse the crash buffer into crash events, most-recent first.

    Handles Java `FATAL EXCEPTION` blocks (with process + first exception line)
    and `ANR in <pkg>` lines. Native tombstones need root and are out of scope.
    """
    lines = logcat_text.splitlines()
    crashes: list[dict] = []
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        if "FATAL EXCEPTION" in line and "AndroidRuntime:" in line:
            ts_m = _CRASH_TS_RE.match(line)
            ts = ts_m.group(1) if ts_m else ""
            block, process, summary = [], "", ""
            j = i
            while j < n and "AndroidRuntime:" in lines[j]:
                content = lines[j].split("AndroidRuntime:", 1)[1].strip()
                block.append(lines[j])
                pm = re.search(r"Process:\s*([^,]+)", content)
                if pm and not process:
                    process = pm.group(1).strip()
                if not summary and "FATAL EXCEPTION" not in content and ("Exception" in content or "Error" in content):
                    summary = content
                j += 1
            crashes.append(
                {
                    "type": "java",
                    "timestamp": ts,
                    "process": process,
                    "summary": summary or "FATAL EXCEPTION",
                    "raw": "\n".join(block),
                }
            )
            i = j
            continue
        if "ANR in " in line:
            ts_m = _CRASH_TS_RE.match(line)
            am = re.search(r"ANR in ([^\s(]+)", line)
            crashes.append(
                {
                    "type": "anr",
                    "timestamp": ts_m.group(1) if ts_m else "",
                    "process": am.group(1) if am else "",
                    "summary": line.split("ANR in ", 1)[1].strip() if "ANR in " in line else line.strip(),
                    "raw": line,
                }
            )
        elif "am_anr" in line:
            # events-buffer ANR: `... I am_anr : [userId,pid,packageName,flags,reason]`
            ts_m = _CRASH_TS_RE.match(line)
            bm = re.search(r"\[([^\]]*)\]", line)
            fields = [f.strip() for f in bm.group(1).split(",")] if bm else []
            if len(fields) >= 3:
                crashes.append(
                    {
                        "type": "anr",
                        "timestamp": ts_m.group(1) if ts_m else "",
                        "process": fields[2],
                        "summary": "ANR: " + ", ".join(fields[4:]) if len(fields) > 4 else "ANR",
                        "raw": line,
                    }
                )
        i += 1
    crashes.reverse()  # logcat is chronological → most recent first
    return crashes


@mcp.tool()
def list_crashes(device: str, package: str = "", limit: int = 10) -> str:
    """List recent app crashes and ANRs (from the logcat crash buffer, no root).

    Android-only: iOS crash logs need syslog/CrashReporter access, not exposed yet.
    Optionally filter by package (substring match on the crashing process).
    Returns JSON: {count, crashes: [{type, timestamp, process, summary}]}.
    Use get_crash() to pull a full stack for the most recent one."""
    if is_ios_ref(device):
        return json.dumps({"error": _ios_unsupported("list_crashes")})
    try:
        text = _run_logcat_crash(device)
    except Exception as e:
        return json.dumps({"error": f"could not read crash log: {e}"})
    crashes = _parse_crashes(text)
    if package:
        crashes = [c for c in crashes if package in (c["process"] or "")]
    out = [
        {"type": c["type"], "timestamp": c["timestamp"], "process": c["process"], "summary": c["summary"][:300]}
        for c in crashes[:limit]
    ]
    return json.dumps({"count": len(out), "crashes": out}, indent=2)


@mcp.tool()
def get_crash(device: str, package: str = "") -> str:
    """Return the full stack trace of the MOST RECENT crash (from the crash buffer).

    Android-only: iOS crash logs need syslog/CrashReporter access, not exposed yet.
    Optionally filter by package. Pair with list_crashes() to see what's there."""
    if is_ios_ref(device):
        return f"Error: {_ios_unsupported('get_crash')}"
    try:
        text = _run_logcat_crash(device)
    except Exception as e:
        return f"Error: could not read crash log: {e}"
    crashes = _parse_crashes(text)
    if package:
        crashes = [c for c in crashes if package in (c["process"] or "")]
    if not crashes:
        scope = f" for {package}" if package else ""
        return f"No crashes found{scope} in the crash buffer."
    c = crashes[0]
    return f"[{c['type']}] {c['timestamp']} {c['process']}\n{c['raw'][:6000]}"


# ── Tier 3: Meta / Discovery ────────────────────────────────────────────


@mcp.tool()
def wait(seconds: float = 2.0) -> str:
    """Pause execution for a fixed number of seconds."""
    from gitd.services.agent_tools import execute_tool

    return execute_tool("wait", {"seconds": seconds})


@mcp.tool()
def explore_app(device: str, package: str, max_depth: int = 2, max_states: int = 10) -> str:
    """Explore an app's UI autonomously using BFS.
    Launches the app, taps every interactive element, builds a state graph.
    Returns JSON with discovered screens, elements, and transitions.
    Use this to understand an unfamiliar app before writing automation for it."""
    script = Path(__file__).parent / "skills" / "auto_creator.py"
    result = subprocess.run(
        [
            sys.executable,
            "-u",
            str(script),
            "--package",
            package,
            "--device",
            device,
            "--max-depth",
            str(max_depth),
            "--max-states",
            str(max_states),
        ],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=str(Path(__file__).parent.parent),
    )
    graph_path = Path(f"data/app_explorer/{package}/state_graph.json")
    if graph_path.exists():
        return graph_path.read_text()[:10000]
    output = result.stdout[-1000:]
    if result.returncode != 0 and result.stderr:
        output += f"\nSTDERR:\n{result.stderr[-1000:]}"
    return f"Exploration finished. Output:\n{output}"


@mcp.tool()
def create_skill(
    name: str,
    app_package: str,
    steps: str,
    platforms: str = "",
    ios_bundle_id: str = "",
    elements_ios: str = "",
    elements_android: str = "",
) -> str:
    """Create a new reusable skill from a JSON list of recorded steps.

    steps is a JSON array like:
    [
      {"action": "launch", "package": "com.example.app", "description": "Open app"},
      {"action": "tap", "x": 540, "y": 1200, "description": "Tap button"},
      {"action": "type", "text": "hello", "description": "Type greeting"},
      {"action": "wait", "seconds": 2, "description": "Wait for load"}
    ]

    Supported actions: launch, tap (x,y or element_idx), type, swipe, back, home, wait.
    For iOS skills, pass platforms="ios" and either app_package or ios_bundle_id as the bundle id.
    Optional elements_ios/elements_android are JSON selector maps written to elements_ios.yaml/elements.yaml.
    After creating, use run_workflow(dev, name, "recorded", params) to replay it."""
    from gitd.services.skill_creation import create_recorded_skill

    result = create_recorded_skill(
        name=name,
        app_package=app_package,
        steps=steps,
        platforms=platforms,
        ios_bundle_id=ios_bundle_id,
        elements_ios=elements_ios,
        elements_android=elements_android,
        skills_dir=Path(__file__).parent / "skills",
    )
    return result["message"]


# ── Lead / influencer lookups (for marketing agents) ────────────────────────


@mcp.tool()
def lookup_lead(handle: str) -> str:
    """Get the full fact sheet for one influencer lead by handle.

    Use this when you need to know everything about an influencer to draft
    a personalised reply or decide next-step outreach: their follower count,
    engagement, bio, niche, what hashtag we found them on, when we DMed them,
    which account sent the DM, their latest reply, and unread state.

    Args:
        handle: TikTok username, with or without @ (e.g. 'bajapawsllc' or '@bajapawsllc')
    """
    from gitd.services.marketing_lookup import lookup_lead as _lookup_lead

    return _lookup_lead(handle)


@mcp.tool()
def list_unread_leads() -> str:
    """List every influencer with an unread reply in the inbox, sorted by recency.

    Returns one row per unread conversation with the handle, unread count,
    last message preview, and timestamp. Useful for daily prioritisation:
    'which leads should I respond to right now?'
    """
    from gitd.services.marketing_lookup import list_unread_leads as _list_unread_leads

    return _list_unread_leads()


# ── Local CRM lookups ────────────────────────────────────────────────────────


@mcp.tool()
def crm_lookup_contact(handle: str) -> str:
    """Get the stored fact sheet for one local CRM contact by handle. Read-only.

    Returns the contact's profile fields, contact status/history, and the
    latest conversation state (last message, unread count, timestamps).

    Args:
        handle: Contact handle, with or without @.
    """
    from gitd.services.crm_lookup import crm_lookup_contact as _lookup

    return _lookup(handle)


@mcp.tool()
def crm_list_unread_messages() -> str:
    """List local CRM contacts with unread messages, sorted by recency. Read-only.

    Returns one row per unread conversation with the handle, unread count,
    last message preview, and timestamp.
    """
    from gitd.services.crm_lookup import crm_list_unread_messages as _list_unread

    return _list_unread()


def main():
    mcp.run()


if __name__ == "__main__":
    main()
