"""Tests for the LangChain / LlamaIndex framework adapters.

The framework-agnostic core (build_ghost_tools) is tested with a mocked
execute_tool — no device, no frameworks. The LangChain adapter is tested for
real (langchain_core is a test dep); the LlamaIndex adapter is importorskip'd.
"""

import pytest

import gitd.services.agent_tools as agent_tools
from integrations._core import DANGEROUS_TOOLS, build_ghost_tools, pydantic_args_model


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


def test_dangerous_tools_excluded_by_default(mock_execute):
    names = {t.name for t in build_ghost_tools("d")}
    assert DANGEROUS_TOOLS.isdisjoint(names)
    assert "tap" in names and "launch_app" in names


def test_dangerous_tools_opt_in(mock_execute):
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


# ── LangChain adapter (verified for real) ────────────────────────────────────


def test_langchain_tools_dispatch(mock_execute):
    pytest.importorskip("langchain_core")
    from integrations.langchain import ghost_langchain_tools

    tools = ghost_langchain_tools("emulator-5554")
    names = {t.name for t in tools}
    assert "tap" in names
    assert DANGEROUS_TOOLS.isdisjoint(names)

    tap = next(t for t in tools if t.name == "tap")
    # a LangChain agent calls .invoke with the structured args
    result = tap.invoke({"x": 540, "y": 300})
    assert result == "tap-ok"
    assert mock_execute[-1] == ("tap", {"x": 540, "y": 300, "device": "emulator-5554"})


# ── LlamaIndex adapter (skipped unless llama_index installed) ─────────────────


def test_llamaindex_tools_dispatch(mock_execute):
    pytest.importorskip("llama_index.core")
    from integrations.llamaindex import ghost_llamaindex_tools

    tools = ghost_llamaindex_tools("emulator-5554")
    names = {t.metadata.name for t in tools}
    assert "tap" in names
    tap = next(t for t in tools if t.metadata.name == "tap")
    result = tap.call(x=540, y=300)
    assert "tap-ok" in str(result)
    assert mock_execute[-1][1]["device"] == "emulator-5554"
