"""Agent tool definitions — maps tool names to device_context functions.

Used by the agent chat service to execute LLM tool calls.
Tool schemas are in Anthropic's tool format and auto-converted for other providers.
"""

import json
import sys

from gitd.bots.common.device import get_device, is_ios_ref
from gitd.services import device_context as ctx
from gitd.services.tool_platforms import platform_error_text, supports_platform
from gitd.skills.platforms import skill_platform_error_text, skill_supports_device

# ── Tool registry ────────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "list_devices",
        "description": "List connected Android ADB device refs and configured iOS Appium device refs.",
        "input_schema": {"type": "object", "properties": {}},
    },
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
        "name": "start_screen_recording",
        "description": "Start recording the device screen. iOS uses WDA MJPEG through ffmpeg; Android uses adb screenrecord.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device": {"type": "string"},
                "filename": {"type": "string", "description": "Optional MP4 filename."},
            },
            "required": ["device"],
        },
    },
    {
        "name": "stop_screen_recording",
        "description": "Stop a running device screen recording and return the saved MP4 path/URL.",
        "input_schema": {"type": "object", "properties": {"device": {"type": "string"}}, "required": ["device"]},
    },
    {
        "name": "screen_recording_status",
        "description": "Return active screen recording status for a device.",
        "input_schema": {"type": "object", "properties": {"device": {"type": "string"}}, "required": ["device"]},
    },
    {
        "name": "get_stream_info",
        "description": (
            "Return platform-aware stream metadata without opening the stream. "
            "iOS reports WDA MJPEG URL/settings and unsupported Portal/WebRTC actions; "
            "Android reports Portal/H264/screencap mode metadata."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "device": {"type": "string"},
                "mode": {
                    "type": "string",
                    "description": "Requested mode, e.g. mjpeg, wda-mjpeg, portal, h264, screencap.",
                },
                "fps": {"type": "integer", "default": 5},
                "quality": {"type": "integer", "default": 8},
            },
            "required": ["device"],
        },
    },
    {
        "name": "get_screen_tree",
        "description": 'Get LLM-readable indented UI hierarchy. Each node: [idx] Class "label" [clickable] [bounds]. Use this to understand screen layout before acting.',
        "input_schema": {"type": "object", "properties": {"device": {"type": "string"}}, "required": ["device"]},
    },
    {
        "name": "get_screen_xml",
        "description": "Get the raw normalized UI XML dump. Prefer get_screen_tree unless exact attributes are needed.",
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
        "name": "device_health",
        "description": "Run a comprehensive device health check. On iOS, includes Appium/WDA status and recovery steps.",
        "input_schema": {"type": "object", "properties": {"device": {"type": "string"}}, "required": ["device"]},
    },
    {
        "name": "fix_device_health",
        "description": (
            "Apply a recovery action returned by device_health.recommended_fix. "
            "On iOS this can reset stale Appium/WDA sessions or restart a user-owned RemoteXPC tunnel."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "device": {"type": "string"},
                "issue": {"type": "string", "description": "Recovery code from device_health.recommended_fix."},
            },
            "required": ["device", "issue"],
        },
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
        "name": "type_unicode",
        "description": "Type unicode text into the focused field. Use for emoji, CJK, accented characters, and other non-ASCII input.",
        "input_schema": {
            "type": "object",
            "properties": {"device": {"type": "string"}, "text": {"type": "string"}},
            "required": ["device", "text"],
        },
    },
    {
        "name": "press_back",
        "description": "Press the platform Back/navigation-back control.",
        "input_schema": {"type": "object", "properties": {"device": {"type": "string"}}, "required": ["device"]},
    },
    {
        "name": "press_home",
        "description": "Press the platform Home button.",
        "input_schema": {"type": "object", "properties": {"device": {"type": "string"}}, "required": ["device"]},
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
            "Launch an app by Android package name or iOS bundle id. "
            "Use search_apps to find the package or bundle id. "
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
        "name": "launch_intent",
        "description": "Launch a full Android intent with optional action, data URI, package/component, and extras. Android-only.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device": {"type": "string"},
                "action": {"type": "string"},
                "data": {"type": "string"},
                "package": {"type": "string"},
                "component": {"type": "string"},
                "extras": {"type": "object"},
            },
            "required": ["device"],
        },
    },
    {
        "name": "open_camera",
        "description": (
            "Open the platform camera app in a specific mode. "
            "On Android this uses launcher/UI automation; on iOS this uses the Camera bundle and WDA UI controls. "
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
        "name": "toggle_overlay",
        "description": "Toggle Portal numbered element overlay on/off. Android-only.",
        "input_schema": {
            "type": "object",
            "properties": {"device": {"type": "string"}, "visible": {"type": "boolean", "default": True}},
            "required": ["device"],
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
        "name": "app_state",
        "description": "Check whether an Android package or iOS bundle id is installed, running, or foreground.",
        "input_schema": {
            "type": "object",
            "properties": {"device": {"type": "string"}, "package": {"type": "string"}},
            "required": ["device", "package"],
        },
    },
    {
        "name": "list_apps",
        "description": "List installed apps with human-readable names and Android package names or iOS bundle ids. Returns [{name, package, bundle_id}]. Use search_apps for faster lookup.",
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
        "description": "List raw Android package names or iOS bundle ids. Use list_apps or search_apps instead.",
        "input_schema": {"type": "object", "properties": {"device": {"type": "string"}}, "required": ["device"]},
    },
    {
        "name": "explore_app",
        "description": (
            "Explore an app UI with the cross-platform BFS app explorer and return the discovered state graph. "
            "Use an Android package name or iOS bundle id."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "device": {"type": "string"},
                "package": {"type": "string", "description": "Android package name or iOS bundle id."},
                "max_depth": {"type": "integer", "default": 2},
                "max_states": {"type": "integer", "default": 10},
            },
            "required": ["device", "package"],
        },
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
    {
        "name": "read_news",
        "description": (
            "Open a news page in iOS Chrome/browser, extract headlines, open the first articles, "
            "and return structured title/body snippets. Use this for news-reading tasks."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "device": {"type": "string"},
                "url": {"type": "string", "default": "https://text.npr.org/"},
                "max_headlines": {"type": "integer", "default": 5},
                "max_articles": {"type": "integer", "default": 3},
                "bundle_id": {"type": "string", "description": "Optional iOS browser bundle id override."},
                "wait_s": {"type": "number", "default": 2.0},
                "save_screenshots": {"type": "boolean", "default": False},
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
                "device": {
                    "type": "string",
                    "description": "Optional device ref used to include platform support flags.",
                },
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
    {
        "name": "run_workflow",
        "description": "Run a skill workflow. Alias of run_skill for MCP/agent parity.",
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
    {
        "name": "run_action",
        "description": "Run a single skill action when the skill supports the target device platform.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device": {"type": "string"},
                "skill": {"type": "string"},
                "action": {"type": "string"},
                "params": {"type": "object", "default": {}},
            },
            "required": ["device", "skill", "action"],
        },
    },
    {
        "name": "create_skill",
        "description": "Create a recorded automation skill with Android/iOS platform metadata and optional element selectors.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "app_package": {
                    "type": "string",
                    "description": "Android package, or iOS bundle id when platforms is ios.",
                },
                "steps": {"type": "array", "description": "Recorded step list."},
                "platforms": {"type": "array", "items": {"type": "string"}, "default": []},
                "ios_bundle_id": {"type": "string", "default": ""},
                "elements_ios": {
                    "type": ["object", "array"],
                    "items": {"type": "object"},
                    "default": [],
                    "description": "Captured iOS element list or selector map for elements_ios.yaml.",
                },
                "elements_android": {
                    "type": ["object", "array"],
                    "items": {"type": "object"},
                    "default": [],
                    "description": "Captured Android element list or selector map for elements.yaml.",
                },
            },
            "required": ["name", "app_package", "steps"],
        },
    },
    {
        "name": "crm_lookup_contact",
        "description": "Get the stored fact sheet for one local CRM contact by handle. Read-only.",
        "input_schema": {
            "type": "object",
            "properties": {"handle": {"type": "string", "description": "Contact handle with or without @."}},
            "required": ["handle"],
        },
    },
    {
        "name": "crm_list_unread_messages",
        "description": "List local CRM contacts with unread messages, sorted by recency. Read-only.",
        "input_schema": {"type": "object", "properties": {}},
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
    {
        "name": "chain",
        "description": (
            "Run several device actions in ONE step, settling between each — e.g. fill a form's "
            "fields, or tap→type→tap a submit. Saves turns on known sequences. Each sub-action is "
            '{"tool": "<name>", "args": {...}} using the same tool names; only read/UI tools are '
            "allowed inside a chain (no shell/run_skill/nested chain). Returns each sub-action's result."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "actions": {
                    "type": "array",
                    "description": 'Ordered sub-actions, e.g. [{"tool":"tap_element","args":{"idx":3}},{"tool":"type_text","args":{"text":"hi"}}].',
                    "items": {"type": "object"},
                },
                "settle": {
                    "type": "string",
                    "enum": ["stabilize", "delay"],
                    "default": "stabilize",
                    "description": "How to wait between sub-actions: 'stabilize' (short fixed settle) or 'delay' (delay_ms).",
                },
                "delay_ms": {
                    "type": "integer",
                    "default": 600,
                    "description": "Settle time when settle='delay' (capped 3000).",
                },
            },
            "required": ["actions"],
        },
    },
]


