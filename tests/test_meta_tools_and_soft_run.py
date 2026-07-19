"""M5: chat-loop meta-tool intercept + soft-skill retrieval via agent tools."""

import json

import gitd.routers.skills as skills_router
import gitd.services.agent_chat as agent_chat
import gitd.services.agent_tools as agent_tools
import gitd.services.skills_from_chat as sfc
from gitd.services.agent_chat import ChatSession, _dispatch_tool, maybe_handle_meta_tool
from gitd.services.skill_creation import create_soft_skill


def _session():
    return ChatSession(id="conv-x", device="dev1")


def test_meta_handler_passes_through_normal_tools():
    assert maybe_handle_meta_tool(_session(), "tap", {"x": 1, "y": 2}) is None


def test_dispatch_routes_normal_tool_to_execute_tool(monkeypatch):
    calls = {}

    def _fake_exec(n, a):
        calls["hit"] = (n, a)
        return "ok"

    monkeypatch.setattr(agent_chat, "execute_tool", _fake_exec)
    out = _dispatch_tool(_session(), "tap", {"x": 1})
    assert out == "ok" and calls["hit"] == ("tap", {"x": 1})


def test_draft_skill_meta_tool(monkeypatch):
    monkeypatch.setattr(agent_chat, "save_session_to_db", lambda s: None)
    monkeypatch.setattr(sfc, "draft_hard_skill", lambda cid: {"conversation_id": cid, "steps": [{"action": "home"}]})
    out = maybe_handle_meta_tool(_session(), "draft_skill", {"device": "dev1"})
    data = json.loads(out)
    assert data["conversation_id"] == "conv-x" and data["steps"] == [{"action": "home"}]


def test_save_skill_meta_tool_forwards_args(monkeypatch):
    monkeypatch.setattr(agent_chat, "save_session_to_db", lambda s: None)
    captured = {}

    def _commit(**kw):
        captured.update(kw)
        return {"ok": True, "skill": kw["name"]}

    monkeypatch.setattr(sfc, "commit_skill", _commit)
    out = maybe_handle_meta_tool(
        _session(),
        "save_skill",
        {"kind": "soft", "name": "Reddit Tips", "guidance": "watch out", "app_package": "com.reddit.frontpage"},
    )
    assert json.loads(out)["ok"] is True
    assert captured["kind"] == "soft"
    assert captured["name"] == "reddit_tips"  # normalized snake_case
    assert captured["conversation_id"] == "conv-x"


def test_meta_tools_exposed_to_agent():
    names = {t["name"] for t in agent_tools.tools_for_device("android-serial-xyz")}
    assert {"draft_skill", "save_skill"} <= names


def test_list_skills_surfaces_kind_and_guidance(tmp_path, monkeypatch):
    create_soft_skill(name="softy", guidance="be careful", app_package="com.a", skills_dir=str(tmp_path))
    monkeypatch.setattr(skills_router, "_SKILLS_DIR", tmp_path)
    out = json.loads(agent_tools.execute_tool("list_skills", {}))
    entry = next(e for e in out if e["name"] == "softy")
    assert entry["kind"] == "soft" and entry["guidance_available"] is True


def test_run_skill_soft_returns_guidance(tmp_path, monkeypatch):
    create_soft_skill(name="softz", guidance="Dismiss the login wall first.", app_package="com.a", skills_dir=str(tmp_path))
    monkeypatch.setattr(skills_router, "_SKILLS_DIR", tmp_path)
    # skip device platform resolution
    monkeypatch.setattr(agent_tools, "skill_supports_device", lambda meta, dev: True)
    out = agent_tools.execute_tool("run_skill", {"skill": "softz", "workflow": "recorded", "device": "dev1"})
    assert "login wall" in out and "guidance" in out.lower()
