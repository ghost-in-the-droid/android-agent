"""Tests for Ollama tool parsing and provider config."""

from gitd.services.agent_chat import (
    PROVIDERS,
    _parse_tool_calls,
    normalize_tool_call,
)


def test_providers_ollama_has_models():
    """Ollama provider should have a pre-filled model list."""
    ollama = PROVIDERS["ollama"]
    assert len(ollama["models"]) >= 5
    assert "llama3.2:3b" in ollama["models"]
    assert "gemma3:4b" in ollama["models"]


def test_parse_tool_calls_basic():
    text = '''I'll take a screenshot.
```tool
{"tool": "screenshot", "args": {"device": "emulator-5554"}}
```'''
    calls = _parse_tool_calls(text)
    assert len(calls) == 1
    assert calls[0]["tool"] == "screenshot"
    assert calls[0]["args"]["device"] == "emulator-5554"


def test_parse_tool_calls_multiple():
    text = '''Let me check the screen and tap.
```tool
{"tool": "get_screen_tree", "args": {"device": "emulator-5554"}}
```
Now I'll tap.
```tool
{"tool": "tap", "args": {"device": "emulator-5554", "x": 540, "y": 1200}}
```'''
    calls = _parse_tool_calls(text)
    assert len(calls) == 2
    assert calls[0]["tool"] == "get_screen_tree"
    assert calls[1]["tool"] == "tap"
    assert calls[1]["args"]["x"] == 540


def test_parse_tool_calls_doubled_braces():
    """Some models (gemma3) wrap JSON in {{ ... }} — should handle gracefully."""
    text = '```tool\n{{"tool": "tap", "args": {{"x": 100, "y": 200}}}}\n```'
    calls = _parse_tool_calls(text)
    assert len(calls) == 1
    assert calls[0]["tool"] == "tap"
    assert calls[0]["args"]["x"] == 100


def test_parse_tool_calls_no_tools():
    text = "I don't need any tools for this. The answer is 42."
    calls = _parse_tool_calls(text)
    assert len(calls) == 0


def test_parse_tool_calls_invalid_json():
    text = '```tool\n{not valid json}\n```'
    calls = _parse_tool_calls(text)
    assert len(calls) == 0


def test_parse_tool_calls_missing_tool_key():
    """Valid JSON but missing 'tool' key should be ignored."""
    text = '```tool\n{"action": "screenshot", "args": {}}\n```'
    calls = _parse_tool_calls(text)
    assert len(calls) == 0


def test_parse_tool_calls_flat_shape():
    """Flat shape (ghost-gemma trained) — args are siblings of 'tool', no nested args."""
    text = '```tool\n{"tool": "launch_app", "package": "com.android.settings"}\n```'
    calls = _parse_tool_calls(text)
    assert len(calls) == 1
    assert calls[0]["tool"] == "launch_app"
    assert calls[0]["package"] == "com.android.settings"


def test_normalize_tool_call_nested():
    """Canonical shape: {"tool": "X", "args": {...}} → args come from the nested dict."""
    name, args = normalize_tool_call({"tool": "tap", "args": {"x": 540, "y": 1200}})
    assert name == "tap"
    assert args == {"x": 540, "y": 1200}


def test_normalize_tool_call_flat():
    """Flat shape (ghost-gemma trained): kwargs are siblings of 'tool'.

    Regression guard for the on-device path silently dropping every flat arg
    (only 'device' survived) — the exact model the feature was trained on.
    """
    name, args = normalize_tool_call({"tool": "launch_app", "package": "com.foo"})
    assert name == "launch_app"
    assert args == {"package": "com.foo"}


def test_normalize_tool_call_does_not_mutate_input():
    """Returned args must be a fresh dict — callers setdefault('device', ...) on it."""
    call = {"tool": "tap", "args": {"x": 1}}
    _, args = normalize_tool_call(call)
    args["device"] = "emulator-5554"
    assert "device" not in call["args"]


def test_normalize_tool_call_empty():
    """Missing 'tool' / no args → empty name, empty args (no crash)."""
    name, args = normalize_tool_call({})
    assert name == ""
    assert args == {}
