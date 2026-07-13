"""Tests for chat_turn provider dispatch.

Guards the provider-routing table in chat_turn — in particular that the
`claude-code` provider still delegates to the live `chat_claude_code`
(in agent_chat_claude_code.py) after the dead in-module `_chat_claude_code`
duplicate was removed.
"""

import gitd.services.agent_chat as agent_chat
import gitd.services.agent_chat_claude_code as cc
from gitd.services.agent_chat import ChatSession, chat_turn


def test_dead_chat_claude_code_removed():
    """The ~180-LOC dead duplicate must stay gone — chat_turn never used it."""
    assert not hasattr(agent_chat, "_chat_claude_code")


def test_chat_turn_routes_claude_code_to_live_module(monkeypatch):
    """provider='claude-code' delegates to agent_chat_claude_code.chat_claude_code."""
    calls = {}

    def fake_chat_claude_code(session, message):
        calls["session"] = session
        calls["message"] = message
        yield {"type": "text", "content": "routed"}

    # chat_turn imports the symbol at call time, so patch it on the module.
    monkeypatch.setattr(cc, "chat_claude_code", fake_chat_claude_code)

    session = ChatSession(id="t1", device="emulator-5554", provider="claude-code")
    events = list(chat_turn(session, "hello"))

    assert calls["message"] == "hello"
    assert {"type": "text", "content": "routed"} in events


def test_chat_turn_unknown_provider_yields_error():
    session = ChatSession(id="t2", device="emulator-5554", provider="bogus-provider")
    events = list(chat_turn(session, "hi"))
    assert events == [{"type": "error", "content": "Unknown provider: bogus-provider"}]
