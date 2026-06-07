import ast
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
    assert supports_platform("get_current_url", "ios") is True
    assert supports_platform("get_current_url", "android") is False
    assert supports_platform("shell", "ios") is False
    assert supports_platform("clipboard_get", "ios") is False

    assert tool_platform_info("shell").support == "android_only"
    assert tool_platform_info("clipboard_get").support == "ios_planned"
    assert platform_error("clipboard_get", "ios")["support"] == "ios_planned"


def test_execute_tool_uses_platform_registry_for_ios_errors():
    shell = execute_tool("shell", {"device": "ios:abc123", "command": "ls"})
    clipboard = execute_tool("clipboard_get", {"device": "ios:abc123"})
    unknown = execute_tool("does_not_exist", {"device": "ios:abc123"})

    assert shell.startswith("ERROR: shell is Android-only")
    assert clipboard.startswith("ERROR: clipboard_get is not supported for ios yet")
    assert unknown == "Unknown tool: does_not_exist"


def test_tools_for_device_filters_by_platform():
    ios_names = {tool["name"] for tool in tools_for_device("ios:abc123")}
    android_names = {tool["name"] for tool in tools_for_device("emulator-5554")}

    assert "open_url" in ios_names
    assert "extract_articles" in ios_names
    assert "shell" not in ios_names
    assert "launch_intent" not in ios_names
    assert "clipboard_get" not in ios_names
    assert "get_current_url" in ios_names

    assert "shell" in android_names
    assert "get_current_url" not in android_names


def test_platform_prompts_do_not_offer_android_only_tools_to_ios():
    ios_tools = tools_for_device("ios:abc123")
    ios_tool_list = tool_prompt_list(ios_tools)
    ios_system = system_prompt_for_device("ios:abc123", DEFAULT_SYSTEM.replace("{tool_list}", ios_tool_list))

    assert "Target platform: iOS via Appium/WebDriverAgent" in ios_system
    assert "open_url" in ios_system
    assert "extract_articles" in ios_system
    assert "shell:" not in ios_system
    assert "launch_intent:" not in ios_system
    assert "open_camera:" not in ios_system
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
    assert "shell" not in ios_names
    assert "get_current_url" in ios_names
    assert "shell" in android_names
    assert "get_current_url" not in android_names
