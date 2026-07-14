"""Per-tool emoji rendering for the ghost CLI tool-call line."""

from gitd.ghostcli.run import _tool_emoji


def test_common_tools_have_distinct_emojis():
    assert _tool_emoji("tap") == "👆"
    assert _tool_emoji("type_text") == "⌨️"
    assert _tool_emoji("swipe") == "📜"
    assert _tool_emoji("launch_app") == "🚀"
    assert _tool_emoji("screenshot") == "📸"
    assert _tool_emoji("press_key") == "🎹"
    assert _tool_emoji("wait") == "⏳"
    assert _tool_emoji("shell") == "⚙️"
    assert _tool_emoji("open_url") == "🌐"
    assert _tool_emoji("get_screen_tree") == "🌲"


def test_unmapped_tool_falls_back_to_toolbox():
    assert _tool_emoji("some_future_tool") == "🧰"
    assert _tool_emoji("") == "🧰"


def test_tap_and_type_are_visually_different():
    # the whole point: the demo must not render a flat wall of identical glyphs
    assert _tool_emoji("tap") != _tool_emoji("type_text")
    assert _tool_emoji("screenshot") != _tool_emoji("launch_app")
