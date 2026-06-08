import ast
import json
import sys
from pathlib import Path

from gitd.services.agent_chat import DEFAULT_SYSTEM, openai_tools_for_device, platform_context, system_prompt_for_device
from gitd.services.agent_tools import TOOLS, execute_tool, tool_prompt_list, tools_for_device
from gitd.services.tool_platforms import TOOL_PLATFORM_SUPPORT, supports_platform, tool_platform_info


def _mcp_tool_names() -> set[str]:
    tree = ast.parse(Path("gitd/mcp_server.py").read_text(encoding="utf-8"))
    names = set()
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        for dec in node.decorator_list:
            if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) and dec.func.attr == "tool":
                names.add(node.name)
    return names


def _mcp_public_docstrings() -> dict[str, str]:
    tree = ast.parse(Path("gitd/mcp_server.py").read_text(encoding="utf-8"))
    docs = {"__module__": ast.get_docstring(tree) or ""}
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        for dec in node.decorator_list:
            if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) and dec.func.attr == "tool":
                docs[node.name] = ast.get_docstring(node) or ""
    return docs


def test_every_agent_and_mcp_tool_has_platform_classification():
    agent_names = {tool["name"] for tool in TOOLS}
    names = agent_names | _mcp_tool_names()

    missing = sorted(name for name in names if name not in TOOL_PLATFORM_SUPPORT)

    assert missing == []


def test_platform_classifications_have_stable_ios_semantics():
    assert supports_platform("screenshot", "ios") is True
    assert supports_platform("start_screen_recording", "ios") is True
    assert supports_platform("stop_screen_recording", "ios") is True
    assert supports_platform("screen_recording_status", "ios") is True
    assert supports_platform("get_stream_info", "ios") is True
    assert supports_platform("get_stream_info", "android") is True
    assert supports_platform("open_url", "ios") is True
    assert supports_platform("device_health", "ios") is True
    assert supports_platform("device_health", "android") is True
    assert supports_platform("fix_device_health", "ios") is True
    assert supports_platform("fix_device_health", "android") is True
    assert supports_platform("get_screen_xml", "ios") is True
    assert supports_platform("press_back", "ios") is True
    assert supports_platform("press_home", "ios") is True
    assert supports_platform("type_unicode", "ios") is True
    assert supports_platform("get_current_url", "ios") is True
    assert supports_platform("get_current_url", "android") is False
    assert supports_platform("shell", "ios") is False
    assert supports_platform("clipboard_get", "ios") is True
    assert supports_platform("clipboard_set", "ios") is True
    assert supports_platform("paste_text", "ios") is True
    assert supports_platform("list_apps", "ios") is True
    assert supports_platform("search_apps", "ios") is True
    assert supports_platform("list_packages", "ios") is True
    assert supports_platform("app_state", "ios") is True
    assert supports_platform("get_notifications", "ios") is True
    assert supports_platform("open_notifications", "ios") is True
    assert supports_platform("clear_notifications", "ios") is True
    assert supports_platform("open_camera", "ios") is True
    assert supports_platform("explore_app", "ios") is True
    assert supports_platform("create_skill", "ios") is True
    assert supports_platform("read_news", "ios") is True
    assert supports_platform("read_news", "android") is False
    assert supports_platform("launch_intent", "ios") is False
    assert supports_platform("launch_intent", "android") is True
    assert supports_platform("toggle_overlay", "ios") is False
    assert supports_platform("toggle_overlay", "android") is True

    assert tool_platform_info("shell").support == "android_only"
    assert tool_platform_info("launch_intent").support == "android_only"
    assert tool_platform_info("toggle_overlay").support == "android_only"
    assert tool_platform_info("device_health").support == "cross_platform"
    assert tool_platform_info("fix_device_health").support == "cross_platform"
    assert tool_platform_info("get_screen_xml").support == "cross_platform"
    assert tool_platform_info("press_back").support == "cross_platform"
    assert tool_platform_info("press_home").support == "cross_platform"
    assert tool_platform_info("type_unicode").support == "cross_platform"
    assert tool_platform_info("start_screen_recording").support == "cross_platform"
    assert tool_platform_info("get_stream_info").support == "cross_platform"
    assert tool_platform_info("clipboard_get").support == "cross_platform"
    assert tool_platform_info("clipboard_set").support == "cross_platform"
    assert tool_platform_info("paste_text").support == "cross_platform"
    assert tool_platform_info("list_apps").support == "cross_platform"
    assert tool_platform_info("app_state").support == "cross_platform"
    assert tool_platform_info("get_notifications").support == "cross_platform"
    assert tool_platform_info("open_camera").support == "cross_platform"
    assert tool_platform_info("explore_app").support == "cross_platform"
    assert tool_platform_info("create_skill").support == "cross_platform"
    assert tool_platform_info("read_news").support == "ios_supported"


