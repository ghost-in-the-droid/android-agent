"""AndroidWorld agent arms (tools/bench/agent_arm.py) against the fake bridge, a fake claude CLI and the
fake device. Pinned: both arms run per seed with the same prompt (goal + fixed sentence, no skill hint),
the before arm hides the skill tools and the after arm installs the skill, the transcript is scrubbed,
the artifact lands outside runs/ and verifications/ with the agent's model and a bench block, the
summary carries tokens and tool calls, and a rate limit stops the arm with exit 3.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests/fixtures/fake_google_maps"
FAKE_BRIDGE = REPO / "tests/fixtures/fake_aw_bridge.py"
FAKE_CLAUDE = REPO / "tests/fixtures/fake_claude_cli.py"


def load_module():
    spec = importlib.util.spec_from_file_location("agent_arm", REPO / "tools/bench/agent_arm.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def environment(tmp_path, monkeypatch):
    skill = tmp_path / "skillhub/ghost/google_maps"
    skill.parent.mkdir(parents=True)
    # Start with skill code only; real hub recordings are not test output.
    shutil.copytree(REPO / "skillhub/ghost/google_maps", skill, ignore=shutil.ignore_patterns("runs", "verifications"))
    # A checkout name may contain 'skill'; it must not become a false prompt hint.
    device_fixture = tmp_path / "device"
    shutil.copytree(FIXTURE, device_fixture)
    monkeypatch.setattr(sys.modules[__name__], "FIXTURE", device_fixture)
    monkeypatch.setenv("GHOST_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("GHOST_SKILLS_DIR", str(tmp_path / "installed"))
    monkeypatch.setenv("FAKE_AW_PARAMS", json.dumps({"query": "Fixture Cafe"}))
    monkeypatch.setenv("FAKE_CLAUDE_PROMPT_LOG", str(tmp_path / "prompts.jsonl"))
    monkeypatch.delenv("FAKE_CLAUDE_RATE_LIMIT", raising=False)
    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    original_run = subprocess.run

    def guarded_run(args, **kwargs):
        if args[0] in ("ssh-keygen", sys.executable) or str(args[0]).endswith("fake_claude_cli.py"):
            return original_run(args, **kwargs)
        pytest.fail("agent arm attempted an external operation: " + repr(args))

    monkeypatch.setattr(subprocess, "run", guarded_run)
    return skill, tmp_path


def common_args(skill, tmp_path, **extra):
    args = [
        str(skill),
        "--androidworld",
        "FakeTask",
        "--n",
        "1",
        "--device",
        "fake:" + str(FIXTURE),
        "--bridge-cmd",
        f"{sys.executable} {FAKE_BRIDGE}",
        "--agent-cmd",
        f"{sys.executable} {FAKE_CLAUDE}",
        "--out-dir",
        str(tmp_path / "agent-arm"),
        "--worktree",
        str(tmp_path),
        "--upstream-commit",
        "abc",
    ]
    for key, value in extra.items():
        args += [f"--{key}", str(value)]
    return args


def test_both_arms_run_with_identical_prompts_and_record_everything(environment, capsys):
    if not shutil.which("ssh-keygen"):
        pytest.skip("SSH signing unavailable")
    skill, tmp = environment
    module = load_module()
    rc = module.main(common_args(skill, tmp, arms="before,after_mcp", model="haiku"))
    out = capsys.readouterr().out
    assert rc == 0, out
    prompts = [json.loads(line) for line in (tmp / "prompts.jsonl").read_text().splitlines()]
    assert len(prompts) == 2 and prompts[0]["prompt"] == prompts[1]["prompt"]
    assert (
        "do FakeTask" in prompts[0]["prompt"]
        and "DONE" in prompts[0]["prompt"]
        and "skill" not in prompts[0]["prompt"].lower()
    )
    assert "--model" in prompts[0]["argv"] and "haiku" in prompts[0]["argv"] and "--max-turns" in prompts[0]["argv"]
    # Arm wiring: before hides the skill tools, after installs the skill into the MCP server's skills dir.
    envs = []
    for entry in prompts:
        cfg_path = entry["argv"][entry["argv"].index("--mcp-config") + 1]
        envs.append(json.loads(Path(cfg_path).read_text())["mcpServers"]["ghost"]["env"])
    assert envs[0]["GHOST_MCP_HIDE_TOOLS"].startswith("run_skill,") and envs[1]["GHOST_MCP_HIDE_TOOLS"] == ""
    assert (Path(envs[1]["GHOST_SKILLS_DIR"]) / "ghost/google_maps/@latest/skill.yaml").exists()
    assert not (Path(envs[0]["GHOST_SKILLS_DIR"]) / "ghost").exists()
    # Transcripts are scrubbed of the home directory and e-mail addresses.
    before = (tmp / "agent-arm/before-30.jsonl").read_text()
    assert str(Path.home()) not in before and "someone@example.com" not in before and "<email>" in before
    # Artifacts live outside runs/ and verifications/, carry the agent's model and a bench block with tokens.
    assert not (skill / "runs").exists() and not (skill / "verifications").exists()
    artifact = json.loads((skill / "bench/agent-runs/after_mcp-30.json").read_text())
    assert (
        artifact["model"] == "claude-haiku-4-5-20251001"
        and artifact["success"] is True
        and artifact["simulation"] is True
    )
    assert (
        artifact["bench"]["arm"] == "after_mcp"
        and artifact["bench"]["tokens"] == 180
        and artifact["bench"]["steps"] == 2
    )
    assert artifact["bench"]["trace_path"].endswith("agent-arm/after_mcp-30.jsonl")
    summary = json.loads((skill / "bench/androidworld.json").read_text())
    (task,) = summary["tasks"]
    assert set(task["arms"]) == {"before", "after_mcp"}
    assert task["arms"]["before"] == {**task["arms"]["before"], "passed": 1, "total": 1, "tokens_median": 180}
    assert "before: 1/1 passed" in out and "after_mcp: 1/1 passed" in out


def test_rate_limit_stops_the_arm_and_exits_3(environment, monkeypatch, capsys):
    skill, tmp = environment
    monkeypatch.setenv("FAKE_CLAUDE_RATE_LIMIT", "1")
    module = load_module()
    rc = module.main(common_args(skill, tmp, arms="before,after_mcp", n=2))
    out = capsys.readouterr().out
    assert rc == 3 and "BLOCKER" in out and "rate limit" in out
    # The first seed ran, the second seed and the second arm did not.
    assert (tmp / "agent-arm/before-30.jsonl").exists()
    assert not (tmp / "agent-arm/before-31.jsonl").exists() and not (tmp / "agent-arm/after_mcp-30.jsonl").exists()
    assert (
        not (skill / "bench/agent-runs/before-30.json").exists()
        or json.loads((skill / "bench/agent-runs/before-30.json").read_text())["success"] is False
    )


def test_parse_transcript_counts_tools_and_tokens():
    module = load_module()
    lines = [
        json.dumps({"type": "assistant", "message": {"model": "m", "content": [{"type": "tool_use", "name": "a"}]}}),
        "not json",
        json.dumps(
            {
                "type": "result",
                "subtype": "success",
                "is_error": False,
                "num_turns": 1,
                "result": "DONE",
                "usage": {"input_tokens": 1, "output_tokens": 2, "cache_read_input_tokens": 3},
            }
        ),
    ]
    parsed = module.parse_transcript(lines)
    assert (parsed["tool_calls"], parsed["model"], parsed["tokens"], parsed["rate_limited"]) == (1, "m", 6, False)
    limited = module.parse_transcript(
        [json.dumps({"type": "result", "is_error": True, "result": "Rate limit exceeded"})]
    )
    assert limited["rate_limited"] is True
    # A max-turns error whose token counts happen to contain "429" is not a rate limit (seen live: 75429 cache tokens).
    turns = module.parse_transcript(
        [
            json.dumps(
                {
                    "type": "result",
                    "is_error": True,
                    "subtype": "error_max_turns",
                    "result": None,
                    "usage": {"cache_creation_input_tokens": 75429, "input_tokens": 50},
                }
            )
        ]
    )
    assert turns["rate_limited"] is False and turns["tokens"] == 75479


def test_find_installed_sees_hub_skills(tmp_path, monkeypatch):
    monkeypatch.setenv("GHOST_SKILLS_DIR", str(tmp_path / "installed"))
    module = load_module()
    ref = module.install_local(REPO / "skillhub/androidworld/pro-expense", tmp_path / "installed")
    assert ref == "androidworld/pro-expense"
    from gitd.skills.engine.find import find_installed, installed_hub_dirs

    assert [r for r, _ in installed_hub_dirs()] == ["androidworld/pro-expense"]
    hits = find_installed("log the reimbursable transactions from my_expenses.txt in pro expense", 3)
    assert hits and hits[0]["skill"] == "androidworld/pro-expense" and hits[0]["source"] == "hub"
    assert hits[0]["action"] == "expense_add_multiple_from_markor"


def test_mcp_hide_tools_removes_only_listed_tools(monkeypatch):
    import asyncio

    import gitd.mcp_server as server

    # Exercise removal against an isolated registry so later profile tests
    # still see the complete tool set.
    manager = server.mcp._tool_manager
    monkeypatch.setattr(manager, "_tools", manager._tools.copy())
    before = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert {"run_skill", "find_skill", "tap"} <= before
    removed = server.hide_tools("run_skill, find_skill,nope")
    after = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert removed == ["run_skill", "find_skill"] and "run_skill" not in after and "tap" in after
