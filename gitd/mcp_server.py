#!/usr/bin/env python3
"""MCP Server — expose Android automation as tools for any LLM agent.

Usage:
  stdio:  python3 -m gitd.mcp_server
  HTTP:   python3 -m gitd.mcp_server  (port 8002)
"""

import base64
import importlib
import json
import re
import subprocess
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gitd.bots.common.adb import Device, list_connected

mcp = FastMCP(
    "android-agent",
    stateless_http=True,
    json_response=True,
    host="127.0.0.1",
    port=8002,
    streamable_http_path="/mcp",
)


# ── Tier 1: Raw Android Control ──────────────────────────────────────────


@mcp.tool()
def list_devices() -> str:
    """List all connected Android devices with serial numbers and models.
    Call this first to get the device serial you need for other tools."""
    devices = list_connected()
    if not devices:
        return "No devices connected. Check USB cables and ADB authorization."
    result = []
    for serial in devices:
        try:
            model = Device(serial).adb("shell", "getprop", "ro.product.model", timeout=3).strip()
        except Exception:
            model = "unknown"
        result.append(f"{serial} ({model})")
    return "\n".join(result)


@mcp.tool()
def screenshot(device: str) -> str:
    """Take a screenshot of the device screen. Returns base64-encoded PNG.
    Use this to SEE what's on screen before deciding what to tap."""
    raw = subprocess.check_output(["adb", "-s", device, "exec-out", "screencap", "-p"], timeout=10)
    return base64.b64encode(raw).decode()


@mcp.tool()
def get_elements(device: str, interactive_only: bool = True) -> str:
    """Get all UI elements on the current screen as a JSON array.
    Each element has: idx, text, content_desc, resource_id, class, bounds, center, clickable, scrollable.
    Use element idx with tap_element(). Call this to understand the screen layout before acting."""
    dev = Device(device)
    xml = dev.dump_xml()
    if not xml:
        return "[]"

    elements = []
    for node in dev.nodes(xml):
        text = dev.node_text(node) or ""
        desc = dev.node_content_desc(node) or ""
        rid = dev.node_rid(node) or ""
        cls_m = re.search(r'class="([^"]*)"', node)
        cls = cls_m.group(1).split(".")[-1] if cls_m else ""
        clickable = 'clickable="true"' in node
        scrollable = 'scrollable="true"' in node

        if interactive_only and not clickable and not scrollable and not text and not desc:
            continue

        bounds = dev.node_bounds(node)
        if not bounds:
            continue
        x1, y1, x2, y2 = bounds
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2

        elements.append(
            {
                "idx": len(elements),
                "text": text,
                "content_desc": desc,
                "resource_id": rid.split("/")[-1] if "/" in rid else rid,
                "class": cls,
                "bounds": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
                "center": {"x": cx, "y": cy},
                "clickable": clickable,
                "scrollable": scrollable,
            }
        )

    return json.dumps(elements, indent=2)


@mcp.tool()
def tap(device: str, x: int, y: int) -> str:
    """Tap at exact pixel coordinates (x, y) on the device screen."""
    Device(device).tap(x, y)
    return f"Tapped ({x}, {y})"


@mcp.tool()
def tap_element(device: str, idx: int) -> str:
    """Tap a UI element by its index from get_elements().
    Call get_elements() first to see what's on screen and get element indices."""
    dev = Device(device)
    xml = dev.dump_xml()
    if not xml:
        return "Error: could not dump UI"

    elements = []
    for node in dev.nodes(xml):
        text = dev.node_text(node) or ""
        desc = dev.node_content_desc(node) or ""
        clickable = 'clickable="true"' in node
        scrollable = 'scrollable="true"' in node
        if not clickable and not scrollable and not text and not desc:
            continue
        bounds = dev.node_bounds(node)
        if not bounds:
            continue
        elements.append({"node": node, "bounds": bounds})

    if idx < 0 or idx >= len(elements):
        return f"Error: element idx {idx} out of range (0-{len(elements) - 1})"

    x1, y1, x2, y2 = elements[idx]["bounds"]
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    dev.tap(cx, cy)
    return f"Tapped element #{idx} at ({cx}, {cy})"