def test_mcp_public_docs_are_ios_safe_for_cross_platform_primitives():
    docs = _mcp_public_docstrings()

    assert "mobile automation" in docs["__module__"]
    assert "Android automation" not in docs["__module__"]

    assert "normalized Appium/WDA XML" in docs["get_screen_xml"]
    assert "raw UI XML dump from the device (uiautomator)" not in docs["get_screen_xml"]

    assert "WDA text entry" in docs["type_unicode"]
    assert "ADBKeyboard broadcast" not in docs["type_unicode"]

    assert "iOS supports WDA-backed HOME, ENTER/RETURN, and BACK/ESCAPE" in docs["press_key"]
    assert "Full list" not in docs["press_key"]


def test_execute_tool_uses_platform_registry_for_ios_errors(monkeypatch):
    monkeypatch.setattr("gitd.services.device_context.clipboard_get", lambda device: "ios clipboard")
    monkeypatch.setattr(
        "gitd.services.device_context.get_notifications",
        lambda device: [{"title": "Slack", "text": "New message", "platform": "ios"}],
    )
    monkeypatch.setattr("gitd.services.device_context.open_notifications", lambda device: True)
    monkeypatch.setattr("gitd.services.device_context.clear_notifications", lambda device: True)
    monkeypatch.setattr(
        "gitd.services.device_context.device_health",
        lambda device: {
            "serial": device,
            "platform": "ios",
            "connection": {"type": "appium-wda", "status": "wda_signing_failed"},
            "recommended_fix": "fix_wda_signing",
        },
    )
    monkeypatch.setattr(
        "gitd.services.device_context.fix_device_health",
        lambda device, issue: {
            "ok": False,
            "platform": "ios",
            "issue": issue,
            "manual_action_required": True,
        },
    )
    monkeypatch.setattr(
        "gitd.routers.streaming.phone_stream_info",
        lambda **kwargs: {
            "ok": True,
            "device": kwargs["device"],
            "platform": "ios",
            "effective_mode": "wda-mjpeg",
            "stream_url": "/api/phone/stream?device=ios%3Aabc123&fps=5&mode=wda-mjpeg",
        },
    )

    shell = execute_tool("shell", {"device": "ios:abc123", "command": "ls"})
    launch_intent = execute_tool("launch_intent", {"device": "ios:abc123", "action": "android.intent.action.VIEW"})
    toggle_overlay = execute_tool("toggle_overlay", {"device": "ios:abc123", "visible": True})
    clipboard = execute_tool("clipboard_get", {"device": "ios:abc123"})
    notifications = json.loads(execute_tool("get_notifications", {"device": "ios:abc123"}))
    opened = execute_tool("open_notifications", {"device": "ios:abc123"})
    cleared = execute_tool("clear_notifications", {"device": "ios:abc123"})
    health = json.loads(execute_tool("device_health", {"device": "ios:abc123"}))
    fix = json.loads(execute_tool("fix_device_health", {"device": "ios:abc123", "issue": "fix_wda_signing"}))
    stream_info = json.loads(execute_tool("get_stream_info", {"device": "ios:abc123", "mode": "mjpeg"}))
    unknown = execute_tool("does_not_exist", {"device": "ios:abc123"})
    android_current_url = execute_tool("get_current_url", {"device": "emulator-5554"})
    android_news = execute_tool(
        "read_news",
        {"device": "emulator-5554", "url": "https://text.npr.org/"},
    )

    assert shell.startswith("ERROR: shell is Android-only")
    assert launch_intent.startswith("ERROR: launch_intent is Android-only")
    assert toggle_overlay.startswith("ERROR: toggle_overlay is Android-only")
    assert clipboard == "ios clipboard"
    assert notifications == [{"title": "Slack", "text": "New message", "platform": "ios"}]
    assert opened == "Notification Center opened"
    assert cleared == "Notifications cleared"
    assert health["connection"]["status"] == "wda_signing_failed"
    assert health["recommended_fix"] == "fix_wda_signing"
    assert fix["issue"] == "fix_wda_signing"
    assert fix["manual_action_required"] is True
    assert stream_info["effective_mode"] == "wda-mjpeg"
    assert stream_info["stream_url"].endswith("mode=wda-mjpeg")
    assert unknown == "Unknown tool: does_not_exist"
    assert android_current_url == "ERROR: get_current_url is currently implemented only for iOS"
    assert android_news == "ERROR: read_news is currently implemented only for iOS"


