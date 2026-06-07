import ast
from pathlib import Path

from gitd.services.agent_tools import TOOLS, execute_tool
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