# Vetted allow-list of tools that are safe to expose in untrusted / third-party
# contexts — the run_flow batch primitive and the LangChain/LlamaIndex adapters
# both gate on this. It is an EXPLICIT allow-list (not "all TOOLS minus a
# dangerous set") so it fails CLOSED: a tool added to the dispatch later is NOT
# auto-exposed until it's deliberately vetted and added here. Every iOS-era
# tool below was classified individually; the exec-capable ones live in
# EXEC_CAPABLE_TOOLS instead and must never move here.
SAFE_DEVICE_TOOLS = frozenset(
    {
        # Screen reading
        "screenshot",
        "screenshot_annotated",
        "screenshot_cropped",
        "get_screen_tree",
        "get_screen_xml",
        "get_elements",
        "get_phone_state",
        "classify_screen",
        "find_on_screen",
        "ocr_screen",
        "ocr_region",
        "get_notifications",
        # Device inventory / status (read-only)
        "list_devices",
        "device_health",
        "app_state",
        "get_stream_info",
        "screen_recording_status",
        # Screen recording (writes only to the vetted recordings dir)
        "start_screen_recording",
        "stop_screen_recording",
        # UI actions
        "tap",
        "tap_element",
        "swipe",
        "type_text",
        "type_unicode",
        "press_key",
        "press_back",
        "press_home",
        "long_press",
        "paste_text",
        "clipboard_get",
        "clipboard_set",
        "launch_app",
        "force_stop",
        "open_camera",
        "speak_text",
        "toggle_overlay",
        "open_notifications",
        "clear_notifications",
        "wait",
        # App inventory
        "list_apps",
        "search_apps",
        "list_packages",
        "list_skills",
        # Browser (read/navigate)
        "web_search",
        "open_url",
        "browser_back",
        "get_current_url",
        "wait_for_text",
        "extract_visible_text",
        "extract_articles",
        "read_news",
        # Local CRM (read-only DB queries, no exec)
        "crm_lookup_contact",
        "crm_list_unread_messages",
    }
)