def test_android_only_agent_tools_dispatch_through_shared_helpers(monkeypatch):
    calls = []

    def fake_launch_intent(device, action="", data="", package="", component="", extras=None):
        calls.append(("intent", device, action, data, package, component, extras))
        return "intent launched"

    def fake_toggle_overlay(device, visible=True):
        calls.append(("overlay", device, visible))
        return True

    monkeypatch.setattr("gitd.services.device_context.launch_intent", fake_launch_intent)
    monkeypatch.setattr("gitd.services.device_context.toggle_overlay", fake_toggle_overlay)

    intent = execute_tool(
        "launch_intent",
        {
            "device": "emulator-5554",
            "action": "android.intent.action.VIEW",
            "data": "https://example.com",
            "package": "com.android.chrome",
            "component": ".Main",
            "extras": {"demo": "yes"},
        },
    )
    overlay = execute_tool("toggle_overlay", {"device": "emulator-5554", "visible": False})

    assert intent == "intent launched"
    assert overlay == "Overlay disabled"
    assert calls == [
        (
            "intent",
            "emulator-5554",
            "android.intent.action.VIEW",
            "https://example.com",
            "com.android.chrome",
            ".Main",
            {"demo": "yes"},
        ),
        ("overlay", "emulator-5554", False),
    ]


def test_mcp_open_notifications_uses_platform_terms(monkeypatch):
    from gitd import mcp_server

    monkeypatch.setattr("gitd.services.device_context.open_notifications", lambda device: True)

    assert mcp_server.open_notifications("ios:abc123") == "Notification Center opened"
    assert mcp_server.open_notifications("emulator-5554") == "Notification shade opened"


def test_agent_list_devices_returns_android_and_ios_metadata(monkeypatch):
    monkeypatch.setattr(
        "gitd.bots.common.device.list_connected_device_refs",
        lambda: ["emulator-5554", "ios:abc123"],
    )
    monkeypatch.setattr(
        "gitd.bots.common.device.list_configured_ios_devices",
        lambda deep_probe=False: [
            {
                "serial": "ios:abc123",
                "status": "available",
                "device_name": "Test iPhone",
                "appium_url": "http://127.0.0.1:4723",
            }
        ],
    )

    devices = json.loads(execute_tool("list_devices", {}))

    assert devices == [
        {"serial": "emulator-5554", "platform": "android"},
        {
            "serial": "ios:abc123",
            "platform": "ios",
            "status": "available",
            "device_name": "Test iPhone",
            "appium_url": "http://127.0.0.1:4723",
        },
    ]


def test_agent_marketing_lookup_tools_use_shared_service(monkeypatch):
    monkeypatch.setattr("gitd.services.marketing_lookup.lookup_lead", lambda handle: f"lead:{handle}")
    monkeypatch.setattr("gitd.services.marketing_lookup.list_unread_leads", lambda: "2 unread")

    assert execute_tool("lookup_lead", {"handle": "demo"}) == "lead:demo"
    assert execute_tool("list_unread_leads", {}) == "2 unread"


def test_agent_run_skill_uses_current_interpreter(monkeypatch):
    captured = {}

    class FakeRun:
        returncode = 0
        stdout = "skill ok"
        stderr = ""

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return FakeRun()

    monkeypatch.setattr("subprocess.run", fake_run)

    result = execute_tool(
        "run_skill",
        {
            "device": "ios:abc123",
            "skill": "safari",
            "workflow": "read_news",
            "params": {"url": "https://text.npr.org/"},
        },
    )

    assert result == "skill ok"
    assert captured["cmd"][:2] == [sys.executable, "-u"]
    assert "gitd/skills/_run_skill.py" in captured["cmd"][2]
    assert captured["kwargs"]["timeout"] == 120


