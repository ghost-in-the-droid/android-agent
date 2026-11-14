"""`ghost skill bench`: AndroidWorld replay arm against a fake bridge and the fake device.

The fake bridge speaks the real JSON-lines protocol (tests/fixtures/fake_aw_bridge.py); the fake
device replays the google_maps fixture. What is pinned: the artifact carries the bench block and the
AndroidWorld verdict (not the skill's own validator), a failed seed is a failed cell, the summary
counts each seed once, unknown tasks and unknown arms are refused, and the bridge's seeding matches
AndroidWorld's suite_utils scheme.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from gitd.skills.engine import bench, cli

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests/fixtures/fake_google_maps"
FAKE_BRIDGE = REPO / "tests/fixtures/fake_aw_bridge.py"


@pytest.fixture
def environment(tmp_path, monkeypatch):
    skill = tmp_path / "skillhub/ghost/google_maps"
    skill.parent.mkdir(parents=True)
    # Start with skill code only; real hub recordings are not test output.
    shutil.copytree(REPO / "skillhub/ghost/google_maps", skill, ignore=shutil.ignore_patterns("runs", "verifications"))
    monkeypatch.setenv("GHOST_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("GHOST_SKILLS_DIR", str(tmp_path / "installed"))
    monkeypatch.delenv("GHOST_DEVICE", raising=False)
    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    original_run = subprocess.run

    def guarded_run(args, **kwargs):
        if args[0] == "ssh-keygen":
            return original_run(args, **kwargs)
        pytest.fail("Fake run attempted an external operation: " + repr(args))

    monkeypatch.setattr(subprocess, "run", guarded_run)
    monkeypatch.setenv("FAKE_AW_LOG", str(tmp_path / "bridge.log"))
    monkeypatch.setenv("FAKE_AW_PARAMS", json.dumps({"query": "Fixture Cafe", "row_objects": [{"name": "x"}]}))
    return skill, tmp_path


def bridge_cmd() -> str:
    return f"{sys.executable} {FAKE_BRIDGE}"


def test_replay_writes_bench_artifacts_and_summary(environment, capsys):
    if not shutil.which("ssh-keygen"):
        pytest.skip("SSH signing unavailable")
    skill, tmp = environment
    rc = cli.main(
        [
            "bench",
            str(skill),
            "--androidworld",
            "FakeTask",
            "--action",
            "search_place",
            "--n",
            "2",
            "--device",
            "fake:" + str(FIXTURE),
            "--bridge-cmd",
            bridge_cmd(),
            "--upstream-commit",
            "abc123",
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "androidworld replay 2/2 passed" in out
    artifacts = sorted((skill / "runs").glob("*.json"))
    assert len(artifacts) == 2
    data = json.loads(artifacts[0].read_text())
    assert data["bench"] == {
        "suite": "androidworld",
        "task_id": "FakeTask",
        "arm": "after_replay",
        "seed": 30,
        "instance_seed": 1030,
        "steps": data["bench"]["steps"],
        "tokens": 0,
        "wall_ms": data["bench"]["wall_ms"],
        "is_successful": 1.0,
    }
    assert data["success"] is True and data["simulation"] is True and data["signature"]["value"]
    summary = json.loads((skill / "bench/androidworld.json").read_text())
    (task,) = summary["tasks"]
    arm = task["arms"]["after_replay"]
    assert (task["task_id"], task["action"], task["seeds"]) == ("FakeTask", "search_place", 2)
    assert (arm["passed"], arm["total"], arm["seeds_run"], arm["tokens_median"]) == (2, 2, [30, 31], 0)
    assert summary["upstream_commit"] == "abc123" and summary["suite"] == "androidworld" and len(arm["artifacts"]) == 2
    assert summary["protocol"] == "docs/benchmark-protocol.md" and summary["generated_at"].endswith("Z")
    # The bridge saw the lifecycle in order for every seed, and only the scalar params the action declares reached the skill.
    ops = [json.loads(line)["op"] for line in (tmp / "bridge.log").read_text().splitlines()]
    assert ops == ["hello", "init", "score", "teardown", "init", "score", "teardown", "quit"]


def test_androidworld_verdict_overrides_skill_validator(environment, monkeypatch, capsys):
    if not shutil.which("ssh-keygen"):
        pytest.skip("SSH signing unavailable")
    skill, tmp = environment
    monkeypatch.setenv("FAKE_AW_SCORES", json.dumps([0.0, 1.0]))
    rc = cli.main(
        [
            "bench",
            str(skill),
            "--androidworld",
            "FakeTask",
            "--action",
            "search_place",
            "--n",
            "2",
            "--device",
            "fake:" + str(FIXTURE),
            "--bridge-cmd",
            bridge_cmd(),
        ]
    )
    captured = capsys.readouterr()
    assert rc == 1 and "androidworld replay 1/2 passed" in captured.err
    verdicts = sorted(json.loads(p.read_text())["success"] for p in (skill / "runs").glob("*.json"))
    assert verdicts == [False, True]
    arm = json.loads((skill / "bench/androidworld.json").read_text())["tasks"][0]["arms"]["after_replay"]
    assert (arm["passed"], arm["total"]) == (1, 2)


def test_summary_counts_a_seed_once(environment):
    skill, _ = environment
    from gitd.skills.engine import load_skill

    s = load_skill(str(skill))
    cells = [
        {"task_id": "T", "arm": "after_replay", "seed": 30, "success": True, "wall_ms": 10, "action": "a"},
        {"task_id": "T", "arm": "after_replay", "seed": 30, "success": False, "wall_ms": 10, "action": "a"},
        {"task_id": "T", "arm": "before", "seed": 30, "success": False, "wall_ms": 900, "tokens": 500, "action": "a"},
    ]
    bench.write_summary(s, cells)
    bench.write_summary(s, cells[:1])
    (task,) = json.loads((skill / "bench/androidworld.json").read_text())["tasks"]
    assert (task["arms"]["after_replay"]["passed"], task["arms"]["after_replay"]["total"]) == (1, 1)
    assert (
        task["arms"]["before"]["passed"],
        task["arms"]["before"]["total"],
        task["arms"]["before"]["tokens_median"],
    ) == (0, 1, 500)


def test_summary_keeps_void_arms_and_void_rows_stay_out_of_arms(environment):
    # A voided arm (VOID notice 2026-10-22: Markor uninstalled mid-run) lives in tasks[].void_arms with
    # valid=false; write_summary must neither drop it nor resurrect it into arms when a seed is added.
    skill, _ = environment
    from gitd.skills.engine import load_skill

    s = load_skill(str(skill))
    bench.write_summary(
        s, [{"task_id": "T", "arm": "after_replay", "seed": 30, "success": True, "wall_ms": 10, "action": "a"}]
    )
    card = skill / "bench/androidworld.json"
    doc = json.loads(card.read_text())
    doc["tasks"][0]["void_arms"] = {
        "before": {"passed": 0, "total": 3, "valid": False, "invalid_reason": "task app missing"}
    }
    card.write_text(json.dumps(doc))
    bench.write_summary(
        s, [{"task_id": "T", "arm": "after_replay", "seed": 31, "success": True, "wall_ms": 10, "action": "a"}]
    )
    (task,) = json.loads(card.read_text())["tasks"]
    assert list(task["arms"]) == ["after_replay"] and task["arms"]["after_replay"]["total"] == 2
    assert task["void_arms"]["before"] == {
        "passed": 0,
        "total": 3,
        "valid": False,
        "invalid_reason": "task app missing",
    }


def test_unknown_task_and_arm_are_refused(environment, capsys):
    skill, _ = environment
    assert (
        cli.main(
            [
                "bench",
                str(skill),
                "--androidworld",
                "Nope",
                "--action",
                "search_place",
                "--no-record",
                "--device",
                "fake:" + str(FIXTURE),
                "--bridge-cmd",
                bridge_cmd(),
            ]
        )
        == 2
    )
    assert "not an AndroidWorld task" in capsys.readouterr().err
    assert (
        cli.main(
            [
                "bench",
                str(skill),
                "--androidworld",
                "FakeTask",
                "--arms",
                "before",
                "--no-record",
                "--device",
                "fake:" + str(FIXTURE),
                "--bridge-cmd",
                bridge_cmd(),
            ]
        )
        == 2
    )


def test_bridge_error_is_a_failed_cell_not_a_crash(environment, monkeypatch):
    skill, _ = environment
    from gitd.skills.engine import load_skill

    s = load_skill(str(skill))
    monkeypatch.setenv("FAKE_AW_TASKS", "Other")
    with bench.AWBridge(bench.bridge_command(bridge_cmd())) as b:
        cells = bench.replay_task(
            s,
            "FakeTask",
            seeds=[30],
            device="fake:" + str(FIXTURE),
            bridge=b,
            action="search_place",
            record=False,
            progress=lambda _m: None,
        )
    assert cells[0]["success"] is False and cells[0]["error"].startswith("bridge: KeyError")


def test_param_adapters_and_passthrough():
    aw = {"row_objects": [{"name": "Lunch", "amount": 1250, "category": 3, "note": "n"}], "seed": 1}
    assert bench.skill_params("ExpenseAddSingle", aw, ["rows"]) == {
        "rows": [{"name": "Lunch", "amount": "12.50", "category": "Food", "note": "n"}]
    }
    assert bench.skill_params("ExpenseDeleteSingle", aw, ["names"]) == {"names": ["Lunch"]}
    assert bench.skill_params("ExpenseAddMultipleFromMarkor", aw, []) == {}
    assert bench.skill_params("SomethingElse", {"query": "q", "row_objects": [], "n": 2}, ["query"]) == {"query": "q"}


def test_bridge_seed_scheme_matches_androidworld_suite_utils():
    spec = importlib.util.spec_from_file_location("aw_bridge", REPO / "tools/bench/aw_bridge.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    expected = int(hashlib.sha256(b"30_ExpenseAddMultipleFromMarkor_0").hexdigest(), 16) % (2**32)
    assert module.instance_seed_for("ExpenseAddMultipleFromMarkor", 30) == expected
    import dataclasses

    @dataclasses.dataclass(frozen=True)
    class Row:
        name: str
        amount: int

    assert module.jsonable({"row_objects": [Row("a", 1)], "x": (1, 2)}) == {
        "row_objects": [{"name": "a", "amount": 1}],
        "x": [1, 2],
    }


def test_pro_expense_helpers_pure_functions():
    spec = importlib.util.spec_from_file_location("pe_helpers", REPO / "skillhub/androidworld/pro-expense/helpers.py")
    h = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(h)
    text = "name|amount_dollars|category_name|note\nLunch|$12.5|Food|Team lunch. Reimbursable.\nBook|$9.99|Education|\n"
    rows = h.parse_expense_text(text)
    assert rows == [
        {"name": "Lunch", "amount": "$12.5", "category": "Food", "note": "Team lunch. Reimbursable."},
        {"name": "Book", "amount": "$9.99", "category": "Education", "note": ""},
    ]
    assert h.normalize_rows(h.reimbursable(rows)) == [
        {"name": "Lunch", "amount": "12.50", "category": "Food", "note": "Team lunch"}
    ]
    assert h.reimbursable([{"name": "a", "amount": "1", "category": "Food", "note": "Reimbursable."}])[0]["note"] == ""
    assert h.cents("$12.5") == 1250 and h.cents("9.99") == 999
    with pytest.raises(ValueError):
        h.normalize_rows([{"name": "x", "amount": "1", "category": "Snacks"}])


def test_pro_expense_rows_accept_androidworld_keys_and_refuse_missing_amount():
    # ab3 finding (bench runner, 2026-10-22): an agent passing the task's own keys got every row saved as
    # 0.00 / Others, the action said success and the validator agreed because it compared against the defaults.
    spec = importlib.util.spec_from_file_location("pe_helpers", REPO / "skillhub/androidworld/pro-expense/helpers.py")
    h = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(h)
    aw_rows = [
        {"name": "Social Club Dues", "amount_dollars": 67.41, "category_name": "Social", "note": "Monthly recurring"},
        {"name": "Legal Fees", "amount_dollars": 10.14, "category_name": "Others", "note": "Monthly recurring"},
    ]
    assert h.normalize_rows(aw_rows) == [
        {"name": "Social Club Dues", "amount": "67.41", "category": "Social", "note": "Monthly recurring"},
        {"name": "Legal Fees", "amount": "10.14", "category": "Others", "note": "Monthly recurring"},
    ]
    assert h.normalize_rows(json.dumps(aw_rows[:1])) == h.normalize_rows(aw_rows[:1]) == h.normalize_rows(aw_rows[0])
    for bad in (
        [{"name": "x", "category": "Food"}],
        [{"name": "x", "amount": "", "category": "Food"}],
        [{"name": "x", "amount": "1"}],
        [],
        [{"name": "x", "amount": "abc", "category": "Food"}],
        ["x"],
    ):
        with pytest.raises(ValueError):
            h.normalize_rows(bad)
    # The Markor csv path refuses a file without an amount column instead of logging 0.00.
    with pytest.raises(ValueError):
        h.normalize_rows(h.parse_expense_text("name|category_name|note\nLunch|Food|Reimbursable\n"))

    # The validator compares the ledger against the caller's amounts, not against defaults.
    class Dev:
        def adb(self, *a):
            return "Social Club Dues|6741|5|Monthly recurring\nLegal Fees|1014|1|Monthly recurring\n"

    class Ctx:
        params = {"rows": aw_rows}

    assert h.validate_expense_add_multiple(Dev(), Ctx()) is True

    class Zero(Dev):
        def adb(self, *a):
            return "Social Club Dues|0|1|Monthly recurring\nLegal Fees|0|1|Monthly recurring\n"

    assert h.validate_expense_add_multiple(Zero(), Ctx()) is False
