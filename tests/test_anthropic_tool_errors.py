"""Regression test for the Anthropic provider's tool-error handling.

Once Device.adb raises ADBError on a failed adb call, a tool invocation
(tap/swipe/launch_app) against an offline/unauthorized device raises. Every
provider loop must turn that into a tool_result the model can react to — NOT
let it propagate uncaught and break the SSE stream. _chat_anthropic is the
default provider and was the one loop that did not wrap execute_tool.
"""

import pytest

anthropic = pytest.importorskip("anthropic")

from gitd.services import agent_chat  # noqa: E402
from gitd.services.agent_chat import ChatSession, _chat_anthropic  # noqa: E402


class _Block:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Resp:
    def __init__(self, content):
        self.content = content


def test_anthropic_tool_error_yields_result_not_raise(monkeypatch):
    # Turn 1: model asks to tap. Turn 2: plain text → ends the loop.
    responses = iter(
        [
            _Resp([_Block(type="tool_use", name="tap", input={"x": 1, "y": 2}, id="tu_1")]),
            _Resp([_Block(type="text", text="done")]),
        ]
    )

    class _FakeMessages:
        def create(self, **kwargs):
            return next(responses)

    class _FakeClient:
        def __init__(self, *a, **k):
            self.messages = _FakeMessages()

    monkeypatch.setattr(anthropic, "Anthropic", _FakeClient)

    # Simulate an offline-device failure surfacing from execute_tool (ADBError
    # is a RuntimeError subclass; any Exception must be caught the same way).
    def _boom(name, args):
        raise RuntimeError("adb shell input tap failed (exit 1): device 'x' not found")

    monkeypatch.setattr(agent_chat, "execute_tool", _boom)

    session = ChatSession(id="s1", device="offline-serial", provider="anthropic", model="claude-sonnet-4-20250514")
    session.auto_screenshot = False  # skip device I/O in _build_vision_content

    # The whole point: draining the generator must NOT raise.
    events = list(_chat_anthropic(session, "tap the button"))

    tool_results = [e for e in events if e.get("type") == "tool_result"]
    assert tool_results, "expected a tool_result event even when the tool failed"
    assert "Tool error" in tool_results[0]["result"]
    assert "device 'x' not found" in tool_results[0]["result"]

    # Protocol stays valid: the assistant tool_use turn must be followed by a
    # user turn carrying a matching tool_result for tool_use_id tu_1.
    tool_result_turns = [
        m
        for m in session.api_messages
        if m["role"] == "user"
        and isinstance(m["content"], list)
        and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in m["content"])
    ]
    assert tool_result_turns, "a tool_result must be sent back for the tool_use"
    ids = [b["tool_use_id"] for m in tool_result_turns for b in m["content"] if b.get("type") == "tool_result"]
    assert "tu_1" in ids
