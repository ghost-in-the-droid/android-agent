"""Agent tool definitions — maps tool names to device_context functions.

Used by the agent chat service to execute LLM tool calls.
Tool schemas are in Anthropic's tool format and auto-converted for other providers.
"""
import json
from gitd.services import device_context as ctx

# ── Tool registry ────────────────────────────────────────────────────────────

TOOLS = [
    # Screen reading
    {"name": "screenshot", "description": "Take a screenshot of the device screen. Returns base64 JPEG. Use this to SEE what's on screen.", "input_schema": {"type": "object", "properties": {"device": {"type": "string"}}, "required": ["device"]}},
    {"name": "screenshot_annotated", "description": "Screenshot with numbered element labels overlaid. Numbers match get_elements indices.", "input_schema": {"type": "object", "properties": {"device": {"type": "string"}}, "required": ["device"]}},
    {"name": "screenshot_cropped", "description": "Screenshot a specific screen region. Use to zoom into an area.", "input_schema": {"type": "object", "properties": {"device": {"type": "string"}, "x1": {"type": "integer"}, "y1": {"type": "integer"}, "x2": {"type": "integer"}, "y2": {"type": "integer"}}, "required": ["device", "x1", "y1", "x2", "y2"]}},
    {"name": "get_screen_tree", "description": "Get LLM-readable indented UI hierarchy. Each node: [idx] Class \"label\" [clickable] [bounds]. Use this to understand screen layout before acting.", "input_schema": {"type": "object", "properties": {"device": {"type": "string"}}, "required": ["device"]}},
    {"name": "get_elements", "description": "Get interactive UI elements as JSON with idx, text, bounds, center. Use idx with tap_element.", "input_schema": {"type": "object", "properties": {"device": {"type": "string"}}, "required": ["device"]}},
    {"name": "get_phone_state", "description": "Get current app, activity, keyboard state. Quick check what's on screen.", "input_schema": {"type": "object", "properties": {"device": {"type": "string"}}, "required": ["device"]}},
    {"name": "classify_screen", "description": "Classify screen type: home, search, profile, dialog, error, loading.", "input_schema": {"type": "object", "properties": {"device": {"type": "string"}}, "required": ["device"]}},
    {"name": "find_on_screen", "description": "Find specific text on screen, return its location. Searches XML first, OCR fallback.", "input_schema": {"type": "object", "properties": {"device": {"type": "string"}, "text": {"type": "string"}}, "required": ["device", "text"]}},
    {"name": "ocr_screen", "description": "OCR the entire screen. Use when UI elements are rendered as images (analytics, games, WebViews).", "input_schema": {"type": "object", "properties": {"device": {"type": "string"}}, "required": ["device"]}},
    {"name": "ocr_region", "description": "OCR a specific screen region. More accurate for targeted text extraction.", "input_schema": {"type": "object", "properties": {"device": {"type": "string"}, "x1": {"type": "integer"}, "y1": {"type": "integer"}, "x2": {"type": "integer"}, "y2": {"type": "integer"}}, "required": ["device", "x1", "y1", "x2", "y2"]}},
    # Input
    {"name": "tap", "description": "Tap at exact pixel coordinates (x, y) on the device screen.", "input_schema": {"type": "object", "properties": {"device": {"type": "string"}, "x": {"type": "integer"}, "y": {"type": "integer"}}, "required": ["device", "x", "y"]}},
    {"name": "tap_element", "description": "Tap a UI element by its index from get_elements(). Call get_elements first.", "input_schema": {"type": "object", "properties": {"device": {"type": "string"}, "idx": {"type": "integer"}}, "required": ["device", "idx"]}},
    {"name": "swipe", "description": "Swipe from (x1,y1) to (x2,y2). Scroll down: swipe(540,1400,540,600).", "input_schema": {"type": "object", "properties": {"device": {"type": "string"}, "x1": {"type": "integer"}, "y1": {"type": "integer"}, "x2": {"type": "integer"}, "y2": {"type": "integer"}, "duration_ms": {"type": "integer", "default": 500}}, "required": ["device", "x1", "y1", "x2", "y2"]}},
    {"name": "type_text", "description": "Type text into the currently focused input field.", "input_schema": {"type": "object", "properties": {"device": {"type": "string"}, "text": {"type": "string"}}, "required": ["device", "text"]}},
    {"name": "press_key", "description": "Press a key: BACK, HOME, ENTER, TAB, POWER, VOLUME_UP, VOLUME_DOWN, APP_SWITCH.", "input_schema": {"type": "object", "properties": {"device": {"type": "string"}, "key": {"type": "string"}}, "required": ["device", "key"]}},
    {"name": "long_press", "description": "Long press at coordinates. For context menus, drag initiation.", "input_schema": {"type": "object", "properties": {"device": {"type": "string"}, "x": {"type": "integer"}, "y": {"type": "integer"}, "duration_ms": {"type": "integer", "default": 1000}}, "required": ["device", "x", "y"]}},
    # App management
    {"name": "launch_app", "description": "Launch an app by package name. E.g. com.zhiliaoapp.musically (TikTok). Use search_apps to find the package name.", "input_schema": {"type": "object", "properties": {"device": {"type": "string"}, "package": {"type": "string"}}, "required": ["device", "package"]}},
    {"name": "force_stop", "description": "Force-stop an app.", "input_schema": {"type": "object", "properties": {"device": {"type": "string"}, "package": {"type": "string"}}, "required": ["device", "package"]}},
    {"name": "list_apps", "description": "List installed apps with human-readable names and package names. Returns [{name, package}]. Use search_apps for faster lookup.", "input_schema": {"type": "object", "properties": {"device": {"type": "string"}}, "required": ["device"]}},
    {"name": "search_apps", "description": "Search installed apps by name. E.g. search_apps('tiktok') returns matching apps with package names. Case-insensitive.", "input_schema": {"type": "object", "properties": {"device": {"type": "string"}, "query": {"type": "string"}}, "required": ["device", "query"]}},
    {"name": "list_packages", "description": "List raw package names (no app names). Use list_apps or search_apps instead.", "input_schema": {"type": "object", "properties": {"device": {"type": "string"}}, "required": ["device"]}},
    # Shell
    {"name": "shell", "description": "Run an ADB shell command. Returns stdout. E.g. shell('ls /sdcard/').", "input_schema": {"type": "object", "properties": {"device": {"type": "string"}, "command": {"type": "string"}}, "required": ["device", "command"]}},
    # Clipboard & notifications
    {"name": "clipboard_get", "description": "Get current clipboard text.", "input_schema": {"type": "object", "properties": {"device": {"type": "string"}}, "required": ["device"]}},
    {"name": "clipboard_set", "description": "Set clipboard text.", "input_schema": {"type": "object", "properties": {"device": {"type": "string"}, "text": {"type": "string"}}, "required": ["device", "text"]}},
    {"name": "get_notifications", "description": "List active notifications.", "input_schema": {"type": "object", "properties": {"device": {"type": "string"}}, "required": ["device"]}},
    # Skills
    {"name": "list_skills", "description": "List installed automation skills with actions and workflows.", "input_schema": {"type": "object", "properties": {}}},
    {"name": "run_skill", "description": "Run a skill workflow. Call list_skills first to see available workflows.", "input_schema": {"type": "object", "properties": {"device": {"type": "string"}, "skill": {"type": "string"}, "workflow": {"type": "string"}, "params": {"type": "object", "default": {}}}, "required": ["device", "skill", "workflow"]}},
    # System
    {"name": "wait", "description": "Pause execution for N seconds.", "input_schema": {"type": "object", "properties": {"seconds": {"type": "number", "default": 2}}, "required": ["seconds"]}},
]


