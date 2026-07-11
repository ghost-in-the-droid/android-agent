"""Platform support metadata for agent and MCP tools."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

PlatformSupport = Literal["cross_platform", "android_only", "ios_supported", "ios_planned"]


@dataclass(frozen=True)
class ToolPlatformInfo:
    name: str
    support: PlatformSupport
    notes: str = ""

    def supports(self, platform: str) -> bool:
        platform = platform.lower()
        if self.support == "cross_platform":
            return platform in {"android", "ios"}
        if self.support == "android_only":
            return platform == "android"
        if self.support == "ios_supported":
            return platform == "ios"
        if self.support == "ios_planned":
            return platform == "android"
        return False

    def to_dict(self) -> dict[str, str | bool]:
        return {
            "name": self.name,
            "support": self.support,
            "android": self.supports("android"),
            "ios": self.supports("ios"),
            "notes": self.notes,
        }


_CROSS_PLATFORM = {
    "list_devices": "Lists Android ADB devices and configured iOS Appium devices.",
    "screenshot": "Uses Android screencap or Appium screenshot.",
    "screenshot_annotated": "Draws labels from the normalized platform UI tree.",
    "screenshot_cropped": "Crops screenshots from either backend.",
    "start_screen_recording": "Android adb screenrecord or iOS WDA MJPEG captured through ffmpeg.",
    "stop_screen_recording": "Stops Android adb screenrecord or iOS WDA MJPEG/ffmpeg recording.",
    "screen_recording_status": "Reports active cross-platform phone screen recording status.",
    "get_stream_info": "Returns effective Android Portal/H264/screencap or iOS WDA MJPEG stream metadata.",
    "get_elements": "Uses normalized Android/iOS element shape.",
    "get_screen_tree": "Uses normalized Android/iOS XML.",
    "get_screen_xml": "Returns Android uiautomator XML or normalized iOS WDA XML.",
    "get_phone_state": "Uses Android state probes or iOS activeAppInfo/window state.",
    "device_health": "Checks Android Portal/device subsystems or iOS Appium/WDA health with actionable recovery steps.",
    "fix_device_health": "Applies Android Portal/screen fixes or iOS Appium/WDA recovery actions returned by device_health.",
    "classify_screen": "Runs against normalized state/tree data.",
    "find_on_screen": "Searches normalized XML with OCR fallback.",
    "ocr_screen": "Runs OCR on platform screenshot bytes.",
    "ocr_region": "Runs OCR on cropped screenshot bytes.",
    "tap": "Routes to ADB input tap or WDA pointer actions.",
    "tap_element": "Taps normalized element centers.",
    "swipe": "Routes to ADB input swipe or WDA pointer actions.",
    "type_text": "Routes to ADB input text or WDA keys/value.",
    "type_unicode": "Routes to Android unicode input or iOS WDA text entry.",
    "press_back": "Best-effort back action on each platform.",
    "press_home": "Uses Android HOME keyevent or iOS mobile: pressButton.",
    "press_key": "Shared key facade with per-platform key support.",
    "launch_app": "Launches Android packages or iOS bundle ids.",
    "force_stop": "Force-stops Android packages or terminates iOS bundle ids.",
    "app_state": "Checks installed/running/foreground state for Android packages or iOS bundle ids.",
    "open_camera": "Android camera launcher or best-effort iOS Camera app launch/mode selection.",
    "long_press": "Routes to ADB/Portal or WDA pointer actions.",
    "web_search": "Android VIEW intent or iOS Appium browser navigation.",
    "open_url": "Android VIEW intent or iOS Appium browser navigation.",
    "browser_back": "Android back or iOS browser/WDA back fallback.",
    "wait_for_text": "Android screen search or iOS visible text wait.",
    "extract_visible_text": "Android normalized text extraction or iOS WebView/native/OCR text extraction.",
    "extract_articles": "Best-effort article/headline extraction on either platform, with OCR fallback on iOS.",
    "search_apps": "Android package manager or iOS configured/common bundle inventory with Appium verification.",
    "list_apps": "Android package manager or iOS configured/common bundle inventory with Appium verification.",
    "list_packages": "Android package manager or iOS configured/common bundle inventory with Appium verification.",
    "list_skills": "Lists skills with platform metadata.",
    "run_skill": "Runs platform-aware skills when the skill supports the target platform.",
    "run_workflow": "Runs platform-aware skills when the skill supports the target platform.",
    "run_action": "Runs platform-aware skill actions when supported.",
    "clipboard_get": "Uses Android clipboard helpers or Appium clipboard extensions on iOS.",
    "clipboard_set": "Uses Android clipboard helpers or Appium clipboard extensions on iOS.",
    "paste_text": "Android clipboard paste keyevent or iOS clipboard plus WDA text insertion into the focused field.",
    "get_notifications": "Android dumpsys notifications or iOS Notification Center text extraction through WDA.",
    "open_notifications": "Android statusbar expansion or iOS Notification Center swipe gesture.",
    "clear_notifications": "Android notification service clear or best-effort iOS Clear control tap.",
    "explore_app": "BFS explorer over Android uiautomator XML or normalized iOS WDA XML with iOS tree/screenshot state identity.",
    "create_skill": "Creates recorded skills with Android package or iOS bundle metadata and per-platform element files.",
    "run_flow": "Batched execution of allow-listed tools; each step routes per-platform.",
    "crm_lookup_contact": "Device-neutral local CRM contact lookup.",
    "crm_list_unread_messages": "Device-neutral local CRM unread-message listing.",
    "chain": "Runs a sequence of sub-actions; each sub-action routes to its own platform backend.",
    "screenshot_sequence": "Captures a screenshot burst via the per-platform screenshot path.",
    "sub_agent": "Device-neutral vision sub-call over cached frames.",
    "wait": "Device-neutral delay.",
}

_IOS_SUPPORTED = {
    "get_current_url": "Currently implemented through iOS WebDriver/WebView state; Android current URL support is not exposed yet.",
    "read_news": "iOS Chrome/WebDriver news-reading workflow that opens headlines and extracts article snippets.",
}

_IOS_PLANNED = {}

_ANDROID_ONLY = {
    "shell": "ADB shell has no iOS equivalent.",
    "list_crashes": "Reads the Android logcat crash buffer; iOS needs syslog/CrashReporter support.",
    "get_crash": "Reads the Android logcat crash buffer; iOS needs syslog/CrashReporter support.",
    "launch_intent": "Android intents have no iOS equivalent.",
    "toggle_overlay": "Portal overlay is Android-only.",
    "speak_text": "Uses the Android Portal app TTS path.",
}


TOOL_PLATFORM_SUPPORT: dict[str, ToolPlatformInfo] = {
    **{name: ToolPlatformInfo(name, "cross_platform", notes) for name, notes in _CROSS_PLATFORM.items()},
    **{name: ToolPlatformInfo(name, "ios_supported", notes) for name, notes in _IOS_SUPPORTED.items()},
    **{name: ToolPlatformInfo(name, "ios_planned", notes) for name, notes in _IOS_PLANNED.items()},
    **{name: ToolPlatformInfo(name, "android_only", notes) for name, notes in _ANDROID_ONLY.items()},
}


def tool_platform_info(name: str) -> ToolPlatformInfo:
    return TOOL_PLATFORM_SUPPORT.get(
        name,
        ToolPlatformInfo(name, "ios_planned", "No explicit platform audit entry yet."),
    )


def tools_for_support(support: PlatformSupport) -> list[str]:
    return sorted(name for name, info in TOOL_PLATFORM_SUPPORT.items() if info.support == support)


def supports_platform(name: str, platform: str) -> bool:
    return tool_platform_info(name).supports(platform)


def platform_error(name: str, platform: str) -> dict[str, str | bool]:
    info = tool_platform_info(name)
    if info.support == "android_only":
        error = f"{name} is Android-only and is not supported for {platform}"
    elif info.support == "ios_planned":
        error = f"{name} is not supported for {platform} yet; iOS support is planned"
    elif info.support == "ios_supported":
        error = f"{name} is currently implemented only for iOS"
    else:
        error = f"{name} does not support {platform}"
    return {"ok": False, "platform": platform, "error": error, "support": info.support, "notes": info.notes}


def platform_error_text(name: str, platform: str) -> str:
    error = platform_error(name, platform)
    return f"ERROR: {error['error']}"


# ── Docs: generated platform-support matrix ──────────────────────────────────
# Emits the per-tool Android/iOS support matrix as Markdown straight from the
# classification above, so the public docs table never drifts from code. This is
# the CLASSIFICATION only — docs overlay a "hardware-confirmed on iOS" badge on
# top (some tools are classified cross-platform but not yet exercised on real WDA,
# and several fall back to OCR on iOS due to the weaker accessibility tree).
#   run:  python -m gitd.services.tool_platforms > tool-support.generated.md

_BADGE = {
    ("android_only", "android"): "✅",
    ("android_only", "ios"): "⚠️ n/a",
    ("cross_platform", "android"): "✅",
    ("cross_platform", "ios"): "✅",
    ("ios_supported", "android"): "⚠️ n/a",
    ("ios_supported", "ios"): "✅",
    ("ios_planned", "android"): "✅",
    ("ios_planned", "ios"): "🔜",
}

_SUPPORT_HEADING = {
    "cross_platform": "Cross-platform (Android + iOS)",
    "ios_supported": "iOS-first",
    "ios_planned": "Android now, iOS planned",
    "android_only": "Android-only",
}


def _row(info: ToolPlatformInfo) -> str:
    android = _BADGE[(info.support, "android")]
    ios = _BADGE[(info.support, "ios")]
    notes = (info.notes or "").replace("|", "\\|")
    return f"| `{info.name}` | {android} | {ios} | {notes} |"


def render_matrix_markdown() -> str:
    """Render the full tool platform-support matrix as Markdown.

    Grouped by support class, each group a table with an Android / iOS badge and
    the per-tool note. Badges: ✅ supported · 🔜 iOS planned · ⚠️ n/a (not
    applicable on that platform). Deterministic (sorted) so regenerating in CI
    produces a stable diff.
    """
    lines = [
        "<!-- GENERATED from gitd/services/tool_platforms.py — do not edit by hand.",
        "     Regenerate: python -m gitd.services.tool_platforms -->",
        "",
        "Legend: ✅ supported · 🔜 iOS planned · ⚠️ n/a (platform can't support it).",
        "Classification only — overlay a 'hardware-confirmed on iOS' badge separately;",
        "several cross-platform tools fall back to OCR on iOS (weaker a11y tree).",
    ]
    for support in ("cross_platform", "ios_supported", "ios_planned", "android_only"):
        names = tools_for_support(support)
        if not names:
            continue
        lines += [
            "",
            f"### {_SUPPORT_HEADING[support]} ({len(names)})",
            "",
            "| Tool | Android | iOS | Notes |",
            "| --- | :---: | :---: | --- |",
        ]
        lines += [_row(TOOL_PLATFORM_SUPPORT[name]) for name in names]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":  # pragma: no cover — docs build entry point
    import sys

    sys.stdout.write(render_matrix_markdown())
