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
    "get_elements": "Uses normalized Android/iOS element shape.",
    "get_screen_tree": "Uses normalized Android/iOS XML.",
    "get_screen_xml": "Returns Android uiautomator XML or normalized iOS WDA XML.",
    "get_phone_state": "Uses Android state probes or iOS activeAppInfo/window state.",
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
    "long_press": "Routes to ADB/Portal or WDA pointer actions.",
    "web_search": "Android VIEW intent or iOS Appium browser navigation.",
    "open_url": "Android VIEW intent or iOS Appium browser navigation.",
    "browser_back": "Android back or iOS browser/WDA back fallback.",
    "wait_for_text": "Android screen search or iOS visible text wait.",
    "extract_visible_text": "Android normalized text extraction or iOS native/web text extraction.",
    "extract_articles": "Best-effort article/headline extraction on either platform.",
    "list_skills": "Lists skills with platform metadata.",
    "run_skill": "Runs platform-aware skills when the skill supports the target platform.",
    "run_workflow": "Runs platform-aware skills when the skill supports the target platform.",
    "run_action": "Runs platform-aware skill actions when supported.",
    "clipboard_get": "Uses Android clipboard helpers or Appium clipboard extensions on iOS.",
    "clipboard_set": "Uses Android clipboard helpers or Appium clipboard extensions on iOS.",
    "lookup_lead": "Device-neutral marketing data lookup.",
    "list_unread_leads": "Device-neutral marketing inbox lookup.",
    "wait": "Device-neutral delay.",
}

_IOS_SUPPORTED = {
    "get_current_url": "Currently implemented through iOS WebDriver/WebView state; Android current URL support is not exposed yet.",
}

_IOS_PLANNED = {
    "open_camera": "Feasible through iOS bundle launch and camera UI automation, not implemented yet.",
    "search_apps": "Needs iOS app inventory via Appium/idb/simctl or host tooling.",
    "list_apps": "Needs iOS app inventory via Appium/idb/simctl or host tooling.",
    "list_packages": "Needs iOS app inventory via Appium/idb/simctl or host tooling.",
    "paste_text": "Depends on iOS clipboard support and paste gesture/key fallback.",
    "get_notifications": "Needs Notification Center gesture/source extraction.",
    "open_notifications": "Needs iOS notification gesture support.",
    "clear_notifications": "Needs iOS notification UI automation.",
    "explore_app": "Needs explorer state identity based on bundle id, tree hash, and screenshot hash.",
    "create_skill": "Needs platform compatibility metadata and iOS element recording.",
}

_ANDROID_ONLY = {
    "shell": "ADB shell has no iOS equivalent.",
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