def test_agent_run_action_uses_current_interpreter(monkeypatch):
    captured = {}

    class FakeRun:
        returncode = 0
        stdout = "action ok"
        stderr = ""

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return FakeRun()

    monkeypatch.setattr("subprocess.run", fake_run)

    result = execute_tool(
        "run_action",
        {
            "device": "ios:abc123",
            "skill": "safari",
            "action": "read_news",
            "params": {"url": "https://text.npr.org/"},
        },
    )

    assert result == "action ok"
    assert captured["cmd"][:2] == [sys.executable, "-u"]
    assert "gitd/skills/_run_skill.py" in captured["cmd"][2]
    assert "--action" in captured["cmd"]
    assert captured["cmd"][captured["cmd"].index("--action") + 1] == "read_news"
    assert "--workflow" not in captured["cmd"]
    assert captured["kwargs"]["timeout"] == 120


def test_agent_create_skill_uses_shared_creator(monkeypatch):
    captured = {}

    def fake_create_recorded_skill(**kwargs):
        captured.update(kwargs)
        return {
            "ok": True,
            "skill": kwargs["name"],
            "steps": len(kwargs["steps"]),
            "dir": "/tmp/skills/ios_agent_demo",
            "platforms": ["ios"],
            "metadata": {
                "name": kwargs["name"],
                "app_package": "",
                "android_package": "",
                "ios_bundle_id": kwargs["app_package"],
                "platforms": ["ios"],
            },
        }

    monkeypatch.setattr("gitd.services.skill_creation.create_recorded_skill", fake_create_recorded_skill)

    result = json.loads(
        execute_tool(
            "create_skill",
            {
                "name": "ios_agent_demo",
                "app_package": "com.google.chrome.ios",
                "steps": [{"action": "launch", "package": "com.google.chrome.ios"}],
                "platforms": ["ios"],
                "elements_ios": [{"text": "Search", "class": "XCUIElementTypeTextField"}],
            },
        )
    )

    assert result["ok"] is True
    assert result["metadata"]["ios_bundle_id"] == "com.google.chrome.ios"
    assert captured["name"] == "ios_agent_demo"
    assert captured["app_package"] == "com.google.chrome.ios"
    assert captured["platforms"] == ["ios"]
    assert captured["elements_ios"] == [{"text": "Search", "class": "XCUIElementTypeTextField"}]


def test_agent_explore_app_uses_auto_creator_subprocess(monkeypatch):
    captured = {}

    class FakeRun:
        returncode = 0
        stdout = "explorer ok"
        stderr = ""

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return FakeRun()

    monkeypatch.setattr("subprocess.run", fake_run)

    result = execute_tool(
        "explore_app",
        {
            "device": "ios:abc123",
            "package": "com.example.agentexplorepytest",
            "max_depth": 1,
            "max_states": 2,
        },
    )

    assert result == "Exploration finished. Output:\nexplorer ok"
    assert captured["cmd"][:2] == [sys.executable, "-u"]
    assert "gitd/skills/auto_creator.py" in captured["cmd"][2]
    assert captured["cmd"][captured["cmd"].index("--package") + 1] == "com.example.agentexplorepytest"
    assert captured["cmd"][captured["cmd"].index("--device") + 1] == "ios:abc123"
    assert captured["cmd"][captured["cmd"].index("--max-depth") + 1] == "1"
    assert captured["cmd"][captured["cmd"].index("--max-states") + 1] == "2"
    assert captured["kwargs"]["timeout"] == 300


def test_tools_for_device_filters_by_platform():
    ios_names = {tool["name"] for tool in tools_for_device("ios:abc123")}
    android_names = {tool["name"] for tool in tools_for_device("emulator-5554")}

    assert "open_url" in ios_names
    assert "list_devices" in ios_names
    assert "start_screen_recording" in ios_names
    assert "stop_screen_recording" in ios_names
    assert "screen_recording_status" in ios_names
    assert "get_stream_info" in ios_names
    assert "get_screen_xml" in ios_names
    assert "device_health" in ios_names
    assert "fix_device_health" in ios_names
    assert "extract_articles" in ios_names
    assert "shell" not in ios_names
    assert "launch_intent" not in ios_names
    assert "clipboard_get" in ios_names
    assert "clipboard_set" in ios_names
    assert "paste_text" in ios_names
    assert "press_back" in ios_names
    assert "press_home" in ios_names
    assert "type_unicode" in ios_names
    assert "get_current_url" in ios_names
    assert "list_apps" in ios_names
    assert "search_apps" in ios_names
    assert "list_packages" in ios_names
    assert "run_workflow" in ios_names
    assert "run_action" in ios_names
    assert "create_skill" in ios_names
    assert "lookup_lead" in ios_names
    assert "list_unread_leads" in ios_names
    assert "app_state" in ios_names
    assert "get_notifications" in ios_names
    assert "open_notifications" in ios_names
    assert "clear_notifications" in ios_names
    assert "open_camera" in ios_names
    assert "explore_app" in ios_names
    assert "read_news" in ios_names

    assert "shell" in android_names
    assert "list_devices" in android_names
    assert "get_screen_xml" in android_names
    assert "press_back" in android_names
    assert "press_home" in android_names
    assert "type_unicode" in android_names
    assert "run_workflow" in android_names
    assert "run_action" in android_names
    assert "create_skill" in android_names
    assert "lookup_lead" in android_names
    assert "list_unread_leads" in android_names
    assert "start_screen_recording" in android_names
    assert "get_stream_info" in android_names
    assert "device_health" in android_names
    assert "fix_device_health" in android_names
    assert "app_state" in android_names
    assert "explore_app" in android_names
    assert "get_current_url" not in android_names
    assert "read_news" not in android_names


