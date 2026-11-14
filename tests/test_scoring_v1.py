"""skillhub/scoring/v1.json is the single source of truth for the quality ladder (0 to 100)."""

import ast
import copy
import importlib.util
import json
import re
from datetime import date
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCORING = REPO / "skillhub" / "scoring" / "v1.json"


def _load(name):
    spec = importlib.util.spec_from_file_location(f"_test_scoring_{name}", REPO / "tools" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


quality_mod = _load("quality")
NOW = "2026-10-05T12:00:00Z"


@pytest.fixture
def table():
    return json.loads(SCORING.read_text())


def _item_max(spec):
    return spec["cap"] if isinstance(spec, dict) else spec


def test_table_metadata_and_caps_sum_to_100(table):
    assert table["version"] == "v1.3"
    date.fromisoformat(table["effective_from"])
    caps = {k: v["cap"] for k, v in table["categories"].items()}
    assert caps == {"docs": 20, "self_evidence": 30, "independent": 30, "community_usage": 10, "maintenance": 10}
    assert sum(caps.values()) == table["max_points"] == 100
    for name, cat in table["categories"].items():
        if "items" in cat:  # itemised categories: item maxima add up exactly to the cap
            assert sum(_item_max(v) for v in cat["items"].values()) == cat["cap"], name


def test_table_items_and_tiers_match_maintainer_decision(table):
    c = table["categories"]
    assert c["docs"]["items"] == {
        "manifest": 3,
        "readme": 3,
        "failure_modes": 4,
        "demo_any": 4,
        "demo_all_actions": 3,
        "before_after": 3,
    }  # v1.3 (2026-11-03): easier to score well, still hard for 90-100
    assert c["self_evidence"]["items"] == {
        "first_self_run": 4,
        "validators": {
            "each": 2,
            "cap": 8,
            "per": "action",
            "weights": {"custom_python": 2, "parameterised_text": 2, "default": 1},
        },
        "bench_one_model": 4,
        "self_reliability": {"cap": 10, "min_runs": 3, "per": "action"},  # v1.3 choice, 2026-11-03
        "self_second_device": 4,
    }
    assert c["independent"]["items"] == {
        "first_independent": 12,
        "second_device_class": 8,
        "third_device_class": 4,
        "bench_second_model": 4,
        "bench_third_model": 2,
    }
    assert (c["community_usage"]["min_runs"], c["community_usage"]["cap"]) == (10, 10)
    assert c["maintenance"]["items"] == {"reverified_30d": 6, "bug_response_7d": {"each": 2, "cap": 4}}
    tiers = [(t["id"], t["points"]) for t in table["tiers"]]
    assert tiers == [("draft", 0), ("runs", 10), ("proven", 35), ("hardened", 60), ("reference", 90)]
    assert [s["multiplier"] for s in table["freshness"]["steps"]] + [table["freshness"]["floor"]] == [1.0, 0.8, 0.5]


def test_full_marks_reach_exactly_100():
    s = dict(
        manifest_valid=True,
        static_scan_clean=True,
        readme=True,
        failure_modes=True,
        demo=True,
        demo_all_actions=True,
        before_after=True,
        self_runs=1,
        self_devices=2,
        runs_self_min_action_total=10**6,
        validators=4,
        bench_models=3,
        independent_device_classes=3,
        community_runs=10**6,
        community_successes=10**6,
        runs_self_total=10**6,
        runs_self_passed=10**6,
        bugs_responded_7d=2,
        last_verified="2026-10-05T00:00:00Z",
    )
    r = quality_mod.quality(s, now=NOW)
    assert r["points"] == 100 and r["scoring_version"] == "v1.3"


def test_self_reliability_needs_three_runs_on_every_action_and_tracks_the_wilson_bound():
    q = quality_mod.quality

    def se(total, passed, per_action=None):
        sig = dict(manifest_valid=True, readme=True, self_runs=1, runs_self_total=total, runs_self_passed=passed)
        sig["runs_self_min_action_total"] = total if per_action is None else per_action
        return q(sig, now=NOW)["categories"]["self_evidence"]

    assert se(2, 2) == 4  # first self-run only
    assert se(30, 30, per_action=2) == 4  # v1.3: the action with the fewest own runs decides
    assert se(3, 3) == 4 + 4  # LB 0.44: a small sample earns little
    assert se(15, 15, per_action=3) == 4 + 8  # LB 0.80, Wilson over ALL own runs
    assert se(30, 30) == 4 + 9  # LB 0.89
    assert se(10, 5) == 4 + 2  # LB 0.24


def test_second_device_and_before_after_are_all_or_nothing():
    q = quality_mod.quality
    base = dict(manifest_valid=True, readme=True, self_runs=1)
    assert q({**base, "self_devices": 1}, now=NOW)["categories"]["self_evidence"] == 4
    assert q({**base, "self_devices": 2}, now=NOW)["categories"]["self_evidence"] == 4 + 4
    assert q(base, now=NOW)["categories"]["docs"] == 6
    assert q({**base, "before_after": True}, now=NOW)["categories"]["docs"] == 6 + 3


def test_solo_author_ceiling_is_50_and_90_needs_other_people():
    """v1.3 intent: own work alone reaches 50 (v1.2: 30); everything else needs independent and community evidence."""
    solo = dict(
        manifest_valid=True, static_scan_clean=True, readme=True, failure_modes=True, demo=True,
        demo_all_actions=True, before_after=True, self_runs=1, validators=4, bench_models=1, self_devices=2,
        runs_self_total=10**6, runs_self_passed=10**6, runs_self_min_action_total=10**6,
    )
    r = quality_mod.quality(solo, now=NOW)
    assert r["points"] == 50 and r["tier"] == "proven"  # v1.3: Proven on own evidence
    assert quality_mod.quality({**solo, "demo": False}, now=NOW)["tier"] == "runs"  # Proven needs a demo
    assert quality_mod.quality({**solo, "self_runs": 0}, now=NOW)["tier"] == "draft"  # and own runs on every action
    assert quality_mod.quality({**solo, "validators": 2}, now=NOW)["tier"] == "runs"  # and 3 validator units/action
    v12 = json.loads((REPO / "skillhub" / "scoring" / "history" / "v1.2.json").read_text())
    assert quality_mod.quality(solo, now=NOW, scoring=v12)["points"] == 30
    plus_indep = {**solo, "independent_device_classes": 3, "bench_models": 3, "last_verified": "2026-10-05T00:00:00Z"}
    assert quality_mod.quality(plus_indep, now=NOW)["points"] == 80 + 6  # + maintenance re-verified; 90 needs usage
    # Hardened needs an independent device class even with every other Hardened gate met
    hardened = {**plus_indep, "oem_combos": 2, "community_runs": 40, "community_successes": 40}
    assert quality_mod.quality(hardened, now=NOW)["tier"] == "hardened"
    assert quality_mod.quality({**hardened, "independent_device_classes": 0}, now=NOW)["tier"] == "proven"


def test_the_file_drives_the_numbers(table, tmp_path):
    s = dict(manifest_valid=True, readme=True, demo=True, self_runs=1)
    base = quality_mod.quality(s, now=NOW, scoring=table)
    assert (base["points"], base["tier"]) == (14, "runs")

    alt = copy.deepcopy(table)
    alt["version"] = "v9-test"
    alt["categories"]["docs"]["items"]["readme"] = 7
    alt["categories"]["docs"]["cap"] = 19
    next(t for t in alt["tiers"] if t["id"] == "runs")["points"] = 30
    r = quality_mod.quality(s, now=NOW, scoring=alt)
    assert r["categories"]["docs"] == 3 + 7 + 4 and r["points"] == 18
    assert r["tier"] == "draft" and r["scoring_version"] == "v9-test"  # threshold moved by the file

    path = tmp_path / "v9.json"
    path.write_text(json.dumps(alt))
    assert quality_mod.load_scoring(path)["version"] == "v9-test"
    assert quality_mod.load_scoring()["version"] == "v1.3"


def test_default_table_is_read_from_disk(tmp_path, monkeypatch, table):
    alt = copy.deepcopy(table)
    alt["version"] = "v-disk"
    f = tmp_path / "scoring.json"
    f.write_text(json.dumps(alt))
    monkeypatch.setattr(quality_mod, "DEFAULT_SCORING", f)
    assert quality_mod.quality({}, now=NOW)["scoring_version"] == "v-disk"


def test_quality_py_hardcodes_no_scoring_numbers():
    tree = ast.parse((REPO / "tools" / "quality.py").read_text())
    nums = {
        n.value
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool)
    }
    # 2/3: "second/third" device class or model; 2/4: Wilson formula; 8: cache size; 86400: seconds per day;
    # 1.96: default z (scoring passes wilson_z from the table).
    assert nums <= {0, 1, 2, 3, 4, 8, 86400, 1.96}, nums
    src = (REPO / "tools" / "quality.py").read_text()
    assert "SCORING_V1" not in src and "THRESHOLDS" not in src


