"""Agent tool definitions — maps tool names to device_context functions.

Used by the agent chat service to execute LLM tool calls.
Tool schemas are in Anthropic's tool format and auto-converted for other providers.
"""

import json

from gitd.services import device_context as ctx
from gitd.bots.common.device import get_device, is_ios_ref
from gitd.skills.platforms import skill_platform_error_text, skill_supports_device
from gitd.services.tool_platforms import platform_error_text, supports_platform

# ── Tool registry ────────────────────────────────────────────────────────────

TOOLS = [
    # Screen reading
    {
        "name": "screenshot",
        "description": "Take a screenshot of the device screen. Returns base64 JPEG. Use this to SEE what's on screen.",
        "input_schema": {"type": "object", "properties": {"device": {"type": "string"}}, "required": ["device"]},
    },
    {
        "name": "screenshot_annotated",
        "description": "Screenshot with numbered element labels overlaid. Numbers match get_elements indices.",
        "input_schema": {"type": "object", "properties": {"device": {"type": "string"}}, "required": ["device"]},
    },
    {
        "name": "screenshot_cropped",
        "description": "Screenshot a specific screen region. Use to zoom into an area.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device": {"type": "string"},
                "x1": {"type": "integer"},
                "y1": {"type": "integer"},
                "x2": {"type": "integer"},
                "y2": {"type": "integer"},
            },
            "required": ["device", "x1", "y1", "x2", "y2"],
        },
    },
    {
        "name": "get_screen_tree",
        "description": 'Get LLM-readable indented UI hierarchy. Each node: [idx] Class "label" [clickable] [bounds]. Use this to understand screen layout before acting.',
        "input_schema": {"type": "object", "properties": {"device": {"type": "string"}}, "required": ["device"]},
    },
    {
        "name": "get_elements",
        "description": "Get interactive UI elements as JSON with idx, text, bounds, center. Use idx with tap_element.",
        "input_schema": {"type": "object", "properties": {"device": {"type": "string"}}, "required": ["device"]},
    },
    {
        "name": "get_phone_state",
        "description": "Get current app, activity, keyboard state. Quick check what's on screen.",
        "input_schema": {"type": "object", "properties": {"device": {"type": "string"}}, "required": ["device"]},
    },
    {
        "name": "classify_screen",
        "description": "Classify screen type: home, search, profile, dialog, error, loading.",
        "input_schema": {"type": "object", "properties": {"device": {"type": "string"}}, "required": ["device"]},
    },
    {
        "name": "find_on_screen",
        "description": "Find specific text on screen, return its location. Searches XML first, OCR fallback.",
        "input_schema": {
            "type": "object",
            "properties": {"device": {"type": "string"}, "text": {"type": "string"}},
            "required": ["device", "text"],
        },
    },
    {
        "name": "ocr_screen",
        "description": "OCR the entire screen. Use when UI elements are rendered as images (analytics, games, WebViews).",
        "input_schema": {"type": "object", "properties": {"device": {"type": "string"}}, "required": ["device"]},
    },
    {
        "name": "ocr_region",
        "description": "OCR a specific screen region. More accurate for targeted text extraction.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device": {"type": "string"},
                "x1": {"type": "integer"},
                "y1": {"type": "integer"},
                "x2": {"type": "integer"},
                "y2": {"type": "integer"},
            },
            "required": ["device", "x1", "y1", "x2", "y2"],
        },
    },
    # Input
    {
        "name": "tap",
        "description": "Tap at exact pixel coordinates (x, y) on the device screen.",
        "input_schema": {
            "type": "object",
            "properties": {"device": {"type": "string"}, "x": {"type": "integer"}, "y": {"type": "integer"}},
            "required": ["device", "x", "y"],
        },
    },
    {
        "name": "tap_element",
        "description": "Tap a UI element by its index from get_elements(). Call get_elements first.",
        "input_schema": {
            "type": "object",
            "properties": {"device": {"type": "string"}, "idx": {"type": "integer"}},
            "required": ["device", "idx"],
        },
    },
    {
        "name": "swipe",
        "description": "Swipe from (x1,y1) to (x2,y2). Scroll down: swipe(540,1400,540,600).",
        "input_schema": {
            "type": "object",
            "properties": {
                "device": {"type": "string"},
                "x1": {"type": "integer"},
                "y1": {"type": "integer"},
                "x2": {"type": "integer"},
                "y2": {"type": "integer"},
                "duration_ms": {"type": "integer", "default": 500},
            },
            "required": ["device", "x1", "y1", "x2", "y2"],
        },
    },
    {
        "name": "type_text",
        "description": "Type text into the currently focused input field.",
        "input_schema": {
            "type": "object",
            "properties": {"device": {"type": "string"}, "text": {"type": "string"}},
            "required": ["device", "text"],
        },
    },
    {
        "name": "press_key",
        "description": "Press a key: BACK, HOME, ENTER, TAB, POWER, VOLUME_UP, VOLUME_DOWN, APP_SWITCH.",
        "input_schema": {
            "type": "object",
            "properties": {"device": {"type": "string"}, "key": {"type": "string"}},
            "required": ["device", "key"],
        },
    },
    {
        "name": "long_press",
        "description": "Long press at coordinates. For context menus, drag initiation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device": {"type": "string"},
                "x": {"type": "integer"},
                "y": {"type": "integer"},
                "duration_ms": {"type": "integer", "default": 1000},
            },
            "required": ["device", "x", "y"],
        },
    },
    # App management
    {
        "name": "launch_app",
        "description": (
            "Launch an app by package name. E.g. com.zhiliaoapp.musically (TikTok). "
            "Use search_apps to find the package name. "
            "Set fresh=true to force-stop first (cold start, clears state — use for benchmarks "
            "or when prior app state would interfere). Default is warm start (resumes prior state)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "device": {"type": "string"},
                "package": {"type": "string"},
                "fresh": {"type": "boolean", "description": "Force-stop first for a clean state. Default false."},
            },
            "required": ["device", "package"],
        },
    },
    {
        "name": "open_camera",
        "description": (
            "Open the camera in a specific mode using standard Android intents. "
            "Works on any device — no need to know the camera package name. "
            "Modes: 'photo' (default rear photo), 'video' (rear video), "
            "'selfie' (front photo), 'selfie_video' (front video). "
            "Set timer_s=3 or timer_s=10 to activate the self-timer."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "device": {"type": "string"},
                "mode": {"type": "string", "enum": ["photo", "video", "selfie", "selfie_video"], "default": "photo"},
                "timer_s": {
                    "type": "integer",
                    "enum": [0, 3, 10],
                    "description": "Self-timer delay. 0 = off.",
                    "default": 0,
                },
            },
            "required": ["device"],
        },
    },
    {
        "name": "speak_text",
        "description": (
            "Make the phone speak text aloud using its built-in TTS engine. "
            "Works from PC and on-device — always emits audio on the phone. "
            "Requires Ghost portal app to be running. "
            "Use for audio feedback, accessibility, or voice responses."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "device": {"type": "string"},
                "text": {"type": "string", "description": "Text to speak aloud."},
                "rate": {
                    "type": "number",
                    "description": "Speed: 0.5=slow, 1.0=normal, 1.5=fast. Default 1.0.",
                    "default": 1.0,
                },
            },
            "required": ["device", "text"],
        },
    },
    {
        "name": "force_stop",
        "description": "Force-stop an app.",
        "input_schema": {
            "type": "object",
            "properties": {"device": {"type": "string"}, "package": {"type": "string"}},
            "required": ["device", "package"],
        },
    },
    {
        "name": "list_apps",
        "description": "List installed apps with human-readable names and Android package names or iOS bundle ids. Returns [{name, package}]. Use search_apps for faster lookup.",
        "input_schema": {"type": "object", "properties": {"device": {"type": "string"}}, "required": ["device"]},
    },
    {
        "name": "search_apps",
        "description": "Search installed apps by name. Returns Android package names or iOS bundle ids. Case-insensitive.",
        "input_schema": {
            "type": "object",
            "properties": {"device": {"type": "string"}, "query": {"type": "string"}},
            "required": ["device", "query"],
        },
    },
    {
        "name": "list_packages",
        "description": "List raw package names (no app names). Use list_apps or search_apps instead.",
        "input_schema": {"type": "object", "properties": {"device": {"type": "string"}}, "required": ["device"]},
    },
    {
        "name": "web_search",
        "description": (
            "Open a web search in the best available browser. "
            "Use when the user asks to search/look up something — faster than launching Chrome "
            "and typing into the address bar. Falls back through Chrome → Firefox → Samsung "
            "Internet → Edge → Brave → … → system default if a specific browser isn't installed. "
            "Engines: 'google' (default), 'ddg', 'bing', 'brave'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "device": {"type": "string"},
                "query": {"type": "string"},
                "engine": {"type": "string", "description": "Search engine: google, ddg, bing, brave. Default google."},
                "bundle_id": {"type": "string", "description": "Optional iOS browser bundle id override."},
            },
            "required": ["device", "query"],
        },
    },
    {
        "name": "open_url",
        "description": "Open a URL in the platform browser. On iOS, uses Appium/WDA and the configured browser bundle id.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device": {"type": "string"},
                "url": {"type": "string"},
                "bundle_id": {"type": "string", "description": "Optional iOS browser bundle id override."},
            },
            "required": ["device", "url"],
        },
    },
    {
        "name": "browser_back",
        "description": "Navigate back in the current browser/app context.",
        "input_schema": {"type": "object", "properties": {"device": {"type": "string"}}, "required": ["device"]},
    },
    {
        "name": "get_current_url",
        "description": "Get the current browser URL when the platform exposes it.",
        "input_schema": {"type": "object", "properties": {"device": {"type": "string"}}, "required": ["device"]},
    },
    {
        "name": "wait_for_text",
        "description": "Wait until text appears on screen and return visible text context.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device": {"type": "string"},
                "text": {"type": "string"},
                "timeout": {"type": "number", "default": 12.0},
            },
            "required": ["device", "text"],
        },
    },
    {
        "name": "extract_visible_text",
        "description": "Extract visible text from the current screen. Browser controls are filtered by default.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device": {"type": "string"},
                "max_lines": {"type": "integer", "default": 200},
                "include_controls": {"type": "boolean", "default": False},
            },
            "required": ["device"],
        },
    },
    {
        "name": "extract_articles",
        "description": "Extract likely visible article/headline candidates from the current browser page.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device": {"type": "string"},
                "max_items": {"type": "integer", "default": 5},
            },
            "required": ["device"],
        },
    },
    # Shell
    {
        "name": "shell",
        "description": "Run an ADB shell command. Returns stdout. E.g. shell('ls /sdcard/').",
        "input_schema": {
            "type": "object",
            "properties": {"device": {"type": "string"}, "command": {"type": "string"}},
            "required": ["device", "command"],
        },
    },
    # Clipboard & notifications
    {
        "name": "paste_text",
        "description": (
            "Set clipboard and paste into the currently focused input field in one call. "
            "Tap the target field first, then call this. "
            "Prefer this over type_text for long text, passwords, or special characters."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "device": {"type": "string"},
                "text": {"type": "string"},
            },
            "required": ["device", "text"],
        },
    },
    {
        "name": "clipboard_get",
        "description": "Get current clipboard text.",
        "input_schema": {"type": "object", "properties": {"device": {"type": "string"}}, "required": ["device"]},
    },
    {
        "name": "clipboard_set",
        "description": "Set clipboard text.",
        "input_schema": {
            "type": "object",
            "properties": {"device": {"type": "string"}, "text": {"type": "string"}},
            "required": ["device", "text"],
        },
    },
    {
        "name": "get_notifications",
        "description": "List active notifications.",
        "input_schema": {"type": "object", "properties": {"device": {"type": "string"}}, "required": ["device"]},
    },
    {
        "name": "open_notifications",
        "description": "Open the platform notification shade or Notification Center.",
        "input_schema": {"type": "object", "properties": {"device": {"type": "string"}}, "required": ["device"]},
    },
    {
        "name": "clear_notifications",
        "description": "Dismiss visible notifications when the platform exposes a clear control.",
        "input_schema": {"type": "object", "properties": {"device": {"type": "string"}}, "required": ["device"]},
    },
    # Skills
    {
        "name": "list_skills",
        "description": "List installed automation skills with actions and workflows.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device": {"type": "string", "description": "Optional device ref used to include platform support flags."},
                "supported_only": {"type": "boolean", "default": False},
            },
        },
    },
    {
        "name": "run_skill",
        "description": "Run a skill workflow. Call list_skills first to see available workflows.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device": {"type": "string"},
                "skill": {"type": "string"},
                "workflow": {"type": "string"},
                "params": {"type": "object", "default": {}},
            },
            "required": ["device", "skill", "workflow"],
        },
    },
    # System
    {
        "name": "wait",
        "description": "Pause execution for N seconds.",
        "input_schema": {
            "type": "object",
            "properties": {"seconds": {"type": "number", "default": 2}},
            "required": ["seconds"],
        },
    },
]


