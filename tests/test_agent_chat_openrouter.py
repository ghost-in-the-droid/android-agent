"""Regression tests for the OpenRouter provider loop fixes.

Two bugs found by ghost-video-editor while running the ghost CLI:
  1. creds read only os.environ, ignoring settings.openrouter_api_key.
  2. single-shot: executed tool_calls but never fed results back → any real task
     died after one round.
"""

import json
from types import SimpleNamespace

import pytest

from gitd.services import agent_chat


def _msg(content=None, tool_calls=None):
    return SimpleNamespace(content=content, tool_calls=tool_calls)


def _resp(message):
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _tool_call(cid, name, args):
    return SimpleNamespace(id=cid, function=SimpleNamespace(name=name, arguments=json.dumps(args)))


@pytest.fixture()
def stub_env(monkeypatch):
    """Neutralize device/screen/tool calls so only the loop logic is exercised."""
    monkeypatch.setattr(agent_chat, "get_screen_tree", lambda d: "")
    monkeypatch.setattr(agent_chat, "openai_tools_for_device", lambda d: [])
    monkeypatch.setattr(agent_chat, "system_prompt_for_device", lambda d: "sys")
    monkeypatch.setattr(agent_chat, "execute_tool", lambda name, args: f"ran {name}")


def _install_fake_openai(monkeypatch, responses, recorder=None):
    """Patch openai.OpenAI so create() returns queued responses in order."""
    seq = iter(responses)

    class FakeClient:
        def __init__(self, **kwargs):
            if recorder is not None:
                recorder.update(kwargs)
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: next(seq)))

    import openai

    monkeypatch.setattr(openai, "OpenAI", FakeClient)


def test_openrouter_multiturn_feeds_tool_results_back(stub_env, monkeypatch):
    # turn 1: model asks for a tool; turn 2: model answers with no tool → loop ends
    responses = [
        _resp(_msg(content=None, tool_calls=[_tool_call("c1", "tap", {"x": 1, "y": 2})])),
        _resp(_msg(content="all done", tool_calls=None)),
    ]
    _install_fake_openai(monkeypatch, responses)
    session = agent_chat.create_session(device="dev", provider="openrouter", model="anthropic/claude-sonnet-4")

    events = list(agent_chat._chat_openrouter(session, "do the thing"))
    types = [e["type"] for e in events]

    assert "tool_call" in types  # the tap was issued
    assert "tool_result" in types  # its result surfaced (was missing when single-shot)
    # the "all done" text is the 2nd model turn — it only happens if the loop
    # continued AFTER executing the tool (the single-shot bug ended before it).
    assert any(e["type"] == "text" and e["content"] == "all done" for e in events)
    assert types[-1] == "done"


def test_openrouter_stops_at_max_turns(stub_env, monkeypatch):
    # model never stops asking for tools → loop must terminate at MAX_TURNS, not hang
    always_tool = _resp(_msg(content=None, tool_calls=[_tool_call("c", "tap", {})]))
    _install_fake_openai(monkeypatch, [always_tool] * (agent_chat.MAX_TURNS + 5))
    session = agent_chat.create_session(device="dev", provider="openrouter", model="m")

    events = list(agent_chat._chat_openrouter(session, "loop"))
    tool_calls = sum(1 for e in events if e["type"] == "tool_call")
    assert tool_calls == agent_chat.MAX_TURNS  # bounded, not infinite
    assert events[-1]["type"] == "done"


def test_openrouter_creds_fall_back_to_settings(stub_env, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    from gitd.config import settings

    monkeypatch.setattr(settings, "openrouter_api_key", "sk-from-config", raising=False)
    recorder: dict = {}
    _install_fake_openai(monkeypatch, [_resp(_msg(content="hi", tool_calls=None))], recorder=recorder)

    session = agent_chat.create_session(device="dev", provider="openrouter", model="m")
    list(agent_chat._chat_openrouter(session, "hello"))
    assert recorder.get("api_key") == "sk-from-config"  # used config key, not empty env