def test_ios_app_listing_tools_use_ios_inventory(monkeypatch):
    class FakeIOSDevice:
        def list_apps(self, query="", verify=True):
            apps = [
                {
                    "name": "Chrome",
                    "package": "com.google.chrome.ios",
                    "bundle_id": "com.google.chrome.ios",
                    "platform": "ios",
                    "verified": True,
                    "installed": True,
                },
                {
                    "name": "TikTok",
                    "package": "com.zhiliaoapp.musically",
                    "bundle_id": "com.zhiliaoapp.musically",
                    "platform": "ios",
                    "verified": True,
                    "installed": True,
                },
            ]
            if query:
                needle = query.lower()
                apps = [app for app in apps if needle in app["name"].lower() or needle in app["bundle_id"].lower()]
            return apps

    monkeypatch.setattr("gitd.services.device_context.get_device", lambda device: FakeIOSDevice())

    search = json.loads(execute_tool("search_apps", {"device": "ios:abc123", "query": "chrome"}))
    packages = json.loads(execute_tool("list_packages", {"device": "ios:abc123"}))

    assert search == [
        {
            "name": "Chrome",
            "package": "com.google.chrome.ios",
            "bundle_id": "com.google.chrome.ios",
            "platform": "ios",
            "verified": True,
            "installed": True,
        }
    ]
    assert packages == ["com.google.chrome.ios", "com.zhiliaoapp.musically"]


def test_ios_open_camera_tool_uses_ios_backend(monkeypatch):
    class FakeIOSDevice:
        def open_camera(self, mode="photo", timer_s=0):
            return {
                "mode": mode,
                "selected_mode": True,
                "switched_camera": True,
                "timer_set": True,
            }

    monkeypatch.setattr("gitd.services.agent_tools.get_device", lambda device: FakeIOSDevice())

    result = execute_tool("open_camera", {"device": "ios:abc123", "mode": "selfie", "timer_s": 3})

    assert result == "Opened iOS Camera - selfie"


def test_ios_paste_text_tool_uses_ios_backend(monkeypatch):
    calls = []

    class FakeIOSDevice:
        def paste_text(self, text):
            calls.append(text)
            return True

    monkeypatch.setattr("gitd.services.agent_tools.get_device", lambda device: FakeIOSDevice())

    result = execute_tool("paste_text", {"device": "ios:abc123", "text": "hello"})

    assert result == "Inserted text on iOS: hello"
    assert calls == ["hello"]