# ── Tool execution ───────────────────────────────────────────────────────────

def execute_tool(name: str, args: dict) -> str:
    """Execute a tool call and return result as string."""
    import time
    import subprocess
    from gitd.bots.common.adb import Device

    device = args.get("device", "")

    try:
        if name == "screenshot":
            r = ctx.screenshot(device)
            return json.dumps({"image": r["image"][:100] + "...(truncated)", "width": r["width"], "height": r["height"]})
        elif name == "screenshot_annotated":
            r = ctx.screenshot_annotated(device)
            return json.dumps({"image": r["image"][:100] + "...(truncated)", "width": r["width"], "height": r["height"]})
        elif name == "screenshot_cropped":
            r = ctx.screenshot_cropped(device, args["x1"], args["y1"], args["x2"], args["y2"])
            return json.dumps({"image": r["image"][:100] + "...(truncated)", "width": r["width"], "height": r["height"]})
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
            Device(device).tap(args["x"], args["y"])
            return f"Tapped ({args['x']}, {args['y']})"
        elif name == "tap_element":
            elements = ctx.get_interactive_elements(device)
            idx = args["idx"]
            if 0 <= idx < len(elements):
                el = elements[idx]
                cx, cy = el["center"]["x"], el["center"]["y"]
                Device(device).tap(cx, cy)
                return f"Tapped element #{idx} '{el.get('text') or el.get('content_desc') or el.get('resource_id', '')}' at ({cx}, {cy})"
            return f"Element index {idx} out of range (0-{len(elements)-1})"
        elif name == "swipe":
            Device(device).swipe(args["x1"], args["y1"], args["x2"], args["y2"], ms=args.get("duration_ms", 500))
            return f"Swiped ({args['x1']},{args['y1']}) -> ({args['x2']},{args['y2']})"
        elif name == "type_text":
            Device(device).adb("shell", "input", "text", args["text"].replace(" ", "%s"))
            return f"Typed: {args['text']}"
        elif name == "press_key":
            key = args["key"]
            if not key.startswith("KEYCODE_"):
                key = "KEYCODE_" + key
            Device(device).adb("shell", "input", "keyevent", key)
            return f"Pressed {key}"
        elif name == "long_press":
            Device(device).long_press(args["x"], args["y"], duration_ms=args.get("duration_ms", 1000))
            return f"Long pressed ({args['x']}, {args['y']})"
        elif name == "launch_app":
            Device(device).adb("shell", "monkey", "-p", args["package"], "-c", "android.intent.category.LAUNCHER", "1")
            return f"Launched {args['package']}"
        elif name == "force_stop":
            Device(device).adb("shell", "am", "force-stop", args["package"])
            return f"Stopped {args['package']}"
        elif name == "list_apps" or name == "search_apps":
            out = Device(device).adb("shell", "pm", "list", "packages", timeout=10)
            pkgs = [p.replace("package:", "").strip() for p in out.splitlines() if p.startswith("package:")]
            # Known app names for common packages
            KNOWN = {
                "com.zhiliaoapp.musically": "TikTok", "com.instagram.android": "Instagram",
                "com.facebook.katana": "Facebook", "com.facebook.orca": "Messenger",
                "com.whatsapp": "WhatsApp", "com.twitter.android": "X (Twitter)",
                "com.snapchat.android": "Snapchat", "com.google.android.youtube": "YouTube",
                "com.google.android.apps.youtube.music": "YouTube Music",
                "com.google.android.apps.maps": "Google Maps", "com.google.android.gm": "Gmail",
                "com.google.android.apps.photos": "Google Photos",
                "com.google.android.apps.docs": "Google Drive",
                "com.android.chrome": "Chrome", "com.android.vending": "Play Store",
                "org.telegram.messenger": "Telegram", "com.discord": "Discord",
                "com.reddit.frontpage": "Reddit", "com.spotify.music": "Spotify",
                "com.amazon.mShop.android.shopping": "Amazon", "com.tinder": "Tinder",
                "com.bumble.app": "Bumble", "co.hinge.app": "Hinge",
                "com.nordvpn.android": "NordVPN", "com.anydesk.adcontrol.ad1": "AnyDesk",
                "com.google.android.gm": "Gmail", "com.google.android.calendar": "Calendar",
                "com.google.android.contacts": "Contacts", "com.google.android.dialer": "Phone",
                "com.android.camera": "Camera", "com.sec.android.app.camera": "Camera",
                "com.android.settings": "Settings", "com.android.calculator2": "Calculator",
                "com.android.deskclock": "Clock", "com.sec.android.gallery3d": "Gallery",
                "com.samsung.android.messaging": "Messages", "com.samsung.android.dialer": "Phone",
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
            out = Device(device).adb("shell", "pm", "list", "packages", "-3", timeout=15)
            pkgs = [p.replace("package:", "").strip() for p in out.splitlines() if p.startswith("package:")]
            return json.dumps(pkgs[:50])
        elif name == "shell":
            out = Device(device).adb("shell", *args["command"].split(), timeout=15)
            return out[:3000]
        elif name == "clipboard_get":
            return ctx.clipboard_get(device) or "(empty)"
        elif name == "clipboard_set":
            ctx.clipboard_set(device, args["text"])
            return "Clipboard set"
        elif name == "get_notifications":
            return json.dumps(ctx.get_notifications(device), indent=2)
        elif name == "list_skills":
            from gitd.routers.skills import _load_all_skills, _load_skill
            skills = _load_all_skills()
            result = []
            for sname, info in skills.items():
                s = _load_skill(sname)
                entry = {"name": info["name"], "app_package": info.get("app_package", "")}
                if s and not isinstance(s, dict):
                    entry["workflows"] = s.list_workflows()
                    entry["actions"] = s.list_actions()
                result.append(entry)
            return json.dumps(result, indent=2)
        elif name == "run_skill":
            runner = __import__("pathlib").Path(__file__).parent.parent / "skills" / "_run_skill.py"
            params = json.dumps(args.get("params", {}))
            r = subprocess.run(
                ["python3", "-u", str(runner), "--skill", args["skill"],
                 "--workflow", args["workflow"], "--device", device, "--params", params],
                capture_output=True, text=True, timeout=120,
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


def get_screenshot_b64(device: str) -> str | None:
    """Get raw base64 screenshot for vision context injection."""
    try:
        r = ctx.screenshot(device)
        return r.get("image")
    except Exception:
        return None