@mcp.tool()
def swipe(device: str, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 500) -> str:
    """Swipe from (x1,y1) to (x2,y2). Use for scrolling, pulling down notifications, etc.
    Common patterns: scroll down = swipe(dev, 540, 1400, 540, 600)
                     scroll up   = swipe(dev, 540, 600, 540, 1400)"""
    Device(device).swipe(x1, y1, x2, y2, ms=duration_ms)
    return f"Swiped ({x1},{y1}) -> ({x2},{y2}) in {duration_ms}ms"


@mcp.tool()
def type_text(device: str, text: str) -> str:
    """Type ASCII text into the currently focused input field.
    Tap an input field first to focus it. Spaces are supported.
    For emoji/unicode, use type_unicode() instead."""
    Device(device).adb("shell", "input", "text", text.replace(" ", "%s"))
    return f"Typed: {text}"


@mcp.tool()
def type_unicode(device: str, text: str) -> str:
    """Type unicode text (emoji, CJK, accented chars) via ADBKeyboard broadcast.
    Requires ADBKeyboard APK installed. Use type_text() for plain ASCII."""
    Device(device).type_unicode(text)
    return f"Typed (unicode): {text}"


@mcp.tool()
def press_back(device: str) -> str:
    """Press the Android Back button."""
    Device(device).back()
    return "Pressed Back"


@mcp.tool()
def press_home(device: str) -> str:
    """Press the Android Home button. Returns to home screen."""
    Device(device).adb("shell", "input", "keyevent", "KEYCODE_HOME")
    return "Pressed Home"


@mcp.tool()
def press_key(device: str, key: str) -> str:
    """Send a key event. key examples: POWER, VOLUME_UP, VOLUME_DOWN, ENTER, TAB, MENU.
    Full list: KEYCODE_ prefix is added automatically if missing."""
    if not key.startswith("KEYCODE_"):
        key = "KEYCODE_" + key
    Device(device).adb("shell", "input", "keyevent", key)
    return f"Sent {key}"


@mcp.tool()
def launch_app(device: str, package: str) -> str:
    """Launch an Android app by package name. Use search_apps() to find the package name."""
    Device(device).adb("shell", "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1")
    return f"Launched {package}"


@mcp.tool()
def search_apps(device: str, query: str) -> str:
    """Search installed apps by name. Case-insensitive. Returns matching apps with package names.
    Example: search_apps('tiktok') → [{"name": "TikTok", "package": "com.zhiliaoapp.musically"}]"""
    from gitd.services.agent_tools import execute_tool
    return execute_tool("search_apps", {"device": device, "query": query})


@mcp.tool()
def list_apps(device: str) -> str:
    """List all installed apps with human-readable names and package names.
    Returns [{name, package}] sorted alphabetically. Use search_apps() for faster lookup."""
    from gitd.services.agent_tools import execute_tool
    return execute_tool("list_apps", {"device": device})


@mcp.tool()
def long_press(device: str, x: int, y: int, duration_ms: int = 1000) -> str:
    """Long press at coordinates. Use for context menus, drag initiation, etc."""
    Device(device).long_press(x, y, duration_ms=duration_ms)
    return f"Long pressed ({x}, {y}) for {duration_ms}ms"


