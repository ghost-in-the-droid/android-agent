"""A/B bench guards: find_skill points the agent at run_skill, run_action hands hub refs to run_skill,
the agent CLI runs isolated (empty cwd, project settings, inline MCP config over ssh), transcripts yield
LLM-call and UI-action counts, and a missing task app is detected before and after an episode.
"""

from __future__ import annotations

import importlib.util
import json
import shlex
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def load_module():
    spec = importlib.util.spec_from_file_location("agent_arm", REPO / "tools/bench/agent_arm.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_find_skill_hits_name_run_skill(monkeypatch):
    import gitd.mcp_server as server
    import gitd.skills.engine.find as find

    monkeypatch.setattr(find, "find_installed", lambda intent, top: [{"skill": "a/b", "action": "x", "source": "hub"}])
    hits = json.loads(server.find_skill("anything"))
    assert hits[0]["run_with"] == "run_skill"
    assert "run_skill(" in server.find_skill.__doc__ and "run_action(" not in server.find_skill.__doc__


def test_run_action_hands_hub_refs_to_run_skill(monkeypatch):
    import gitd.mcp_server as server

    calls = []
    monkeypatch.setattr(
        server,
        "run_skill",
        lambda name, action, params="{}", device="": calls.append((name, action, params, device)) or "ran",
    )
    assert server.run_action("emulator-5554", "androidworld/pro-expense", "expense_add_single", '{"rows": []}') == "ran"
    assert calls == [("androidworld/pro-expense", "expense_add_single", '{"rows": []}', "emulator-5554")]


def test_remote_agent_command_is_isolated_and_carries_mcp_inline(tmp_path):
    module = load_module()
    config = module.mcp_config(
        tmp_path / "mcp.json",
        worktree=tmp_path,
        serial="emulator-5554",
        skills_dir=tmp_path / "s",
        hide="",
        mcp_host="mcp-host.example",
    )
    server = json.loads(config.read_text())["mcpServers"]["ghost"]
    assert (
        server["command"] == "ssh"
        and server["args"][-2] == "mcp-host.example"
        and "-m gitd.mcp_server" in server["args"][-1]
    )
    command = module.claude_command(
        "claude", model="haiku", max_turns=5, config=config, agent_host="agent-host.example"
    )
    assert command[:4] == ["ssh", "-o", "BatchMode=yes", "agent-host.example"]
    remote = command[-1]
    assert remote.startswith('cd "$(mktemp -d)" && ')
    args = shlex.split(remote.split("&& ", 1)[1])
    assert args[args.index("--setting-sources") + 1] == "project" and "--no-session-persistence" in args
    assert json.loads(args[args.index("--mcp-config") + 1]) == json.loads(config.read_text())


def test_transcript_counts_llm_calls_ui_actions_and_tool_errors():
    module = load_module()

    def assistant(mid, *tools):
        return json.dumps(
            {
                "type": "assistant",
                "message": {
                    "id": mid,
                    "model": "claude-haiku-x",
                    "content": [
                        {"type": "tool_use", "id": f"{mid}{i}", "name": f"mcp__ghost__{t}", "input": {}}
                        for i, t in enumerate(tools)
                    ],
                },
            }
        )

    lines = [
        json.dumps({"type": "system", "subtype": "init", "claude_code_version": "9.9.9"}),
        assistant("m1", "get_screen_tree"),
        assistant("m1", "tap"),  # one API call streamed as two events
        assistant("m2", "type_text", "swipe"),
        json.dumps(
            {
                "type": "user",
                "message": {"content": [{"type": "tool_result", "content": "ERROR: package x is not installed."}]},
            }
        ),
        assistant("m3", "run_skill", "press_back"),
        json.dumps({"type": "result", "num_turns": 3, "usage": {"input_tokens": 10, "output_tokens": 5}}),
    ]
    out = module.parse_transcript(lines)
    assert out["llm_calls"] == 3 and out["cli_version"] == "9.9.9" and out["tool_errors"] == 1
    assert out["ui_actions"] == {"tap": 1, "type": 1, "swipe": 1, "key": 1, "launch": 0, "total": 4}
    assert out["skill_calls"] == ["mcp__ghost__run_skill"] and out["tokens"] == 15


def test_missing_packages_reads_pm_path(monkeypatch):
    module = load_module()

    class Proc:
        def __init__(self, stdout):
            self.stdout = stdout

    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda cmd, **_: Proc("package:/data/app/base.apk\n" if cmd[-1] == "com.arduia.expense" else ""),
    )
    assert module.missing_packages("emulator-5554", ["com.arduia.expense", "net.gsantner.markor"]) == [
        "net.gsantner.markor"
    ]
    assert module.missing_packages("fake:pixel", ["net.gsantner.markor"]) == []


def test_token_cap_kills_the_episode(tmp_path):
    module = load_module()
    script = tmp_path / "chatty.py"
    script.write_text(
        "import json, sys, time\nsys.stdin.read()\n"
        "for i in range(100):\n"
        '    print(json.dumps({"type": "assistant", "message": {"id": f"m{i}", "usage": {"input_tokens": 1000}, "content": []}}), flush=True)\n'
        "    time.sleep(0.05)\n"
    )
    out = module.run_agent(["python3", str(script)], "go", tmp_path / "t.jsonl", timeout_s=60, token_cap=5000)
    assert out["over_cap"] and not out["timed_out"] and 5000 < out["tokens"] < 100_000