# ── Tool execution ───────────────────────────────────────────────────────────

_KNOWN_TOOL_NAMES = {tool["name"] for tool in TOOLS}
_UI_ACTION_TOOLS = {
    "tap",
    "tap_element",
    "swipe",
    "type_text",
    "press_key",
    "long_press",
    "launch_app",
    "open_url",
    "web_search",
    "browser_back",
    "wait_for_text",
}


def _ios_unsupported(tool_name: str) -> str:
    return platform_error_text(tool_name, "ios")


def tools_for_device(device: str | None) -> list[dict]:
    """Return the tools that should be offered to an agent for this device."""
    if not device:
        return list(TOOLS)
    platform = "ios" if is_ios_ref(device) else "android"
    return [tool for tool in TOOLS if supports_platform(tool["name"], platform)]


def tool_prompt_list(tools: list[dict]) -> str:
    """Compact tool list for text-only providers."""
    return "\n".join(
        f"- {t['name']}: {t['description']}  params: {list(t.get('input_schema', {}).get('properties', {}).keys())}"
        for t in tools
    )


def execute_tool(name: str, args: dict) -> str:
    """Execute a tool call and return result as string.
    UI actions auto-append the screen tree so the agent sees the result immediately."""
    result = _execute_tool_inner(name, args)
    # Auto-append screen tree after UI actions
    if name in _UI_ACTION_TOOLS and args.get("device"):
        try:
            import time as _t

            _t.sleep(0.5)
            tree = ctx.get_screen_tree(args["device"])
            if tree and tree != "(empty screen)":
                result += f"\n\n[Screen after action]\n{tree}"
        except Exception:
            pass
    return result


