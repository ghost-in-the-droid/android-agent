"""Offline imports must retain source evidence and never rewrite findings."""

import copy
import json
from pathlib import Path

import pytest

from tools.bench.bench_card import (
    add_skill_provenance,
    convert_task,
    main,
    mark_itt_failure,
    merge_card,
    merge_labelled_result,
)
from tools.bench.showcase_pool import pooled_headline


@pytest.fixture
def report():
    return json.loads((Path(__file__).parent / "fixtures/bench_card_nat2.json").read_text())


def task(report):
    return convert_task(report, "calc_3plus3", "ghost/calculator", "calculate", 'Calculator "3+3"')


def merge(existing, converted, **kwargs):
    return merge_card(existing, converted, skill="ghost/calculator", suite="ghost-native", source="nat2.json", **kwargs)


def test_cli_round_trip(tmp_path, monkeypatch, report):
    monkeypatch.chdir(tmp_path)
    Path("nat2.json").write_text(json.dumps(report))
    args = [
        "nat2.json",
        "--task",
        "calc_3plus3",
        "--skill",
        "ghost/calculator",
        "--suite",
        "ghost-native",
        "--action",
        "calculate",
        "--label",
        'Calculator "3+3"',
    ]
    assert main(args) == 0
    card = json.loads(Path("skillhub/ghost/calculator/bench/ghost-native.json").read_text())
    result = card["tasks"][0]
    assert result["episodes"] == report["episodes"]["calc_3plus3"]
    assert result["stats"]["arms"] == report["stats"]["tasks"][0]["arms"]
    assert result["stats"]["paired"] == report["stats"]["tasks"][0]["paired"]
    assert result["action"] == "calculate"
    assert result["label"] == 'Calculator "3+3"'
    assert card["model"] == ["claude-haiku-5-5"]
    assert card["run_ids"] == ["nat2"]
    assert card["evidence_class"] == "maintainer"
    assert card["label"] == "maintainer-run, not independent"
    assert card["generated_at"].endswith("Z")
    for arm, stats in result["stats"]["arms"].items():
        assert result["arms"][arm] == {
            "passed": stats["passed"],
            "total": stats["total"],
            "tokens_median": stats["tokens"]["median"],
            "wall_ms_median": stats["wall_ms"]["median"],
        }
    assert main(args) == 0
    assert len(json.loads(Path("skillhub/ghost/calculator/bench/ghost-native.json").read_text())["tasks"]) == 1


def test_merge_preserves_findings_and_other_tasks(report):
    converted = task(report)
    old = copy.deepcopy(converted)
    old["void_arms"] = {"before": {"valid": False, "invalid_reason": "missing app"}}
    old["labelled_results"] = {"pre_fix": {"valid": True, "passed": 1, "total": 2}}
    old["arms"] = {}
    other = {"task_id": "read_result", "action": "read_result", "arms": {}}
    existing = {"tasks": [old, other]}
    snapshot = copy.deepcopy(existing)
    card = merge(existing, converted)
    assert card["tasks"][0]["arms"] == converted["arms"]
    assert card["tasks"][0]["void_arms"] == old["void_arms"]
    assert card["tasks"][0]["labelled_results"] == old["labelled_results"]
    assert card["tasks"][1] == other
    assert existing == snapshot


@pytest.mark.parametrize("key,value", [("skill", "ghost/clock"), ("pass", False), ("valid", False)])
def test_refuse_wrong_skill_or_counts(report, key, value):
    report["episodes"]["calc_3plus3"][0][key] = value
    with pytest.raises(ValueError, match="differs|disagree"):
        task(report)


def test_preserve_invalid_episode_and_trace(report):
    row = copy.deepcopy(report["episodes"]["calc_3plus3"][0])
    row.update(seed=99, valid=False, invalid_reason="token cap", **{"pass": False})
    report["episodes"]["calc_3plus3"].append(row)
    assert task(report)["episodes"][-1] == row


def test_preserve_arms_refuses_changed_numbers(report):
    converted = task(report)
    card = merge({}, converted)
    card["tasks"][0]["arms"]["after_mcp"]["passed"] = 1
    with pytest.raises(ValueError, match="existing 1 disagrees"):
        merge(card, converted, preserve_arms=True)


def test_preserve_arms_keeps_unreported_arms_and_metadata(report):
    converted = task(report)
    card = merge({}, converted)
    card["tasks"][0]["arms"]["before"]["note"] = "historical source"
    del converted["arms"]["after_replay"]
    assert merge(card, converted, preserve_arms=True)["tasks"][0]["arms"] == card["tasks"][0]["arms"]


def test_labelled_episodes_leave_current_results_and_findings_unchanged(report):
    converted = task(report)
    card = merge({}, converted)
    finding = {"passed": 1, "total": 2, "note": "original counting rule", "valid": True}
    card["tasks"][0]["labelled_results"] = {"pre_fix": finding}
    rows = converted["episodes"]
    rows[0].update(valid=False, invalid_reason="token cap")
    result = merge_labelled_result(card, converted, "pre_fix", "after_mcp")
    imported = result["tasks"][0]["labelled_results"]["pre_fix"].pop("episodes")
    assert imported == [r for r in rows if r["arm"] == "after_mcp"]
    assert imported[0]["valid"] is False
    assert result == card