# Exec-capable tools, deliberately EXCLUDED from SAFE_DEVICE_TOOLS — same class
# as `shell`: they run subprocesses, launch arbitrary intents, or write code
# that is later imported. Kept as an explicit set so tests can prove the two
# sets stay disjoint and that new dispatch branches land in one or the other.
#   shell            — arbitrary adb shell
#   run_skill / run_workflow / run_action — execute skill code in a subprocess
#   create_skill     — writes skill code to gitd/skills/ (later imported)
#   launch_intent    — arbitrary Android intent incl. component + extras
#   explore_app      — spawns the BFS explorer subprocess, drives UI for minutes
#   fix_device_health — device-admin recovery actions (can install the Portal APK)
#   chain            — meta-executor: runs N sub-actions. Like run_flow it must
#                      not be reachable from run_flow / framework adapters (an
#                      untrusted batch shouldn't nest another batch), so it's
#                      denied here. It still gates its OWN sub-actions to
#                      SAFE_DEVICE_TOOLS, so even first-party callers can't
#                      smuggle shell/run_skill through it.
EXEC_CAPABLE_TOOLS = frozenset(
    {
        "shell",
        "run_skill",
        "run_workflow",
        "run_action",
        "create_skill",
        "launch_intent",
        "explore_app",
        "fix_device_health",
        "chain",
    }
)


