import ast
import json
from pathlib import Path

from gitd.services.agent_chat import DEFAULT_SYSTEM, openai_tools_for_device, platform_context, system_prompt_for_device
from gitd.services.agent_tools import TOOLS, execute_tool, tool_prompt_list, tools_for_device
from gitd.services.tool_platforms import TOOL_PLATFORM_SUPPORT, platform_error, supports_platform, tool_platform_info


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


def test_every_agent_and_mcp_tool_has_platform_classification():
    agent_names = {tool["name"] for tool in TOOLS}
    names = agent_names | _mcp_tool_names()

    missing = sorted(name for name in names if name not in TOOL_PLATFORM_SUPPORT)

    assert missing == []


def test_platform_classifications_have_stable_ios_semantics():
    assert supports_platform("screenshot", "ios") is True
    assert supports_platform("open_url", "ios") is True
    assert supports_platform("device_health", "ios") is True
    assert supports_platform("device_health", "android") is True
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

    assert tool_platform_info("shell").support == "android_only"
    assert tool_platform_info("device_health").support == "cross_platform"
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

    shell = execute_tool("shell", {"device": "ios:abc123", "command": "ls"})
    clipboard = execute_tool("clipboard_get", {"device": "ios:abc123"})
    notifications = json.loads(execute_tool("get_notifications", {"device": "ios:abc123"}))
    opened = execute_tool("open_notifications", {"device": "ios:abc123"})
    cleared = execute_tool("clear_notifications", {"device": "ios:abc123"})
    health = json.loads(execute_tool("device_health", {"device": "ios:abc123"}))
    unknown = execute_tool("does_not_exist", {"device": "ios:abc123"})

    assert shell.startswith("ERROR: shell is Android-only")
    assert clipboard == "ios clipboard"
    assert notifications == [{"title": "Slack", "text": "New message", "platform": "ios"}]
    assert opened == "Notification shade opened"
    assert cleared == "Notifications cleared"
    assert health["connection"]["status"] == "wda_signing_failed"
    assert health["recommended_fix"] == "fix_wda_signing"
    assert unknown == "Unknown tool: does_not_exist"


def test_tools_for_device_filters_by_platform():
    ios_names = {tool["name"] for tool in tools_for_device("ios:abc123")}
    android_names = {tool["name"] for tool in tools_for_device("emulator-5554")}

    assert "open_url" in ios_names
    assert "device_health" in ios_names
    assert "extract_articles" in ios_names
    assert "shell" not in ios_names
    assert "launch_intent" not in ios_names
    assert "clipboard_get" in ios_names
    assert "clipboard_set" in ios_names
    assert "paste_text" in ios_names
    assert "get_current_url" in ios_names
    assert "list_apps" in ios_names
    assert "search_apps" in ios_names
    assert "list_packages" in ios_names
    assert "app_state" in ios_names
    assert "get_notifications" in ios_names
    assert "open_notifications" in ios_names
    assert "clear_notifications" in ios_names
    assert "open_camera" in ios_names
    assert "read_news" in ios_names

    assert "shell" in android_names
    assert "device_health" in android_names
    assert "app_state" in android_names
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

    monkeypatch.setattr("gitd.services.agent_tools.get_device", lambda device: FakeIOSDevice())

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


def test_platform_prompts_do_not_offer_android_only_tools_to_ios():
    ios_tools = tools_for_device("ios:abc123")
    ios_tool_list = tool_prompt_list(ios_tools)
    ios_system = system_prompt_for_device("ios:abc123", DEFAULT_SYSTEM.replace("{tool_list}", ios_tool_list))

    assert "Target platform: iOS via Appium/WebDriverAgent" in ios_system
    assert "open_url" in ios_system
    assert "extract_articles" in ios_system
    assert "read_news" in ios_system
    assert "shell:" not in ios_system
    assert "launch_intent:" not in ios_system
    assert "open_camera:" in ios_system
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
    assert "Android via ADB/Portal" in platform_context("emulator-5554")


def test_openai_tool_schema_is_filtered_by_device():
    ios_names = {tool["function"]["name"] for tool in openai_tools_for_device("ios:abc123")}
    android_names = {tool["function"]["name"] for tool in openai_tools_for_device("emulator-5554")}

    assert "open_url" in ios_names
    assert "device_health" in ios_names
    assert "shell" not in ios_names
    assert "get_current_url" in ios_names
    assert "read_news" in ios_names
    assert "shell" in android_names
    assert "device_health" in android_names
    assert "get_current_url" not in android_names
    assert "read_news" not in android_names