def test_cli_refusal_exit_two_does_not_write(tmp_path, monkeypatch, report, capsys):
    monkeypatch.chdir(tmp_path)
    report["stats"]["tasks"][0]["arms"]["before"]["total"] = 100
    Path("nat2.json").write_text(json.dumps(report))
    with pytest.raises(SystemExit) as exc:
        main(
            [
                "nat2.json",
                "--task",
                "calc_3plus3",
                "--skill",
                "ghost/calculator",
                "--suite",
                "ghost-native",
                "--action",
                "calculate",
                "--label",
                "Calculator",
            ]
        )
    assert exc.value.code == 2
    assert "disagree" in capsys.readouterr().err
    assert not Path("skillhub").exists()


def test_episodes_only_preserves_published_itt_arm_and_omits_incompatible_stats(report):
    converted = task(report)
    card = merge({}, converted)
    card["tasks"][0]["arms"]["after_mcp"].update(passed=4, total=6)
    result = merge(card, converted, episodes_only=True)["tasks"][0]
    assert result["arms"] == card["tasks"][0]["arms"]
    assert result["episodes"] == converted["episodes"]
    assert "after_mcp" not in result["stats"]["arms"]
    assert "after_mcp_vs_before" not in result["stats"]["paired"]
    assert result["stats"]["arms"]["before"] == converted["stats"]["arms"]["before"]


def test_provenance_respects_fixed_arm_and_resolves_prefixed_findings(report):
    converted = task(report)
    converted["arms"]["after_mcp"]["skill_sha"] = "a1980cff (feat/skillhub 1b3f8e66)"
    historical = copy.deepcopy(converted["episodes"][:1])
    converted["labelled_results"] = {"pre_fix": {"skill_sha": "pre-a1980cff", "episodes": historical}}
    add_skill_provenance(converted, "38a33c23", "0.1.0")
    assert historical[0]["skill_sha"] == "38a33c23"
    for row in converted["episodes"]:
        assert row["skill_sha"] == converted["arms"][row["arm"]]["skill_sha"]
        assert row["skill_version"] == "0.1.0"


def test_itt_failure_preserves_source_validity_and_refuses_success(report):
    converted = task(report)
    with pytest.raises(ValueError, match="failed episode"):
        mark_itt_failure(converted, "after_mcp:0")
    row = converted["episodes"][0]
    row.update(valid=False, invalid_reason="token cap", **{"pass": False})
    mark_itt_failure(converted, "after_mcp:0")
    assert row["valid"] is False
    assert row["invalid_reason"] == "token cap"
    assert row["counted"] is True


def test_itt_adjudication_retains_source_flags_separately(report):
    converted = task(report)
    row = converted["episodes"][0]
    row.update(valid=False, invalid_reason="token cap", **{"pass": False})
    explanation = "fail (intention-to-treat): episode capped after the skill launch timeout"
    mark_itt_failure(converted, "after_mcp:0", explanation)
    assert row["valid"] is True
    assert row["pass"] is False
    assert row["source_valid"] is False
    assert row["source_invalid_reason"] == "token cap"
    assert "invalid_reason" not in row
    assert row["counted_as"] == explanation


def test_showcase_pool_includes_every_declared_task_and_itt_failure():
    result = pooled_headline(Path(__file__).resolve().parents[1] / "skillhub/showcase.yml")
    assert result["tasks"] == 6
    assert result["before"] == {"passed": 19, "total": 24}
    assert result["after_mcp"] == {"passed": 23, "total": 24}
    assert result["paired"] == {"pairs": 24, "for_skill": 5, "against_skill": 1, "mcnemar_exact_p": 0.21875}


def test_pool_requires_current_itt_failure_to_be_adjudicated_valid(tmp_path):
    manifest = tmp_path / "showcase.yml"
    manifest.write_text("skills:\n  - ref: ghost/test\n    task_ids: [test]\n")
    bench = tmp_path / "ghost/test/bench/native.json"
    bench.parent.mkdir(parents=True)
    failure = {
        "arm": "after_mcp",
        "seed": 1,
        "pass": False,
        "valid": False,
        "counted": True,
        "counting_rule": "intention-to-treat",
    }
    card = {
        "tasks": [
            {
                "task_id": "test",
                "arms": {"before": {"passed": 1, "total": 1}, "after_mcp": {"passed": 0, "total": 1}},
                "episodes": [{"arm": "before", "seed": 1, "pass": True, "valid": True}, failure],
            }
        ]
    }
    bench.write_text(json.dumps(card))
    with pytest.raises(ValueError, match="counted episodes disagree"):
        pooled_headline(manifest)
    failure.update(valid=True, counted_as="fail (intention-to-treat)")
    bench.write_text(json.dumps(card))
    assert pooled_headline(manifest)["paired"]["against_skill"] == 1