# ── Tool execution ───────────────────────────────────────────────────────────

_KNOWN_TOOL_NAMES = {tool["name"] for tool in TOOLS}
_UI_ACTION_TOOLS = {
    "tap",
    "tap_element",
    "swipe",
    "type_text",
    "type_unicode",
    "press_back",
    "press_home",
    "press_key",
    "long_press",
    "launch_app",
    "open_url",
    "web_search",
    "browser_back",
    "wait_for_text",
}


def _device_platform(device: str) -> str:
    return "ios" if is_ios_ref(device) else "android"


def _platform_unsupported(tool_name: str, device: str) -> str:
    return platform_error_text(tool_name, _device_platform(device))


def tools_for_device(device: str | None) -> list[dict]:
    """Return the tools that should be offered to an agent for this device."""
    if not device:
        return list(TOOLS)
    platform = _device_platform(device)
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
        if device and not supports_platform(name, _device_platform(device)):
            return _platform_unsupported(name, device)

        if name == "list_devices":
            from gitd.bots.common.device import list_configured_ios_devices, list_connected_device_refs

            ios_details = {}
            try:
                ios_details = {
                    item.get("serial"): item
                    for item in list_configured_ios_devices(deep_probe=False)
                    if item.get("serial")
                }
            except Exception:
                ios_details = {}
            entries = []
            for serial in list_connected_device_refs():
                platform = "ios" if is_ios_ref(serial) else "android"
                entry = {"serial": serial, "platform": platform}
                if platform == "ios":
                    details = ios_details.get(serial) or {}
                    for key in (
                        "status",
                        "status_message",
                        "device_name",
                        "model",
                        "appium_url",
                        "source",
                        "host_state",
                    ):
                        if details.get(key):
                            entry[key] = details[key]
                entries.append(entry)
            return json.dumps(entries, indent=2)
        elif name == "screenshot":
            r = ctx.screenshot(device)
            return json.dumps(
                {
                    "device": r.get("device", device),
                    "platform": r.get("platform", "ios" if is_ios_ref(device) else "android"),
                    "image": r["image"][:100] + "...(truncated)",
                    "width": r["width"],
                    "height": r["height"],
                }
            )
        elif name == "screenshot_annotated":
            r = ctx.screenshot_annotated(device)
            return json.dumps(
                {
                    "device": r.get("device", device),
                    "platform": r.get("platform", "ios" if is_ios_ref(device) else "android"),
                    "image": r["image"][:100] + "...(truncated)",
                    "width": r["width"],
                    "height": r["height"],
                }
            )
        elif name == "screenshot_cropped":
            r = ctx.screenshot_cropped(device, args["x1"], args["y1"], args["x2"], args["y2"])
            return json.dumps(
                {
                    "device": r.get("device", device),
                    "platform": r.get("platform", "ios" if is_ios_ref(device) else "android"),
                    "image": r["image"][:100] + "...(truncated)",
                    "width": r["width"],
                    "height": r["height"],
                }
            )
        elif name == "start_screen_recording":
            from gitd.services.phone_recording import start_recording

            return json.dumps(start_recording(device, filename=args.get("filename", "")), indent=2)
        elif name == "stop_screen_recording":
            from gitd.services.phone_recording import stop_recording

            return json.dumps(stop_recording(device), indent=2)
        elif name == "screen_recording_status":
            from gitd.services.phone_recording import recording_status

            return json.dumps(recording_status(device), indent=2)
        elif name == "get_stream_info":
            from gitd.routers.streaming import phone_stream_info

            return json.dumps(
                phone_stream_info(
                    device=device,
                    fps=int(args.get("fps", 5)),
                    quality=int(args.get("quality", 8)),
                    mode=args.get("mode", "mjpeg"),
                ),
                indent=2,
            )
        elif name == "get_screen_tree":
            return ctx.get_screen_tree(device)
        elif name == "get_screen_xml":
            return ctx.get_screen_xml(device)
        elif name == "get_elements":
            return json.dumps(ctx.get_interactive_elements(device), indent=2)
        elif name == "get_phone_state":
            return json.dumps(ctx.get_phone_state(device), indent=2)
        elif name == "device_health":
            return json.dumps(ctx.device_health(device), indent=2)
        elif name == "fix_device_health":
            return json.dumps(ctx.fix_device_health(device, args["issue"]), indent=2)
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
                return f"Typed: {args['text']}"
            # `adb input text` is ASCII-only — one non-ASCII char blanks the whole
            # field. Transliterate to the closest ASCII so accented input still
            # lands (use type_unicode for full-fidelity emoji/CJK).
            from gitd.bots.common.adb import ascii_typeable

            typed = ascii_typeable(args["text"])
            Device(device).adb("shell", "input", "text", typed.replace(" ", "%s"))
            if typed != args["text"]:
                return f"Typed (transliterated non-ASCII): {args['text']!r} -> {typed!r}"
            return f"Typed: {typed}"
        elif name == "type_unicode":
            if is_ios_ref(device):
                get_device(device).type_text(args["text"])
            else:
                Device(device).type_unicode(args["text"])
            return f"Typed (unicode): {args['text']}"
        elif name == "press_back":
            get_device(device).back()
            return "Pressed Back"
        elif name == "press_home":
            if is_ios_ref(device):
                get_device(device).press_key("HOME")
            else:
                Device(device).adb("shell", "input", "keyevent", "KEYCODE_HOME")
            return "Pressed Home"
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
        elif name == "toggle_overlay":
            ok = ctx.toggle_overlay(device, bool(args.get("visible", True)))
            return (
                f"Overlay {'enabled' if args.get('visible', True) else 'disabled'}"
                if ok
                else "Failed — Portal not available"
            )
        elif name == "force_stop":
            if is_ios_ref(device):
                get_device(device).terminate_app(args["package"])
                return f"Stopped iOS app {args['package']}"
            Device(device).adb("shell", "am", "force-stop", args["package"])
            return f"Stopped {args['package']}"
        elif name == "app_state":
            return json.dumps(ctx.app_state(device, args["package"]), indent=2)
        elif name == "launch_intent":
            return ctx.launch_intent(
                device,
                action=args.get("action", ""),
                data=args.get("data", ""),
                package=args.get("package", ""),
                component=args.get("component", ""),
                extras=args.get("extras") or None,
            )
        elif name == "web_search":
            if is_ios_ref(device):
                from gitd.services.browser import dumps
                from gitd.services.browser import web_search as _web_search

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
            from gitd.services.browser import dumps
            from gitd.services.browser import open_url as _open_url

            return dumps(_open_url(device, args["url"], bundle_id=args.get("bundle_id") or None))
        elif name == "browser_back":
            from gitd.services.browser import browser_back as _browser_back
            from gitd.services.browser import dumps

            return dumps(_browser_back(device))
        elif name == "get_current_url":
            from gitd.services.browser import dumps
            from gitd.services.browser import get_current_url as _get_current_url

            return dumps(_get_current_url(device))
        elif name == "wait_for_text":
            from gitd.services.browser import dumps
            from gitd.services.browser import wait_for_text as _wait_for_text

            return dumps(_wait_for_text(device, args["text"], timeout=float(args.get("timeout", 12.0))))
        elif name == "extract_visible_text":
            from gitd.services.browser import dumps
            from gitd.services.browser import extract_visible_text as _extract_visible_text

            return dumps(
                _extract_visible_text(
                    device,
                    max_lines=int(args.get("max_lines", 200)),
                    include_controls=bool(args.get("include_controls", False)),
                )
            )
        elif name == "extract_articles":
            from gitd.services.browser import dumps
            from gitd.services.browser import extract_articles as _extract_articles

            return dumps(_extract_articles(device, max_items=int(args.get("max_items", 5))))
        elif name == "read_news":
            from gitd.services.browser import dumps
            from gitd.services.browser import read_news as _read_news

            return dumps(
                _read_news(
                    device,
                    args.get("url", "https://text.npr.org/"),
                    max_headlines=int(args.get("max_headlines", 5)),
                    max_articles=int(args.get("max_articles", 3)),
                    bundle_id=args.get("bundle_id") or None,
                    wait_s=float(args.get("wait_s", 2.0)),
                    save_screenshots=bool(args.get("save_screenshots", False)),
                )
            )
        elif name == "list_apps" or name == "search_apps":
            query = args.get("query", "") if name == "search_apps" else ""
            return json.dumps(ctx.list_apps(device, query=query), indent=2)
        elif name == "list_packages":
            return json.dumps(ctx.list_packages(device)[:50], indent=2)
        elif name == "explore_app":
            from pathlib import Path

            package = args["package"]
            script = Path(__file__).resolve().parents[1] / "skills" / "auto_creator.py"
            project_dir = Path(__file__).resolve().parents[2]
            max_depth = int(args.get("max_depth", 2))
            max_states = int(args.get("max_states", 10))
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
                cwd=str(project_dir),
            )
            graph_path = project_dir / "data" / "app_explorer" / package / "state_graph.json"
            if graph_path.exists():
                return graph_path.read_text()[:10000]
            output = result.stdout[-1000:]
            if result.returncode != 0 and result.stderr:
                output += f"\nSTDERR:\n{result.stderr[-1000:]}"
            return f"Exploration finished. Output:\n{output}"
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
            if not ctx.open_notifications(device):
                return "Failed"
            return "Notification Center opened" if is_ios_ref(device) else "Notification shade opened"
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
                    "description": info.get("description", ""),
                    "app_package": info.get("app_package", ""),
                    "android_package": info.get("android_package", ""),
                    "ios_bundle_id": info.get("ios_bundle_id", ""),
                    "platforms": info.get("platforms", []),
                    "supports_android": info.get("supports_android", False),
                    "supports_ios": info.get("supports_ios", False),
                    "platform_limitations": info.get("platform_limitations", {}),
                    "default_params": info.get("default_params", {}),
                }
                if supported is not None:
                    entry["supported_on_device"] = supported
                if s and not isinstance(s, dict):
                    entry["workflows"] = s.list_workflows()
                    entry["actions"] = s.list_actions()
                result.append(entry)
            return json.dumps(result, indent=2)
        elif name in {"run_skill", "run_workflow", "run_action"}:
            from gitd.routers.skills import _load_all_skills

            skills = _load_all_skills()
            skill_info = skills.get(args["skill"])
            if skill_info and not skill_supports_device(skill_info.get("metadata") or {}, device):
                return skill_platform_error_text(args["skill"], skill_info.get("metadata") or {}, device)
            runner = __import__("pathlib").Path(__file__).parent.parent / "skills" / "_run_skill.py"
            params = json.dumps(args.get("params", {}))
            mode_arg = "--action" if name == "run_action" else "--workflow"
            target = args["action"] if name == "run_action" else args["workflow"]
            r = subprocess.run(
                [
                    sys.executable,
                    "-u",
                    str(runner),
                    "--skill",
                    args["skill"],
                    mode_arg,
                    target,
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
        elif name == "create_skill":
            from gitd.services.skill_creation import create_recorded_skill

            result = create_recorded_skill(
                name=args["name"],
                app_package=args.get("app_package", ""),
                steps=args.get("steps", []),
                platforms=args.get("platforms", []),
                ios_bundle_id=args.get("ios_bundle_id", ""),
                elements_ios=args.get("elements_ios") if "elements_ios" in args else None,
                elements_android=args.get("elements_android") if "elements_android" in args else None,
            )
            return json.dumps(
                {
                    "ok": True,
                    "skill": result["skill"],
                    "steps": result["steps"],
                    "dir": result["dir"],
                    "platforms": result["platforms"],
                    "metadata": result["metadata"],
                },
                indent=2,
            )
        elif name == "crm_lookup_contact":
            from gitd.services.crm_lookup import crm_lookup_contact

            return crm_lookup_contact(args["handle"])
        elif name == "crm_list_unread_messages":
            from gitd.services.crm_lookup import crm_list_unread_messages

            return crm_list_unread_messages()
        elif name == "wait":
            time.sleep(args.get("seconds", 2))
            return f"Waited {args.get('seconds', 2)}s"
        elif name == "chain":
            return _execute_chain(device, args)
        else:
            return f"Unknown tool: {name}"
    except Exception as e:
        return f"Error: {e}"


# Cap on sub-actions per chain — a batch that big is almost certainly a
# runaway; bound it so one chain call can't monopolise the device.
_CHAIN_MAX_ACTIONS = 15
_CHAIN_MAX_DELAY_S = 3.0
_CHAIN_STABILIZE_S = 0.6


def _execute_chain(device: str, args: dict) -> str:
    """Run a sequence of sub-actions in one step, settling between each.

    Fail-closed like run_flow: every sub-action's tool must be on
    SAFE_DEVICE_TOOLS, and a chain may not nest another chain — a batch is
    exactly where an injected instruction would try to smuggle an exec tool, so
    the whole chain is refused before any sub-action runs if any step names a
    non-allowed tool. Sub-actions dispatch via _execute_tool_inner (no
    per-action screen-tree append); we settle between them instead.
    """
    import time

    subs = args.get("actions")
    if not isinstance(subs, list) or not subs:
        return "chain: 'actions' must be a non-empty list of {tool, args}"
    if len(subs) > _CHAIN_MAX_ACTIONS:
        return f"chain: too many actions ({len(subs)} > {_CHAIN_MAX_ACTIONS})"

    # Validate the WHOLE batch before running ANY of it, so a chain that hides a
    # disallowed action after some benign steps executes nothing.
    for i, sub in enumerate(subs):
        if not isinstance(sub, dict) or "tool" not in sub:
            return f"chain: step {i} must be an object with a 'tool' field"
        tool = sub["tool"]
        if tool == "chain":
            return f"chain: step {i} may not nest another chain"
        if tool not in SAFE_DEVICE_TOOLS:
            return f"chain: step {i} tool '{tool}' is not allowed inside a chain (only read/UI tools)"

    settle = args.get("settle", "stabilize")
    delay_s = min(max(int(args.get("delay_ms", 600)), 0) / 1000, _CHAIN_MAX_DELAY_S)

    infos: list[str] = []
    for i, sub in enumerate(subs):
        tool = sub["tool"]
        sub_args = dict(sub.get("args") or {})
        sub_args.setdefault("device", device)
        try:
            out = _execute_tool_inner(tool, sub_args)
            infos.append(f"{tool}: {str(out)[:80]}")
        except Exception as e:
            infos.append(f"{tool}: err:{e}")
            break  # abort the rest of the chain on the first hard failure
        if i < len(subs) - 1:
            time.sleep(delay_s if settle == "delay" else _CHAIN_STABILIZE_S)

    return f"chain[{len(infos)}/{len(subs)}]: " + " > ".join(infos)


def get_screenshot_b64(device: str) -> str | None:
    """Get raw base64 screenshot for vision context injection."""
    try:
        r = ctx.screenshot(device)
        return r.get("image")
    except Exception:
        return None