@mcp.tool()
def get_phone_state(device: str) -> str:
    """Get current app, activity, keyboard state, and focused element.
    Quick way to check what app/screen the device is on without parsing full elements."""
    from gitd.services.device_context import get_phone_state as _get_state
    return json.dumps(_get_state(device), indent=2)


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
    """Get the raw UI XML dump from the device (uiautomator).
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
    return f"Clipboard set" if _set(device, text) else "Failed"


@mcp.tool()
def get_notifications(device: str) -> str:
    """Get active notifications. Returns JSON array of {package, title, text}."""
    from gitd.services.device_context import get_notifications as _notif
    return json.dumps(_notif(device), indent=2)


@mcp.tool()
def open_notifications(device: str) -> str:
    """Pull down the notification shade."""
    from gitd.services.device_context import open_notifications as _open
    return "Notification shade opened" if _open(device) else "Failed"


@mcp.tool()
def launch_intent(device: str, action: str = "", data: str = "",
                  package: str = "", extras: str = "{}") -> str:
    """Launch a full Android intent. More powerful than launch_app().
    Examples:
      Open a URL: action="android.intent.action.VIEW" data="https://google.com"
      Open Settings: package="com.android.settings"
      Share text: action="android.intent.action.SEND" extras='{"android.intent.extra.TEXT": "hello"}'"""
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
def list_skills() -> str:
    """List all installed Android automation skills with their actions and workflows.
    Use this to discover what high-level automations are available.
    Prefer using run_workflow() over raw tap/swipe when a skill exists for the task."""
    import yaml

    skills_dir = Path(__file__).parent / "skills"
    result = []
    for d in sorted(skills_dir.iterdir()):
        meta_path = d / "skill.yaml"
        if d.is_dir() and meta_path.exists() and not d.name.startswith("__"):
            meta = yaml.safe_load(meta_path.read_text()) or {}
            info = {
                "name": meta.get("name", d.name),
                "app_package": meta.get("app_package"),
                "description": meta.get("description", ""),
            }
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
    parsed_params = json.loads(params)
    runner = Path(__file__).parent / "skills" / "_run_skill.py"
    result = subprocess.run(
        [
            "python3",
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
    parsed_params = json.loads(params)
    runner = Path(__file__).parent / "skills" / "_run_skill.py"
    result = subprocess.run(
        [
            "python3",
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


# ── Tier 3: Meta / Discovery ────────────────────────────────────────────


@mcp.tool()
def explore_app(device: str, package: str, max_depth: int = 2, max_states: int = 10) -> str:
    """Explore an Android app's UI autonomously using BFS.
    Launches the app, taps every interactive element, builds a state graph.
    Returns JSON with discovered screens, elements, and transitions.
    Use this to understand an unfamiliar app before writing automation for it."""
    script = Path(__file__).parent / "skills" / "auto_creator.py"
    result = subprocess.run(
        [
            "python3",
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
    return f"Exploration finished. Output:\n{result.stdout[-1000:]}"


@mcp.tool()
def create_skill(name: str, app_package: str, steps: str) -> str:
    """Create a new reusable skill from a JSON list of recorded steps.

    steps is a JSON array like:
    [
      {"action": "launch", "package": "com.example.app", "description": "Open app"},
      {"action": "tap", "x": 540, "y": 1200, "description": "Tap button"},
      {"action": "type", "text": "hello", "description": "Type greeting"},
      {"action": "wait", "seconds": 2, "description": "Wait for load"}
    ]

    Supported actions: launch, tap (x,y or element_idx), type, swipe, back, home, wait.
    After creating, use run_workflow(dev, name, "recorded", params) to replay it."""
    import yaml

    parsed_steps = json.loads(steps)
    skill_dir = Path(__file__).parent / "skills" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "actions").mkdir(exist_ok=True)
    (skill_dir / "workflows").mkdir(exist_ok=True)

    meta = {
        "name": name,
        "version": "1.0.0",
        "app_package": app_package,
        "description": f"Auto-generated skill with {len(parsed_steps)} steps",
    }
    (skill_dir / "skill.yaml").write_text(yaml.dump(meta, default_flow_style=False))
    (skill_dir / "workflows" / "recorded.json").write_text(json.dumps(parsed_steps, indent=2))
    (skill_dir / "__init__.py").write_text(f'"""Skill: {name}"""\n')

    return f"Skill '{name}' created at skills/{name}/ with {len(parsed_steps)} steps"


def main():
    mcp.run()


if __name__ == "__main__":
    main()
