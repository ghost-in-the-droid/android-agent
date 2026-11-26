"""Tests for the MartLLM provider: it reuses the OpenRouter tool-calling loop
against MartLLM's OpenAI-compatible endpoint."""

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


def _install_fake_openai(monkeypatch, responses, recorder):
    """Patch openai.OpenAI; record client kwargs and every create() call."""
    seq = iter(responses)
    recorder.setdefault("calls", [])

    def create(**kw):
        recorder["calls"].append(kw)
        return next(seq)

    class FakeClient:
        def __init__(self, **kwargs):
            recorder.update(kwargs)
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))

    import openai

    monkeypatch.setattr(openai, "OpenAI", FakeClient)


def test_martllm_is_a_listed_provider():
    ids = [p["id"] for p in agent_chat.get_providers()]
    assert "martllm" in ids
    assert agent_chat.PROVIDERS["martllm"]["models"]


def test_martllm_uses_its_endpoint_and_env_key(stub_env, monkeypatch):
    monkeypatch.setenv("MARTLLM_API_KEY", "mk-from-env")
    recorder: dict = {}
    responses = [
        _resp(_msg(content=None, tool_calls=[_tool_call("c1", "tap", {"x": 1, "y": 2})])),
        _resp(_msg(content="all done", tool_calls=None)),
    ]
    _install_fake_openai(monkeypatch, responses, recorder)
    session = agent_chat.create_session(device="dev", provider="martllm", model="deepseek/deepseek-v4-flash")

    events = list(agent_chat.chat_turn(session, "do the thing"))

    assert recorder["base_url"] == "https://api.martllm.com/v1"
    assert recorder["api_key"] == "mk-from-env"
    assert [c["model"] for c in recorder["calls"]] == ["deepseek/deepseek-v4-flash"] * 2
    # the tool result is fed back before the second model turn
    assert recorder["calls"][1]["messages"][-1]["role"] == "tool"
    assert any(e["type"] == "text" and e["content"] == "all done" for e in events)
    assert events[-1]["type"] == "done"


def test_martllm_creds_fall_back_to_settings_and_default_model(stub_env, monkeypatch):
    monkeypatch.delenv("MARTLLM_API_KEY", raising=False)
    from gitd.config import settings

    monkeypatch.setattr(settings, "martllm_api_key", "mk-from-config", raising=False)
    recorder: dict = {}
    _install_fake_openai(monkeypatch, [_resp(_msg(content="hi", tool_calls=None))], recorder)

    session = agent_chat.create_session(device="dev", provider="martllm", model="")
    list(agent_chat._chat_martllm(session, "hello"))
    assert recorder["api_key"] == "mk-from-config"
    assert recorder["calls"][0]["model"] == "anthropic/claude-sonnet-4.6"
