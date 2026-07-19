"""M6: claude-code MCP parity for chat → skill.

Exercises the MCP-facing draft_skill / save_skill tools + the latest-conversation
resolver + the soft short-circuit in run_workflow. MCP tools are plain callables
(FastMCP's @mcp.tool() preserves the function); tests redirect the skills dir by
monkeypatching mcp_server.__file__, mirroring test_mcp_ios_skill_creation.py.
"""

import json

import pytest
import yaml

from gitd import mcp_server
from gitd.services.agent_chat import ChatMessage, ChatSession, save_session_to_db
from gitd.services.skills_from_chat import latest_conversation_id


@pytest.fixture(autouse=True)
def _tables():
    from gitd.models.base import Base, engine

    Base.metadata.create_all(engine)
    yield


def _seed_conversation(conv_id: str, device: str, messages):
    sess = ChatSession(id=conv_id, device=device)
    sess.messages = messages
    save_session_to_db(sess)


def test_latest_conversation_id_returns_newest():
    from gitd.models.base import SessionLocal
    from gitd.models.chat import ChatConversation

    db = SessionLocal()
    try:
        db.query(ChatConversation).filter_by(device="devLC").delete()
        db.add(ChatConversation(id="lc_old", device="devLC", created_at="2026-01-01T00:00:00", updated_at="2026-01-01T00:00:00"))
        db.add(ChatConversation(id="lc_new", device="devLC", created_at="2026-01-02T00:00:00", updated_at="2026-01-02T00:00:00"))
        db.commit()
    finally:
        db.close()
    assert latest_conversation_id("devLC") == "lc_new"
    assert latest_conversation_id("no-such-device") is None


def test_mcp_draft_skill_from_latest_conversation():
    _seed_conversation(
        "mcp_conv_1",
        "devMCP1",
        [
            ChatMessage(role="tool_call", tool_name="launch_app", tool_args={"package": "com.reddit.frontpage"}, content=""),
            ChatMessage(role="tool_result", tool_name="launch_app", content="Launched"),
            ChatMessage(role="tool_call", tool_name="tap", tool_args={"x": 5, "y": 6}, content=""),
            ChatMessage(role="tool_result", tool_name="tap", content="Tapped (5, 6)"),
        ],
    )
    out = json.loads(mcp_server.draft_skill("devMCP1"))
    assert [s["action"] for s in out["steps"]] == ["launch", "tap"]
    assert out["app_package"] == "com.reddit.frontpage"


def test_mcp_draft_skill_no_conversation():
    assert "No chat conversation" in mcp_server.draft_skill("ghost-device-none")


def test_mcp_save_soft_skill(tmp_path, monkeypatch):
    fake = tmp_path / "gitd" / "mcp_server.py"
    fake.parent.mkdir(parents=True)
    monkeypatch.setattr(mcp_server, "__file__", str(fake))
    msg = mcp_server.save_skill(
        device="devMCP2",
        name="Reddit Tips",
        kind="soft",
        app_package="com.reddit.frontpage",
        guidance="Dismiss the login wall before scrolling.",
    )
    assert "reddit_tips" in msg
    sdir = tmp_path / "gitd" / "skills" / "reddit_tips"
    meta = yaml.safe_load((sdir / "skill.yaml").read_text())
    assert meta["kind"] == "soft"
    assert "login wall" in (sdir / "guidance.md").read_text()


def test_mcp_save_hard_skill_from_conversation(tmp_path, monkeypatch):
    _seed_conversation(
        "mcp_conv_3",
        "devMCP3",
        [
            ChatMessage(role="tool_call", tool_name="launch_app", tool_args={"package": "com.x"}, content=""),
            ChatMessage(role="tool_result", tool_name="launch_app", content="Launched"),
            ChatMessage(role="tool_call", tool_name="press_home", tool_args={}, content=""),
            ChatMessage(role="tool_result", tool_name="press_home", content="Home"),
        ],
    )
    fake = tmp_path / "gitd" / "mcp_server.py"
    fake.parent.mkdir(parents=True)
    monkeypatch.setattr(mcp_server, "__file__", str(fake))
    msg = mcp_server.save_skill(device="devMCP3", name="from_conv_mcp")
    steps = json.loads((tmp_path / "gitd" / "skills" / "from_conv_mcp" / "workflows" / "recorded.json").read_text())
    assert [s["action"] for s in steps] == ["launch", "home"]


def test_mcp_run_workflow_soft_returns_guidance(tmp_path, monkeypatch):
    from gitd.services.skill_creation import create_soft_skill

    fake = tmp_path / "gitd" / "mcp_server.py"
    (tmp_path / "gitd" / "skills").mkdir(parents=True)
    monkeypatch.setattr(mcp_server, "__file__", str(fake))
    create_soft_skill(
        name="softmcp",
        guidance="Watch the captcha gate.",
        app_package="com.a",
        skills_dir=str(tmp_path / "gitd" / "skills"),
    )
    monkeypatch.setattr(mcp_server, "_load_skill_metadata", lambda s: {"kind": "soft", "app_package": "com.a"})
    monkeypatch.setattr(mcp_server, "skill_supports_device", lambda meta, dev: True)
    out = mcp_server.run_workflow("devMCP4", "softmcp", "recorded")
    assert "captcha gate" in out