def test_ios_agent_primitive_aliases_use_ios_backend(monkeypatch):
    calls = []

    class FakeIOSDevice:
        def tap(self, x, y):
            calls.append(("tap", x, y))

        def swipe(self, x1, y1, x2, y2, ms=500):
            calls.append(("swipe", x1, y1, x2, y2, ms))

        def long_press(self, x, y, duration_ms=1000):
            calls.append(("long_press", x, y, duration_ms))

        def type_text(self, text):
            calls.append(("type", text))

        def back(self):
            calls.append(("back",))

        def press_key(self, key):
            calls.append(("key", key))

    monkeypatch.setattr("gitd.services.agent_tools.get_device", lambda device: FakeIOSDevice())
    monkeypatch.setattr("gitd.services.agent_tools.ctx.get_screen_tree", lambda device: "(empty screen)")
    monkeypatch.setattr("gitd.services.agent_tools.ctx.get_screen_xml", lambda device: "<hierarchy />")

    tapped = execute_tool("tap", {"device": "ios:abc123", "x": 10, "y": 20})
    swiped = execute_tool("swipe", {"device": "ios:abc123", "x1": 1, "y1": 2, "x2": 3, "y2": 4})
    long_pressed = execute_tool("long_press", {"device": "ios:abc123", "x": 8, "y": 9, "duration_ms": 1500})
    typed = execute_tool("type_unicode", {"device": "ios:abc123", "text": "cafe\u0301"})
    back = execute_tool("press_back", {"device": "ios:abc123"})
    home = execute_tool("press_home", {"device": "ios:abc123"})
    xml = execute_tool("get_screen_xml", {"device": "ios:abc123"})

    assert tapped == "Tapped (10, 20)"
    assert swiped == "Swiped (1,2) -> (3,4)"
    assert long_pressed == "Long pressed (8, 9)"
    assert typed == "Typed (unicode): cafe\u0301"
    assert back == "Pressed Back"
    assert home == "Pressed Home"
    assert xml == "<hierarchy />"
    assert calls == [
        ("tap", 10, 20),
        ("swipe", 1, 2, 3, 4, 500),
        ("long_press", 8, 9, 1500),
        ("type", "cafe\u0301"),
        ("back",),
        ("key", "HOME"),
    ]


def test_platform_prompts_do_not_offer_android_only_tools_to_ios():
    ios_tools = tools_for_device("ios:abc123")
    ios_tool_list = tool_prompt_list(ios_tools)
    ios_system = system_prompt_for_device("ios:abc123", DEFAULT_SYSTEM.replace("{tool_list}", ios_tool_list))

    assert "Target platform: iOS via Appium/WebDriverAgent" in ios_system
    assert "open_url" in ios_system
    assert "extract_articles" in ios_system
    assert "read_news" in ios_system
    assert "call search_apps/list_apps if you need to discover a bundle id" in ios_system
    assert "shell:" not in ios_system
    assert "launch_intent:" not in ios_system
    assert "toggle_overlay:" not in ios_system
    assert "open_camera:" in ios_system
    assert "standard Android intents" not in ios_system
    assert "camera package name" not in ios_system
    assert "Use search_apps to find the package name" not in ios_system
    assert "Android-only concepts" in ios_system

    android_system = system_prompt_for_device(
        "emulator-5554",
        DEFAULT_SYSTEM.replace("{tool_list}", tool_prompt_list(tools_for_device("emulator-5554"))),
    )
    assert "Target platform: Android via ADB/Portal" in android_system
    assert "shell:" in android_system
    assert "get_current_url:" not in android_system


def test_platform_context_for_ios_and_android():
    assert "iOS via Appium/WebDriverAgent" in platform_context("ios:abc123")
    assert "discover a bundle id" in platform_context("ios:abc123")
    assert "Android via ADB/Portal" in platform_context("emulator-5554")


def test_openai_tool_schema_is_filtered_by_device():
    ios_names = {tool["function"]["name"] for tool in openai_tools_for_device("ios:abc123")}
    android_names = {tool["function"]["name"] for tool in openai_tools_for_device("emulator-5554")}

    assert "open_url" in ios_names
    assert "list_devices" in ios_names
    assert "device_health" in ios_names
    assert "fix_device_health" in ios_names
    assert "shell" not in ios_names
    assert "press_back" in ios_names
    assert "press_home" in ios_names
    assert "type_unicode" in ios_names
    assert "get_screen_xml" in ios_names
    assert "run_workflow" in ios_names
    assert "run_action" in ios_names
    assert "create_skill" in ios_names
    assert "lookup_lead" in ios_names
    assert "list_unread_leads" in ios_names
    assert "get_current_url" in ios_names
    assert "read_news" in ios_names
    assert "shell" in android_names
    assert "list_devices" in android_names
    assert "device_health" in android_names
    assert "fix_device_health" in android_names
    assert "press_back" in android_names
    assert "press_home" in android_names
    assert "type_unicode" in android_names
    assert "get_screen_xml" in android_names
    assert "run_workflow" in android_names
    assert "run_action" in android_names
    assert "create_skill" in android_names
    assert "lookup_lead" in android_names
    assert "list_unread_leads" in android_names
    assert "get_current_url" not in android_names
    assert "read_news" not in android_names
