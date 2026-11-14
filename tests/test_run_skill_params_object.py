"""MCP run_skill accepts params/state_params as a JSON object or as JSON text (agents send both)."""

import asyncio

import pytest

from gitd import mcp_server


@pytest.fixture
def captured(monkeypatch):
    seen = {}

    def fake_engine_run(skill, action, params, device, **kwargs):
        seen["params"], seen["state_params"] = params, kwargs.get("state_params")

        class R:
            def as_dict(self):
                return {"success": True}

        return R()

    monkeypatch.setattr("gitd.skills.engine.run_action", fake_engine_run)
    monkeypatch.setattr("gitd.skills.engine.load_skill", lambda path: object())
    monkeypatch.setattr("gitd.skills.engine.fingerprint.check", lambda *a, **k: None, raising=False)
    return seen


def test_json_object_helper():
    assert mcp_server._json_object({"a": 1}, "params") == {"a": 1}
    assert mcp_server._json_object('{"a": 1}', "params") == {"a": 1}
    assert mcp_server._json_object("", "params") == {}
    assert mcp_server._json_object(None, "params") == {}
    with pytest.raises(ValueError, match="params must be a JSON object"):
        mcp_server._json_object("[1, 2]", "params")


def test_mcp_schema_accepts_an_object_for_params():
    tools = asyncio.run(mcp_server.mcp.list_tools())
    schema = next(t for t in tools if t.name == "run_skill").inputSchema["properties"]
    for field in ("params", "state_params"):
        types = {s.get("type") for s in schema[field].get("anyOf", [schema[field]])}
        assert {"string", "object"} <= types, (field, schema[field])