def _execute_tool_inner(name: str, args: dict) -> str:
    import subprocess
    import time

    from gitd.bots.common.adb import Device

    device = args.get("device", "")

    try:
        if name not in _KNOWN_TOOL_NAMES:
            return f"Unknown tool: {name}"
        if is_ios_ref(device) and not supports_platform(name, "ios"):
            return _ios_unsupported(name)

        if name == "screenshot":
            r = ctx.screenshot(device)
            return json.dumps(
                {"image": r["image"][:100] + "...(truncated)", "width": r["width"], "height": r["height"]}
            )
        elif name == "screenshot_annotated":
            r = ctx.screenshot_annotated(device)
            return json.dumps(
                {"image": r["image"][:100] + "...(truncated)", "width": r["width"], "height": r["height"]}
            )
        elif name == "screenshot_cropped":
            r = ctx.screenshot_cropped(device, args["x1"], args["y1"], args["x2"], args["y2"])
            return json.dumps(
                {"image": r["image"][:100] + "...(truncated)", "width": r["width"], "height": r["height"]}
            )
        elif name == "get_screen_tree":
            return ctx.get_screen_tree(device)
        elif name == "get_elements":
            return json.dumps(ctx.get_interactive_elements(device), indent=2)
        elif name == "get_phone_state":
            return json.dumps(ctx.get_phone_state(device), indent=2)
        elif name == "classify_screen":
            return json.dumps(ctx.classify_screen(device), indent=2)
        elif name == "find_on_screen":
            r = ctx.find_on_screen(device, args["text"])
            return json.dumps(r) if r else "Not found on screen"
        elif name == "ocr_screen":
            return json.dumps(ctx.ocr_screen(device), indent=2)
        elif name == "ocr_region":
            return json.dumps(ctx.ocr_region(device, args["x1"], args["y1"], args["x2"], args["y2"]), indent=2)
        elif name == "tap":
            get_device(device).tap(args["x"], args["y"])
            return f"Tapped ({args['x']}, {args['y']})"
        elif name == "tap_element":
            elements = ctx.get_interactive_elements(device)
            idx = args["idx"]
            if 0 <= idx < len(elements):
                el = elements[idx]
                cx, cy = el["center"]["x"], el["center"]["y"]
                get_device(device).tap(cx, cy)
                return f"Tapped element #{idx} '{el.get('text') or el.get('content_desc') or el.get('resource_id', '')}' at ({cx}, {cy})"
            return f"Element index {idx} out of range (0-{len(elements) - 1})"
        elif name == "swipe":
            get_device(device).swipe(args["x1"], args["y1"], args["x2"], args["y2"], ms=args.get("duration_ms", 500))
            return f"Swiped ({args['x1']},{args['y1']}) -> ({args['x2']},{args['y2']})"
        elif name == "type_text":
            if is_ios_ref(device):
                get_device(device).type_text(args["text"])
            else:
                Device(device).adb("shell", "input", "text", args["text"].replace(" ", "%s"))
            return f"Typed: {args['text']}"
        elif name == "press_key":
            key = args["key"]
            if is_ios_ref(device):
                get_device(device).press_key(key)
            elif not key.startswith("KEYCODE_"):
                key = "KEYCODE_" + key
                Device(device).adb("shell", "input", "keyevent", key)
            else:
                Device(device).adb("shell", "input", "keyevent", key)
            return f"Pressed {key}"
        elif name == "long_press":
            get_device(device).long_press(args["x"], args["y"], duration_ms=args.get("duration_ms", 1000))
            return f"Long pressed ({args['x']}, {args['y']})"
        elif name == "launch_app":
            if is_ios_ref(device):
                bundle_id = args["package"]
                if bool(args.get("fresh", False)):
                    try:
                        get_device(device).terminate_app(bundle_id)
                    except Exception:
                        pass
                get_device(device).launch_app(bundle_id)
                return f"Launched iOS app {bundle_id}" + (" [fresh]" if args.get("fresh", False) else "")
            dev = Device(device)
            pkg = args["package"]
            fresh = bool(args.get("fresh", False))
            # Verify the package exists first — `monkey`/`am start` both fall
            # through silently for missing packages, so without this the agent
            # gets a phantom success and burns turns wondering why the app
            # didn't open.
            installed = dev.adb("shell", "pm", "list", "packages", pkg, timeout=10)
            if f"package:{pkg}" not in installed:
                pkgs_out = dev.adb("shell", "pm", "list", "packages", timeout=10)
                all_pkgs = [
                    p.replace("package:", "").strip() for p in pkgs_out.splitlines() if p.startswith("package:")
                ]
                # Suggest installed packages whose name contains a token from the
                # requested one — usually catches `com.reddit.android` →
                # `com.reddit.frontpage`.
                tokens = [t for t in pkg.split(".") if len(t) > 2 and t not in {"com", "org", "net", "android", "app"}]
                hits = [p for p in all_pkgs if any(t in p for t in tokens)][:6]
                hint = f" Did you mean: {', '.join(hits)}?" if hits else ""
                return f"ERROR: package {pkg} is not installed.{hint}"
            # Check if the package is disabled — `pm list packages -d` lists disabled
            # packages. All launch methods silently fail (or "No activities found") when
            # the package is disabled, giving the agent a phantom success.
            disabled = dev.adb("shell", "pm", "list", "packages", "-d", pkg, timeout=10)
            if f"package:{pkg}" in disabled:
                return f"ERROR: {pkg} is installed but disabled. Enable it first: adb shell pm enable {pkg}"
            # When the daemon runs ON the phone (Chaquopy), `am start` and
            # `monkey` both fail under the app's own uid: am resolves to
            # USER_CURRENT_OR_SELF and gets blocked on INTERACT_ACROSS_USERS_FULL,
            # monkey aborts setting a system property. Going through the app
            # process's own Context.startActivity() works because it's a
            # public Android surface — same path any third-party launcher
            # uses. The Kotlin helper `DeviceActions.launchApp` lives at
            # app/src/main/java/com/ghostinthedroid/app/ondevice/DeviceActions.kt.
            # Outside Chaquopy (host-side dev runs), fall back to the adb
            # `am start` path, which works because host adb runs as `shell`
            # (uid 2000) and has the cross-user permission.
            try:
                from java import jclass  # type: ignore[import-not-found]

                actions = jclass("com.ghostinthedroid.app.ondevice.DeviceActions").INSTANCE
                return str(actions.launchApp(pkg, fresh))
            except Exception:
                # Host-side fallback (no Chaquopy): use am start through ADB.
                resolve = dev.adb(
                    "shell",
                    "cmd",
                    "package",
                    "resolve-activity",
                    "--brief",
                    "-c",
                    "android.intent.category.LAUNCHER",
                    pkg,
                    timeout=10,
                )
                launcher = ""
                for line in resolve.splitlines():
                    line = line.strip()
                    if "/" in line and line.startswith(pkg):
                        launcher = line
                        break
                if not launcher:
                    # resolve-activity can fail on some ROMs (ASUS, Samsung) even for
                    # valid launcher packages. Fall back to monkey which works as long
                    # as the package is enabled and has a LAUNCHER activity.
                    if fresh:
                        dev.adb("shell", "am", "force-stop", pkg)
                    monkey_out = dev.adb(
                        "shell",
                        "monkey",
                        "-p",
                        pkg,
                        "-c",
                        "android.intent.category.LAUNCHER",
                        "1",
                        timeout=10,
                    )
                    if "Events injected: 1" in monkey_out:
                        return f"Launched {pkg} (monkey)" + (" [fresh]" if fresh else "")
                    return f"ERROR: {pkg} has no LAUNCHER activity (monkey: {monkey_out.strip()[:100]})"
                am_args = ["shell", "am", "start", "--user", "0"]
                if fresh:
                    am_args += ["--activity-clear-task"]
                am_args += ["-n", launcher]
                out = dev.adb(*am_args, timeout=15)
                if "Error:" in out or "Activity not started" in out:
                    return f"ERROR launching {pkg}: {out.strip()[:200]}"
                return f"Launched {pkg} ({launcher})" + (" [fresh]" if fresh else "")
        elif name == "open_camera":
            if is_ios_ref(device):
                result = get_device(device).open_camera(
                    mode=args.get("mode", "photo"),
                    timer_s=int(args.get("timer_s", 0)),
                )
                warnings = []
                if not result.get("selected_mode"):
                    warnings.append("mode control not found")
                if result.get("switched_camera") is False:
                    warnings.append("front camera switch not found")
                if result.get("timer_set") is False:
                    warnings.append("timer control not found")
                suffix = f" ({'; '.join(warnings)})" if warnings else ""
                return f"Opened iOS Camera - {result['mode']}{suffix}"
            dev = Device(device)
            mode = args.get("mode", "photo").lower()
            timer_s = int(args.get("timer_s", 0))
            import time as _time

            _VIDEO_MODES = {"video", "selfie_video"}
            _FRONT_MODES = {"selfie", "selfie_video"}

            # Find installed camera package
            _CAMERA_PKGS = [
                "com.asus.camera",
                "com.sec.android.app.camera",
                "com.google.android.GoogleCamera",
                "com.android.camera2",
                "com.android.camera",
            ]
            camera_pkg = None
            for cpkg in _CAMERA_PKGS:
                if f"package:{cpkg}" in dev.adb("shell", "pm", "list", "packages", cpkg, timeout=5):
                    camera_pkg = cpkg
                    break
            if not camera_pkg:
                return "ERROR: no camera app found on device"

            # Wake screen if it's off — camera won't open on a sleeping display
            awake = dev.adb("shell", "dumpsys", "window", "displays", timeout=5)
            if "mAwake=false" in awake:
                dev.adb("shell", "input", "keyevent", "KEYCODE_WAKEUP")
                _time.sleep(0.5)
                # Dismiss any lock screen via swipe up
                dev.adb("shell", "input", "swipe", "540", "1600", "540", "800", "300")
                _time.sleep(0.5)

            # Always force-stop for clean state — avoids stale mode/timer from last session
            dev.adb("shell", "am", "force-stop", camera_pkg)
            _time.sleep(0.4)

            # Launch via LAUNCHER intent — same as tapping the icon.
            # DO NOT use IMAGE_CAPTURE/VIDEO_CAPTURE intents — those open a
            # "capture for app" flow that shows a Retake/Use dialog and saves
            # nothing to the gallery.
            launch_result = execute_tool("launch_app", {"device": device, "package": camera_pkg, "fresh": False})
            if "ERROR" in launch_result:
                return f"ERROR opening camera: {launch_result}"

            # Wait for camera UI to be ready
            _READY = {"button_capture", "take picture", "shutter", "capture"}
            _ERRORS = {"being used by another", "camera not ready"}
            for _ in range(10):  # up to 5s
                _time.sleep(0.5)
                xml = dev.dump_xml() or ""
                xml_lower = xml.lower()
                if any(ind in xml_lower for ind in _READY):
                    break
                if any(ind in xml_lower for ind in _ERRORS):
                    return "ERROR: camera busy — try again in a moment"
            else:
                return "ERROR: camera did not become ready in time"

            # Switch to front camera if needed
            if mode in _FRONT_MODES:
                xml = dev.dump_xml() or ""
                switched = False
                _FRONT_KEYWORDS = ("switch", "front", "toggle", "flip", "selfie", "btn_toggle")
                for node in dev.nodes(xml):
                    desc = (dev.node_content_desc(node) or "").lower()
                    text = (dev.node_text(node) or "").lower()
                    rid = (dev.node_rid(node) or "").lower()
                    if any(k in desc or k in text or k in rid for k in _FRONT_KEYWORDS):
                        b = dev.node_bounds(node)
                        if b and 'clickable="true"' in node:
                            dev.tap((b[0] + b[2]) // 2, (b[1] + b[3]) // 2)
                            _time.sleep(0.8)
                            switched = True
                            break
                if not switched:
                    return "ERROR: could not find front-camera switch button"

            # Switch to video mode if needed
            if mode in _VIDEO_MODES:
                xml = dev.dump_xml() or ""
                for node in dev.nodes(xml):
                    text = (dev.node_text(node) or "").lower()
                    desc = (dev.node_content_desc(node) or "").lower()
                    if text == "video" or desc == "video":
                        b = dev.node_bounds(node)
                        if b:
                            dev.tap((b[0] + b[2]) // 2, (b[1] + b[3]) // 2)
                            _time.sleep(0.6)
                            break

            mode_label = {
                "photo": "📷 photo",
                "video": "🎬 video",
                "selfie": "🤳 selfie",
                "selfie_video": "🤳🎬 selfie video",
            }.get(mode, mode)
            result = f"Opened camera — {mode_label}"

            # Timer: UI automation — not a native intent parameter.
            # Supported values differ by OEM: ASUS=3s/10s, Samsung=2s/5s/10s.
            # Pick the closest supported value and tap through the UI.
            if timer_s > 0:
                _time.sleep(1.0)
                # Snap to closest OEM-supported value
                _SUPPORTED = [2, 3, 5, 10]
                timer_s = min(_SUPPORTED, key=lambda v: abs(v - timer_s))

                def _find_timer_node(xml_str, secs):
                    """Search for a timer button matching `secs` seconds."""
                    targets = [
                        f"{secs}s",
                        f"{secs} s",
                        f"timer_{secs}s",  # Samsung: FRONT_TIMER_5S / REAR_TIMER_5S
                        f"_{secs}s",  # suffix match for TIMER_5S
                    ]
                    for node in dev.nodes(xml_str):
                        text = (dev.node_text(node) or "").lower()
                        desc = (dev.node_content_desc(node) or "").lower()
                        combined = text + " " + desc
                        if any(t in combined for t in targets):
                            return dev.node_bounds(node)
                    return None

                xml = dev.dump_xml() or ""
                bounds = _find_timer_node(xml, timer_s)

                if not bounds:
                    # Samsung pattern: timer is inside "Quick controls" panel.
                    # Step 1: tap "Quick controls" to expand.
                    for node in dev.nodes(xml):
                        desc = (dev.node_content_desc(node) or "").lower()
                        text = (dev.node_text(node) or "").lower()
                        if "quick control" in desc or "quick control" in text:
                            b = dev.node_bounds(node)
                            if b:
                                dev.tap((b[0] + b[2]) // 2, (b[1] + b[3]) // 2)
                                _time.sleep(0.6)
                                break
                    # Step 2: tap "Timer" entry to expand timer options.
                    xml = dev.dump_xml() or ""
                    for node in dev.nodes(xml):
                        desc = (dev.node_content_desc(node) or "").lower()
                        text = (dev.node_text(node) or "").lower()
                        if (desc == "timer" or text == "timer") and "off" not in desc:
                            b = dev.node_bounds(node)
                            if b:
                                dev.tap((b[0] + b[2]) // 2, (b[1] + b[3]) // 2)
                                _time.sleep(0.6)
                                break
                    # Step 3: now find the specific value.
                    xml = dev.dump_xml() or ""
                    bounds = _find_timer_node(xml, timer_s)

                if bounds:
                    dev.tap((bounds[0] + bounds[2]) // 2, (bounds[1] + bounds[3]) // 2)
                    _time.sleep(0.4)
                    # Close the Quick controls panel if it's still open (Samsung leaves it open).
                    # Press Back once to dismiss it without closing the camera.
                    xml_after = dev.dump_xml() or ""
                    for node in dev.nodes(xml_after):
                        desc = (dev.node_content_desc(node) or "").lower()
                        text_n = (dev.node_text(node) or "").lower()
                        if "close" in desc or "close" in text_n or "dismiss" in desc:
                            b = dev.node_bounds(node)
                            if b:
                                dev.tap((b[0] + b[2]) // 2, (b[1] + b[3]) // 2)
                                break
                    else:
                        # No close button found — tap outside the panel (top of screen)
                        dev.adb("shell", "input", "keyevent", "KEYCODE_BACK")
                    _time.sleep(0.3)
                    result += f" | ⏱ {timer_s}s timer set"
                else:
                    result += " | ⚠️ timer button not found (tap it manually)"

            return result
        elif name == "speak_text":
            from gitd.services.device_context import speak_text as _speak

            return _speak(device, args["text"], float(args.get("rate", 1.0)))
        elif name == "force_stop":
            if is_ios_ref(device):
                get_device(device).terminate_app(args["package"])
                return f"Stopped iOS app {args['package']}"
            Device(device).adb("shell", "am", "force-stop", args["package"])
            return f"Stopped {args['package']}"
        elif name == "web_search":
            if is_ios_ref(device):
                from gitd.services.browser import dumps, web_search as _web_search

                return dumps(
                    _web_search(
                        device,
                        args["query"],
                        engine=args.get("engine", "google"),
                        bundle_id=args.get("bundle_id") or None,
                    )
                )
            from gitd.services.web_search import open_search

            return open_search(device, args["query"], engine=args.get("engine", "google"))
        elif name == "open_url":
            from gitd.services.browser import dumps, open_url as _open_url

            return dumps(_open_url(device, args["url"], bundle_id=args.get("bundle_id") or None))
        elif name == "browser_back":
            from gitd.services.browser import dumps, browser_back as _browser_back

            return dumps(_browser_back(device))
        elif name == "get_current_url":
            from gitd.services.browser import dumps, get_current_url as _get_current_url

            return dumps(_get_current_url(device))
        elif name == "wait_for_text":
            from gitd.services.browser import dumps, wait_for_text as _wait_for_text

            return dumps(_wait_for_text(device, args["text"], timeout=float(args.get("timeout", 12.0))))
        elif name == "extract_visible_text":
            from gitd.services.browser import dumps, extract_visible_text as _extract_visible_text

            return dumps(
                _extract_visible_text(
                    device,
                    max_lines=int(args.get("max_lines", 200)),
                    include_controls=bool(args.get("include_controls", False)),
                )
            )
        elif name == "extract_articles":
            from gitd.services.browser import dumps, extract_articles as _extract_articles

            return dumps(_extract_articles(device, max_items=int(args.get("max_items", 5))))
        elif name == "list_apps" or name == "search_apps":
            if is_ios_ref(device):
                query = args.get("query", "") if name == "search_apps" else ""
                return json.dumps(get_device(device).list_apps(query=query), indent=2)
            out = Device(device).adb("shell", "pm", "list", "packages", timeout=10)
            pkgs = [p.replace("package:", "").strip() for p in out.splitlines() if p.startswith("package:")]
            # Known app names for common packages
            KNOWN = {
                "com.zhiliaoapp.musically": "TikTok",
                "com.instagram.android": "Instagram",
                "com.facebook.katana": "Facebook",
                "com.facebook.orca": "Messenger",
                "com.whatsapp": "WhatsApp",
                "com.twitter.android": "X (Twitter)",
                "com.snapchat.android": "Snapchat",
                "com.google.android.youtube": "YouTube",
                "com.google.android.apps.youtube.music": "YouTube Music",
                "com.google.android.apps.maps": "Google Maps",
                "com.google.android.gm": "Gmail",
                "com.google.android.apps.photos": "Google Photos",
                "com.google.android.apps.docs": "Google Drive",
                "com.android.chrome": "Chrome",
                "com.android.vending": "Play Store",
                "org.telegram.messenger": "Telegram",
                "com.discord": "Discord",
                "com.reddit.frontpage": "Reddit",
                "com.spotify.music": "Spotify",
                "com.amazon.mShop.android.shopping": "Amazon",
                "com.tinder": "Tinder",
                "com.bumble.app": "Bumble",
                "co.hinge.app": "Hinge",
                "com.nordvpn.android": "NordVPN",
                "com.anydesk.adcontrol.ad1": "AnyDesk",
                "com.google.android.calendar": "Calendar",
                "com.google.android.contacts": "Contacts",
                "com.google.android.dialer": "Phone",
                "com.android.camera": "Camera",
                "com.sec.android.app.camera": "Camera",
                "com.android.settings": "Settings",
                "com.android.calculator2": "Calculator",
                "com.android.deskclock": "Clock",
                "com.sec.android.gallery3d": "Gallery",
                "com.samsung.android.messaging": "Messages",
                "com.samsung.android.dialer": "Phone",
                "com.samsung.android.app.notes": "Samsung Notes",
            }
            apps = []
            for pkg in pkgs:
                name_guess = KNOWN.get(pkg, "")
                if not name_guess:
                    # Derive from package: com.example.myapp → myapp, capitalize
                    last = pkg.split(".")[-1]
                    name_guess = last.replace("_", " ").replace("-", " ").title()
                apps.append({"name": name_guess, "package": pkg})
            apps.sort(key=lambda a: a["name"].lower())
            if name == "search_apps":
                query = args.get("query", "").lower()
                apps = [a for a in apps if query in a["name"].lower() or query in a["package"].lower()]
            return json.dumps(apps, indent=2)
        elif name == "list_packages":
            if is_ios_ref(device):
                apps = get_device(device).list_apps()
                return json.dumps([app["bundle_id"] for app in apps][:50], indent=2)
            out = Device(device).adb("shell", "pm", "list", "packages", "-3", timeout=15)
            pkgs = [p.replace("package:", "").strip() for p in out.splitlines() if p.startswith("package:")]
            return json.dumps(pkgs[:50])
        elif name == "shell":
            out = Device(device).adb("shell", *args["command"].split(), timeout=15)
            return out[:3000]
        elif name == "paste_text":
            if is_ios_ref(device):
                get_device(device).paste_text(args["text"])
                t = args["text"]
                return f"Inserted text on iOS: {t[:60]}{'...' if len(t) > 60 else ''}"
            from gitd.bots.common.adb import Device as _Dev

            ctx.clipboard_set(device, args["text"])
            _Dev(device).adb("shell", "input", "keyevent", "KEYCODE_PASTE")
            t = args["text"]
            return f"Pasted: {t[:60]}{'…' if len(t) > 60 else ''}"
        elif name == "clipboard_get":
            return ctx.clipboard_get(device) or "(empty)"
        elif name == "clipboard_set":
            ctx.clipboard_set(device, args["text"])
            return "Clipboard set"
        elif name == "get_notifications":
            return json.dumps(ctx.get_notifications(device), indent=2)
        elif name == "open_notifications":
            return "Notification shade opened" if ctx.open_notifications(device) else "Failed"
        elif name == "clear_notifications":
            return "Notifications cleared" if ctx.clear_notifications(device) else "Failed"
        elif name == "list_skills":
            from gitd.routers.skills import _load_all_skills, _load_skill

            skills = _load_all_skills()
            result = []
            target_device = args.get("device") or device
            supported_only = bool(args.get("supported_only"))
            for sname, info in skills.items():
                supported = skill_supports_device(info.get("metadata") or {}, target_device) if target_device else None
                if supported_only and supported is False:
                    continue
                s = _load_skill(sname)
                entry = {
                    "name": info["name"],
                    "app_package": info.get("app_package", ""),
                    "android_package": info.get("android_package", ""),
                    "ios_bundle_id": info.get("ios_bundle_id", ""),
                    "platforms": info.get("platforms", []),
                    "supports_android": info.get("supports_android", False),
                    "supports_ios": info.get("supports_ios", False),
                }
                if supported is not None:
                    entry["supported_on_device"] = supported
                if s and not isinstance(s, dict):
                    entry["workflows"] = s.list_workflows()
                    entry["actions"] = s.list_actions()
                result.append(entry)
            return json.dumps(result, indent=2)
        elif name == "run_skill":
            from gitd.routers.skills import _load_all_skills

            skills = _load_all_skills()
            skill_info = skills.get(args["skill"])
            if skill_info and not skill_supports_device(skill_info.get("metadata") or {}, device):
                return skill_platform_error_text(args["skill"], skill_info.get("metadata") or {}, device)
            runner = __import__("pathlib").Path(__file__).parent.parent / "skills" / "_run_skill.py"
            params = json.dumps(args.get("params", {}))
            r = subprocess.run(
                [
                    "python3",
                    "-u",
                    str(runner),
                    "--skill",
                    args["skill"],
                    "--workflow",
                    args["workflow"],
                    "--device",
                    device,
                    "--params",
                    params,
                ],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(__import__("pathlib").Path(__file__).parent.parent.parent),
            )
            return r.stdout[-2000:] if r.returncode == 0 else f"FAILED: {r.stdout[-1000:]}\n{r.stderr[-500:]}"
        elif name == "wait":
            time.sleep(args.get("seconds", 2))
            return f"Waited {args.get('seconds', 2)}s"
        else:
            return f"Unknown tool: {name}"
    except Exception as e:
        return f"Error: {e}"

    # Auto-append screen tree after UI actions so agent sees result immediately
    if name in _UI_ACTION_TOOLS and device and isinstance(result, str):
        try:
            import time as _t

            _t.sleep(0.5)  # Brief settle time for UI to update
            tree = ctx.get_screen_tree(device)
            if tree and tree != "(empty screen)":
                result += f"\n\n[Screen after action]\n{tree}"
        except Exception:
            pass
    return result


def get_screenshot_b64(device: str) -> str | None:
    """Get raw base64 screenshot for vision context injection."""
    try:
        r = ctx.screenshot(device)
        return r.get("image")
    except Exception:
        return None