def load_report():
    spec = importlib.util.spec_from_file_location("ab_report", REPO / "tools/bench/ab_report.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_report_stats_match_reference_values():
    r = load_report()
    assert r.mcnemar_exact(0, 3) == 0.25 and r.mcnemar_exact(0, 5) == 0.0625 and r.mcnemar_exact(2, 2) == 1.0
    lo, hi = r.wilson(3, 3)
    assert abs(lo - 0.4385) < 1e-3 and hi == 1.0 and r.wilson(0, 0) == (0.0, 0.0)


def test_report_pairs_on_seed_and_skips_cut_short_episodes():
    r = load_report()
    cells = [{"task_id": "t", "arm": "before", "seed": s, "success": False, "tokens": 1000} for s in (1, 2, 3)]
    cells += [{"task_id": "t", "arm": "after_mcp", "seed": s, "success": True, "tokens": 100} for s in (1, 2)]
    cells += [{"task_id": "t", "arm": "after_mcp", "seed": 3, "success": False, "tokens": 5, "error": "agent: timeout"}]
    task = r.aggregate(cells, authoring_tokens=1800)["tasks"][0]
    assert task["arms"]["after_mcp"]["total"] == 2
    paired = task["paired"]["after_mcp_vs_before"]
    assert paired["pairs"] == 2 and paired["only_after_passed"] == 2 and paired["tokens_saved_median"] == 900
    assert paired["break_even_reuses"] == 2


def test_run_skill_resolves_flat_names_and_installed_copy_loads(tmp_path, monkeypatch):
    import gitd.mcp_server as server
    from gitd.skills.engine import loader

    loaded = []
    monkeypatch.setattr(
        loader, "load_skill", lambda ref: loaded.append(str(ref)) or (_ for _ in ()).throw(RuntimeError("stop"))
    )
    import gitd.skills.engine as engine

    monkeypatch.setattr(engine, "load_skill", loader.load_skill)
    try:
        server.run_skill("calculator", "calculate", "{}")
    except RuntimeError:
        pass
    assert loaded and loaded[0].endswith("skillhub/ghost/calculator")
    module = load_module()
    ref = module.install_local(REPO / "skillhub/ghost/calculator", tmp_path)
    monkeypatch.undo()
    from gitd.skills.engine.loader import load_skill

    assert load_skill(tmp_path / ref / "@latest").name == "calculator"


def test_run_budget_shrinks_the_episode_cap_and_stops_when_spent(monkeypatch, tmp_path):
    module = load_module()
    caps = []
    monkeypatch.setattr(
        module,
        "run_agent",
        lambda cmd, prompt, transcript, timeout_s, token_cap=0: (
            caps.append(token_cap) or {"tokens": 700, "result": "DONE"}
        ),
    )
    monkeypatch.setattr(module, "missing_packages", lambda device, packages: [])
    monkeypatch.setattr(module.bench_mod, "force_stop", lambda *a: None)

    class Bridge:
        def request(self, op, **_):
            return {"init": {"goal": "g", "instance_seed": 1}, "score": {"is_successful": 1.0}}.get(op, {})

    class Skill:
        skill_dir = tmp_path
        author = "a"
        name = "b"

        class fingerprint:
            app_package = "p"

    monkeypatch.setattr(module, "install_local", lambda *a: "a/b")
    import gitd.skills.engine.evidence as evidence

    monkeypatch.setattr(evidence, "collect_fingerprint", lambda *a: None)
    budget = {"limit": 1500, "spent": 0}
    cells, blocker = module.run_arm(
        "before",
        skill=Skill,
        task="ExpenseAddSingle",
        seeds=[1, 2, 3, 4],
        device="emulator-5554",
        bridge=Bridge(),
        agent_cmd="claude",
        model="haiku",
        max_turns=5,
        worktree=tmp_path,
        out_dir=tmp_path,
        timeout_s=10,
        token_cap=3000,
        budget=budget,
    )
    assert caps == [1500, 800, 100] and len(cells) == 3 and "budget" in blocker and budget["spent"] == 2100


def test_cap_is_fail_counts_the_capped_episode_and_keeps_the_arm_going(monkeypatch, tmp_path):
    module = load_module()
    calls = []

    def agent(cmd, prompt, transcript, timeout_s, token_cap=0):
        calls.append(token_cap)
        return {"tokens": 4100, "over_cap": len(calls) == 1, "result": "DONE"}

    monkeypatch.setattr(module, "run_agent", agent)
    monkeypatch.setattr(module, "missing_packages", lambda device, packages: [])
    monkeypatch.setattr(module.bench_mod, "force_stop", lambda *a: None)
    scores = []

    class Bridge:
        def request(self, op, **_):
            if op == "score":
                scores.append(1)
            return {"init": {"goal": "g", "instance_seed": 1}, "score": {"is_successful": 1.0}}.get(op, {})

    class Skill:
        skill_dir = tmp_path
        author = "a"
        name = "b"

        class fingerprint:
            app_package = "p"

    import gitd.skills.engine.evidence as evidence

    monkeypatch.setattr(evidence, "collect_fingerprint", lambda *a: None)
    cells, blocker = module.run_arm(
        "before",
        skill=Skill,
        task="ExpenseAddSingle",
        seeds=[1, 2],
        device="emulator-5554",
        bridge=Bridge(),
        agent_cmd="claude",
        model="haiku",
        max_turns=5,
        worktree=tmp_path,
        out_dir=tmp_path,
        timeout_s=10,
        token_cap=4000,
        cap_is_fail=True,
    )
    assert blocker is None and len(cells) == 2
    assert cells[0]["capped"] and cells[0]["success"] is False and "error" not in cells[0] and len(scores) == 1
    assert cells[1]["success"] is True
