"""Tools Hub routes — list, inspect, and test all available agent tools."""

import time

from fastapi import APIRouter, Body, HTTPException

router = APIRouter(prefix="/api/tools", tags=["tools-hub"])


def _get_all_tools() -> list[dict]:
    """Return all tools grouped by category."""
    from gitd.services.agent_tools import TOOLS
    from gitd.services.tool_platforms import tool_platform_info

    CATEGORIES = {
        "Screen Reading": [
            "screenshot",
            "screenshot_annotated",
            "screenshot_cropped",
            "start_screen_recording",
            "stop_screen_recording",
            "screen_recording_status",
            "get_screen_tree",
            "get_elements",
            "get_phone_state",
            "device_health",
            "fix_device_health",
            "classify_screen",
            "find_on_screen",
            "ocr_screen",
            "ocr_region",
            "get_screen_xml",
        ],
        "Web": [
            "web_search",
            "open_url",
            "browser_back",
            "get_current_url",
            "wait_for_text",
            "extract_visible_text",
            "extract_articles",
            "read_news",
        ],
        "Input": [
            "tap",
            "tap_element",
            "swipe",
            "type_text",
            "type_unicode",
            "press_back",
            "press_home",
            "press_key",
            "long_press",
        ],
        "App Management": ["launch_app", "force_stop", "app_state", "list_packages", "explore_app", "launch_intent"],
        "Shell": ["shell"],
        "Clipboard & Notifications": [
            "paste_text",
            "clipboard_get",
            "clipboard_set",
            "get_notifications",
            "open_notifications",
            "clear_notifications",
        ],
        "Skills": ["list_skills", "run_skill"],
        "Device": ["list_devices", "toggle_overlay"],
        "System": ["wait"],
    }

    # Build lookup
    tool_map = {t["name"]: t for t in TOOLS}

    # Also add device_context tools not in TOOLS
    extra_tools = [
        {
            "name": "get_screen_xml",
            "description": "Get raw UI XML dump from uiautomator.",
            "input_schema": {"type": "object", "properties": {"device": {"type": "string"}}, "required": ["device"]},
            "category": "Screen Reading",
        },
        {
            "name": "launch_intent",
            "description": "Launch full Android intent (action, data, package, extras).",
            "input_schema": {
                "type": "object",
                "properties": {
                    "device": {"type": "string"},
                    "action": {"type": "string"},
                    "data": {"type": "string"},
                    "package": {"type": "string"},
                },
                "required": ["device"],
            },
            "category": "App Management",
        },
        {
            "name": "open_notifications",
            "description": "Pull down the notification shade.",
            "input_schema": {"type": "object", "properties": {"device": {"type": "string"}}, "required": ["device"]},
            "category": "Clipboard & Notifications",
        },
        {
            "name": "clear_notifications",
            "description": "Dismiss all notifications.",
            "input_schema": {"type": "object", "properties": {"device": {"type": "string"}}, "required": ["device"]},
            "category": "Clipboard & Notifications",
        },
        {
            "name": "list_devices",
            "description": "List all connected Android devices with serial and model.",
            "input_schema": {"type": "object", "properties": {}},
            "category": "Device",
        },
        {
            "name": "toggle_overlay",
            "description": "Toggle Portal numbered element overlay on/off.",
            "input_schema": {
                "type": "object",
                "properties": {"device": {"type": "string"}, "visible": {"type": "boolean"}},
                "required": ["device"],
            },
            "category": "Device",
        },
    ]
    for et in extra_tools:
        if et["name"] not in tool_map:
            tool_map[et["name"]] = et

    result = []
    for cat, names in CATEGORIES.items():
        tools = []
        for name in names:
            t = tool_map.get(name)
            if t:
                params = []
                props = t.get("input_schema", {}).get("properties", {})
                required = t.get("input_schema", {}).get("required", [])
                for pname, pschema in props.items():
                    params.append(
                        {
                            "name": pname,
                            "type": pschema.get("type", "string"),
                            "required": pname in required,
                            "default": pschema.get("default"),
                        }
                    )
                tools.append(
                    {
                        "name": name,
                        "description": t.get("description", ""),
                        "params": params,
                        "category": cat,
                        "platform_support": tool_platform_info(name).to_dict(),
                    }
                )
        result.append({"category": cat, "tools": tools})
    return result


@router.get("", summary="List All Tools")
def list_tools():
    """List all available agent tools grouped by category."""
    return _get_all_tools()


@router.get("/platforms", summary="List Tool Platform Support")
def list_tool_platforms():
    """List platform support classification for every known agent/MCP tool."""
    from gitd.services.tool_platforms import TOOL_PLATFORM_SUPPORT

    return {
        "tools": [info.to_dict() for _, info in sorted(TOOL_PLATFORM_SUPPORT.items())],
        "categories": {
            "cross_platform": "Works on Android and iOS, or is device-neutral.",
            "android_only": "Intentionally Android-only; no iOS equivalent is planned for this tool shape.",
            "ios_supported": "Implemented for iOS, but Android parity is not exposed through this tool yet.",
            "ios_planned": "Android implementation exists; iOS replacement is planned but not implemented.",
        },
    }


@router.post("/test", summary="Test a Tool")
def test_tool(data: dict = Body({})):
    """Execute a tool with given args and return the result."""
    from gitd.bots.common.device import is_ios_ref
    from gitd.services.agent_tools import execute_tool
    from gitd.services.tool_platforms import platform_error, supports_platform

    tool_name = data.get("name", "")
    tool_args = data.get("args", {})
    if not tool_name:
        raise HTTPException(status_code=400, detail="tool name required")

    t0 = time.time()
    try:
        device = str(tool_args.get("device") or "")
        if device:
            platform = "ios" if is_ios_ref(device) else "android"
            if not supports_platform(tool_name, platform):
                duration_ms = (time.time() - t0) * 1000
                return {**platform_error(tool_name, platform), "duration_ms": round(duration_ms, 1)}
        result = execute_tool(tool_name, tool_args)
        duration_ms = (time.time() - t0) * 1000
        return {"ok": True, "result": result[:5000], "duration_ms": round(duration_ms, 1)}
    except Exception as e:
        duration_ms = (time.time() - t0) * 1000
        return {"ok": False, "error": str(e), "duration_ms": round(duration_ms, 1)}