def test_registry_carries_scoring_version_and_reserves_scoring_dir(tmp_path):
    build_registry = _load("build_registry")
    reg = build_registry.build_registry(REPO / "skillhub", now=NOW)
    assert "scoring" not in reg["authors"]
    assert reg["skills"] and all(v["quality"]["scoring_version"] == "v1.3" for v in reg["skills"].values())
    committed = json.loads((REPO / "skillhub" / "registry.json").read_text())
    assert all(v["quality"]["scoring_version"] == "v1.3" for v in committed["skills"].values())


def test_ci_and_codeowners_treat_scoring_as_maintainer_owned(tmp_path):
    import sys

    sys.path.insert(0, str(REPO))
    from tools.build_codeowners import build_codeowners
    from tools.ci.common import submission_scope

    for d in ("ghost", "scoring", "alice"):
        (tmp_path / d).mkdir()
    lines = build_codeowners(tmp_path).splitlines()
    assert "/skillhub/scoring/ @C-K-Loan" in lines and "/skillhub/scoring/ @scoring" not in lines
    assert submission_scope(["skillhub/scoring/v1.json", "skillhub/alice/x/skill.yaml"]) == ["alice"]


def test_site_formula_reads_the_table():
    ts = (REPO / "site" / "src" / "lib" / "hub" / "scoring.ts").read_text()
    assert "skillhub/scoring/v1.json" in ts
    assert not re.search(r"\bcap: \d", ts) and not re.search(r"\bpoints: \d", ts)
