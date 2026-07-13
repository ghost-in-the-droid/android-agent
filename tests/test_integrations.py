"""Tests for the LangChain / LlamaIndex framework adapters.

The framework-agnostic core (build_ghost_tools) is tested with a mocked
execute_tool — no device, no frameworks. Both the LangChain and LlamaIndex
adapters are tested for real (langchain-core and llama-index-core are test deps),
so the "both frameworks are first-class" claim in the docs is CI-verified.
"""

import pytest

import gitd.services.agent_tools as agent_tools
from gitd.services.agent_tools import SAFE_DEVICE_TOOLS
from integrations._core import build_ghost_tools, pydantic_args_model

_DANGEROUS = {"shell", "run_skill"}


@pytest.fixture
def mock_execute(monkeypatch):
    calls = []

    def fake(name, args):
        calls.append((name, dict(args)))
        return f"{name}-ok"

    monkeypatch.setattr(agent_tools, "execute_tool", fake)
    return calls


# ── framework-agnostic core ──────────────────────────────────────────────────


def test_build_ghost_tools_binds_device_and_strips_it(mock_execute):
    tools = build_ghost_tools("emulator-5554")
    tap = next(t for t in tools if t.name == "tap")
    # device is bound, not an agent-supplied arg
    assert "device" not in tap.args_schema["properties"]
    assert "device" not in tap.args_schema.get("required", [])

    out = tap.run(x=540, y=300)
    assert out == "tap-ok"
    name, args = mock_execute[-1]
    assert name == "tap"
    assert args == {"x": 540, "y": 300, "device": "emulator-5554"}


def test_bound_device_overrides_any_passed_device(mock_execute):
    tools = build_ghost_tools("real-serial")
    tap = next(t for t in tools if t.name == "tap")
    tap.run(x=1, y=2, device="attacker-serial")  # must not win
    assert mock_execute[-1][1]["device"] == "real-serial"


def test_default_exposes_only_the_allow_list(mock_execute):
    """Fail-closed: by default, ONLY vetted allow-list tools are exposed —
    not merely 'everything except a dangerous deny-list'."""
    names = {t.name for t in build_ghost_tools("d")}
    assert names <= SAFE_DEVICE_TOOLS  # subset — nothing off the allow-list leaks
    assert _DANGEROUS.isdisjoint(names)
    assert "tap" in names and "launch_app" in names


def test_new_tool_is_not_auto_exposed(mock_execute, monkeypatch):
    """A tool added to the dispatch later must NOT appear until it's vetted onto
    the allow-list — this is what a deny-list would have failed open on."""
    monkeypatch.setattr(
        agent_tools,
        "TOOLS",
        agent_tools.TOOLS + [{"name": "some_new_risky_tool", "description": "x", "input_schema": {}}],
    )
    names = {t.name for t in build_ghost_tools("d")}
    assert "some_new_risky_tool" not in names


def test_include_dangerous_exposes_everything(mock_execute):
    names = {t.name for t in build_ghost_tools("d", include_dangerous=True)}
    assert "shell" in names and "run_skill" in names


def test_pydantic_args_model_respects_required_and_optional():
    model = pydantic_args_model(
        "tap",
        {"type": "object", "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}}, "required": ["x", "y"]},
    )
    inst = model(x=1, y=2)
    assert inst.x == 1 and inst.y == 2
    with pytest.raises(Exception):
        model(x=1)  # y required


# ── LangChain adapter (langchain-core is a test dep — runs, never skips) ──────


def test_langchain_tools_dispatch(mock_execute):
    from integrations.langchain import ghost_langchain_tools

    tools = ghost_langchain_tools("emulator-5554")
    names = {t.name for t in tools}
    assert "tap" in names
    assert _DANGEROUS.isdisjoint(names)

    tap = next(t for t in tools if t.name == "tap")
    # a LangChain agent calls .invoke with the structured args
    result = tap.invoke({"x": 540, "y": 300})
    assert result == "tap-ok"
    assert mock_execute[-1] == ("tap", {"x": 540, "y": 300, "device": "emulator-5554"})


# ── LlamaIndex adapter (llama-index-core is a test dep — runs, never skips) ────


def test_llamaindex_tools_dispatch(mock_execute):
    from llama_index.core.tools import FunctionTool

    from integrations.llamaindex import ghost_llamaindex_tools

    tools = ghost_llamaindex_tools("emulator-5554")
    assert all(isinstance(t, FunctionTool) for t in tools)
    names = {t.metadata.name for t in tools}
    assert "tap" in names
    assert _DANGEROUS.isdisjoint(names)  # shell/run_skill excluded, like LangChain

    tap = next(t for t in tools if t.metadata.name == "tap")
    # the LLM-facing tool spec must expose x/y and NOT the bound device
    schema = tap.metadata.fn_schema.model_json_schema()
    assert set(schema.get("properties", {})) == {"x", "y"}
    assert "function" in tap.metadata.to_openai_tool()

    # an agent runtime calls the tool like this
    result = tap.call(x=540, y=300)
    assert "tap-ok" in str(result)
    assert mock_execute[-1] == ("tap", {"x": 540, "y": 300, "device": "emulator-5554"})
