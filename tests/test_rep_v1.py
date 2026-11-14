"""Contributor rep v1 (skillhub/scoring/rep-v1.json): run credit per principal and the registry `contributors`."""

import json

import pytest

from tests.test_honest_scoring import NOW, REPO, _load, hub, registry  # noqa: F401  (hub is a fixture)

rep = _load("rep")
TABLE = json.loads((REPO / "skillhub" / "scoring" / "rep-v1.json").read_text())


def _reg(hub_dir):
    return registry.build_registry(hub_dir, now=NOW, warn=lambda m: None)


def test_rep_table_is_well_formed():
    assert TABLE["version"].startswith("rep-v1")
    assert {"published", "verified", "maintained", "badges", "rules"} <= set(TABLE)
    assert all(isinstance(v, int) and v > 0 for v in TABLE["verified"].values())
    assert TABLE["maintained"]["per_skill"] < TABLE["verified"]["independent_run"]  # maintenance is the small bonus
    stats = dict.fromkeys(
        ("published_skills", "verified_runs", "verified_skills", "new_device_classes", "new_bench_models", "maintained_skills"), 1
    )
    assert all(rep.badge_holds(b["rule"], stats) for b in TABLE["badges"])
    assert [b["id"] for b in TABLE["badges"]] == ["author", "verifier", "device_pioneer", "maintainer"]
    assert any("worth 0 rep" in r for r in TABLE["rules"])


def test_bad_badge_rule_is_a_build_error():
    with pytest.raises(ValueError):
        rep.badge_holds("downloads >= 1", {"verified_runs": 1})


def test_run_credit_goes_to_the_key_holder_never_the_label(hub):
    hub_dir, _, _, art = hub
    # maintainer key under a platform label: maintenance credit for ghost (the key), not ghost-aw-replay
    art("verifications", "aw-a.json", "maint", verifier="ghost-aw-replay", fingerprint_hash="a" * 64, device_class="emu/13")
    # author key under a platform label: credits nobody
    art("verifications", "aw-b.json", "alice", verifier="ghost-aw-replay", fingerprint_hash="b" * 64, device_class="emu/14")
    # carol twice on one fingerprint (latest counts once), then on a second device class
    art("verifications", "carol-1.json", "carol", verifier="carol", fingerprint_hash="c" * 64, device_class="Fairphone/5/14",
        finished_at="2026-10-19T00:00:00Z")
    art("verifications", "carol-2.json", "carol", verifier="carol", fingerprint_hash="c" * 64, device_class="Fairphone/5/14")
    art("verifications", "carol-3.json", "carol", verifier="carol", fingerprint_hash="e" * 64, device_class="Pixel/9/15",
        bench={"suite": "androidworld", "task_id": "t1", "arm": "after_mcp", "model": "m-1"})
    # carol's failing run earns nothing
    art("verifications", "carol-4.json", "carol", verifier="carol", ok=False, fingerprint_hash="g" * 64, device_class="X/1/14")
    art("verifications", "ci-d.json", "ci", verifier="ghost-ci-emulator", fingerprint_hash="d" * 64)
    reg = _reg(hub_dir)
    credits = reg["skills"]["alice/foo"]["quality"]["signals"]["runs_rep"]
    assert credits == {
        "carol": {"class": "independent", "credited": 2, "new_device_classes": 2, "new_bench_models": 1},
        "ghost": {"class": "maintainer", "credited": 1, "new_device_classes": 0, "new_bench_models": 0},
        "ghost-ci-emulator": {"class": "ci", "credited": 1, "new_device_classes": 0, "new_bench_models": 0},
    }
    c = reg["contributors"]
    v, m = TABLE["verified"], TABLE["maintained"]["per_skill"]
    assert set(c) == {"alice", "carol", "ghost", "ghost-ci-emulator"}  # no label-only principal, no seeded profile
    assert c["carol"]["breakdown"] == {
        "published": 0,
        "verified": 2 * v["independent_run"] + 2 * v["new_device_class"] + v["new_bench_model"],
        "maintained": 0,
    }
    assert c["carol"]["badges"] == ["verifier", "device_pioneer"]
    assert c["ghost"]["breakdown"]["maintained"] == m and c["ghost"]["badges"] == ["maintainer"]
    alice = c["alice"]
    assert alice["breakdown"]["published"] == reg["skills"]["alice/foo"]["quality"]["points"] > 0
    assert alice["rep"] == alice["breakdown"]["published"] and alice["badges"] == ["author"]
    assert alice["published"][0]["skill"] == "alice/foo"


def test_own_verifications_of_own_skill_earn_no_verifier_rep(hub):
    hub_dir, _, _, art = hub
    art("verifications", "alice-self.json", "alice", verifier="alice", fingerprint_hash="c" * 64)
    reg = _reg(hub_dir)
    assert reg["skills"]["alice/foo"]["quality"]["signals"]["runs_rep"] == {}
    assert reg["contributors"]["alice"]["breakdown"]["verified"] == 0


def test_contributors_rules_on_plain_registry_data():
    def sk(author, points, status="active", runs_rep=None):
        return {"author": author, "status": status, "quality": {"points": points, "tier": "runs", "signals": {"runs_rep": runs_rep or {}}}}

    skills = {
        "ghost/a": sk("ghost", 20),
        "ghost/old": sk("ghost", 50, status="deprecated"),
        "androidworld/x": sk("androidworld", 21, runs_rep={"ghost": {"class": "maintainer", "credited": 18, "new_device_classes": 0, "new_bench_models": 0}}),
        "bob/b": sk("bob", 30, runs_rep={
            "ghost": {"class": "independent", "credited": 1, "new_device_classes": 1, "new_bench_models": 0},
            "bob": {"class": "independent", "credited": 5, "new_device_classes": 5, "new_bench_models": 0},  # never self
            "dan": {"class": "independent", "credited": 0, "new_device_classes": 0, "new_bench_models": 0},  # failing only
        }),
    }
    authors = {"ghost": {"trust": "official", "github": "ghost-in-the-droid"}, "bob": {"trust": "unverified", "github": "bob"}}
    out = rep.contributors(skills, authors, maintainers={"ghost": ["C-K-Loan"]}, rep=TABLE)
    assert list(out) == ["bob", "ghost"]  # androidworld (benchmark) and dan (nothing counted) have no profile
    g = out["ghost"]
    assert (g["github"], g["maintainers"], g["trust"]) == ("ghost-in-the-droid", ["C-K-Loan"], "official")
    v = TABLE["verified"]
    assert g["breakdown"] == {
        "published": 20,  # deprecated skill earns 0
        "verified": v["independent_run"] + v["new_device_class"],
        "maintained": TABLE["maintained"]["per_skill"],  # per skill, not per run (18 runs)
    }
    assert g["rep"] == sum(g["breakdown"].values())
    assert [p["points"] for p in g["published"]] == [20, 0]
    assert g["badges"] == ["author", "verifier", "device_pioneer", "maintainer"]
    assert out["bob"]["breakdown"] == {"published": 30, "verified": 0, "maintained": 0}
    assert rep.contributors(skills, authors, rep=TABLE) == rep.contributors(dict(reversed(skills.items())), authors, rep=TABLE)
