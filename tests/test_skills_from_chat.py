"""M4: chat → skill orchestration service."""

from types import SimpleNamespace

import yaml

import gitd.services.agent_chat as agent_chat
from gitd.services.skills_from_chat import commit_skill, draft_hard_skill


def _msg(role, tool_name="", tool_args=None, content="", tool_id=""):
    return {"role": role, "tool_name": tool_name, "tool_args": tool_args or {}, "content": content, "tool_id": tool_id}


def _fake_session(messages):
    return SimpleNamespace(messages=messages)


def test_draft_hard_skill_distils_and_guesses_package(monkeypatch):
    trace = [
        _msg("tool_call", "launch_app", {"package": "com.reddit.frontpage"}),
        _msg("tool_result", content="Launched"),
        _msg("tool_call", "tap", {"x": 5, "y": 6}),
        _msg("tool_result", content="Tapped (5, 6)"),
        _msg("tool_call", "screenshot", {}),  # noise → dropped
        _msg("tool_result", content="<img>"),
    ]
    monkeypatch.setattr(agent_chat, "load_conversation", lambda cid: _fake_session(trace))
    draft = draft_hard_skill("conv1")
    assert draft["step_count"] == 2
    assert [s["action"] for s in draft["steps"]] == ["launch", "tap"]
    assert draft["app_package"] == "com.reddit.frontpage"
    assert "2 steps" in draft["summary"]


def test_draft_missing_conversation_raises(monkeypatch):
    monkeypatch.setattr(agent_chat, "load_conversation", lambda cid: None)
    try:
        draft_hard_skill("nope")
        assert False, "expected ValueError"
    except ValueError as e:
        assert "not found" in str(e)


def test_commit_soft_skill(tmp_path):
    res = commit_skill(
        kind="soft",
        name="reddit_tips",
        app_package="com.reddit.frontpage",
        description="Reddit gotchas",
        guidance="Dismiss the login wall before scrolling.",
        skills_dir=str(tmp_path),
    )
    assert res["kind"] == "soft"
    meta = yaml.safe_load((tmp_path / "reddit_tips" / "skill.yaml").read_text())
    assert meta["kind"] == "soft" and meta["description"] == "Reddit gotchas"
    assert "login wall" in (tmp_path / "reddit_tips" / "guidance.md").read_text()


def test_commit_hard_skill_with_steps(tmp_path):
    res = commit_skill(
        kind="hard",
        name="open_reddit",
        app_package="com.reddit.frontpage",
        description="Open Reddit and tap search",
        steps=[{"action": "launch", "package": "com.reddit.frontpage"}, {"action": "tap", "x": 1, "y": 2}],
        skills_dir=str(tmp_path),
    )
    assert res["steps"] == 2
    meta = yaml.safe_load((tmp_path / "open_reddit" / "skill.yaml").read_text())
    assert meta["kind"] == "hard" and meta["description"] == "Open Reddit and tap search"


def test_commit_hard_skill_from_conversation(monkeypatch, tmp_path):
    trace = [
        _msg("tool_call", "launch_app", {"package": "com.x"}),
        _msg("tool_result", content="Launched"),
        _msg("tool_call", "press_home", {}),
        _msg("tool_result", content="Home"),
    ]
    monkeypatch.setattr(agent_chat, "load_conversation", lambda cid: _fake_session(trace))
    res = commit_skill(kind="hard", name="from_conv", conversation_id="c9", skills_dir=str(tmp_path))
    assert res["steps"] == 2
    steps = __import__("json").loads((tmp_path / "from_conv" / "workflows" / "recorded.json").read_text())
    assert [s["action"] for s in steps] == ["launch", "home"]
    # app_package inferred from the trace
    assert yaml.safe_load((tmp_path / "from_conv" / "skill.yaml").read_text())["app_package"] == "com.x"


def test_commit_soft_requires_guidance(tmp_path):
    try:
        commit_skill(kind="soft", name="x", skills_dir=str(tmp_path))
        assert False, "expected ValueError"
    except ValueError:
        pass
