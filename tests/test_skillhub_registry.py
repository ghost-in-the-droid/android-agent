"""tools/build_registry.py + tools/quality.py (contract section 3). No network."""

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def _load(name):
    spec = importlib.util.spec_from_file_location(f"_test_tools_{name}", REPO / "tools" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


build_registry = _load("build_registry")
quality_mod = _load("quality")

TOP_KEYS = {"schema_version", "generated_at", "repo", "authors", "skills", "rep_version", "contributors"}
AUTHOR_KEYS = {"trust", "github", "skills"}
SKILL_KEYS = {
    "author",
    "slug",
    "name",
    "description",
    "skill_class",
    "schema",
    "trust",
    "status",
    "flags",
    "icon",
    "demo",
    "demos",
    "before_after",
    "latest",
    "versions",
    "quality",
    "updated_at",
    "forked_from",
    "superseded_by",
    "deprecated_reason",
}
VERSION_KEYS = {
    "tag",
    "commit",
    "fingerprint",
    "actions",
    "data_access",
    "has_python",
    "files",
    "size_bytes",
    "license",
    "side_effects",
    "destructive",
    "tos_risk",
    "locale",  # last 5: Amendment A (D6)
    "prompts",
}  # {action: [ref_prompt, *variants]} for `ghost skill find`
FP_KEYS = {"os", "os_version", "hardware", "app_package", "app_version", "apps"}
SIGNAL_KEYS = {
    "manifest_valid",
    "static_scan_clean",
    "readme",
    "soft_md",
    "demo",
    "demo_all_actions",
    "bench",
    "failure_modes",
    "validators",
    "validators_total",
    "bench_models",
    "self_runs",
    "independent_runs",
    "independent_device_classes",
    "independent_verifier_classes",
    "community_runs",
    "community_successes",
    "oem_combos",
    "last_verified",
    "tests_pass",
    "fingerprints_verified",
    "hardened_since",
    "curator_review",
    "open_p1_over_14d",
    "author_contributor",
    "bugs_responded_7d",
    "runs_total",
    "runs_passed",
    "runs_total_90d",
    "runs_passed_90d",
    "runs_self_total",
    "runs_self_passed",
    "runs_independent_total",
    "runs_independent_passed",
    "runs_rejected",
    "runs_rejected_reasons",
    "runs_bench",
    # scoring v1.2 (honest scoring): evidence classes, current version, per-action credit
    "current_version",
    "maintainer_runs",
    "ci_runs",
    "independent_devices",
    "device_grid",
    "last_self_run",
    "actions_with_passing_run",
    "runs_maintainer_total",
    "runs_maintainer_passed",
    "runs_ci_total",
    "runs_ci_passed",
    "runs_previous_total",
    "runs_previous_passed",
    "runs_emulator_total",
    "runs_emulator_passed",
    "runs_emulator_unknown",
    "runs_actions",
    "runs_verifiers",
    "runs_self_min_action_total",
    "self_devices",
    "before_after",
    "runs_rep",
}
QUALITY_KEYS = {
    "tier",
    "score",
    "points",
    "categories",
    "freshness_multiplier",
    "provisional_until",
    "runs",
    "scoring_version",
    "signals",
}
RUNS_KEYS = {
    "current_version",
    "passed",
    "total",
    "passed_90d",
    "total_90d",
    "self",
    "maintainer",
    "ci",
    "independent",
    "previous_versions",
    "emulator",
    "independent_devices",
    "device_grid",
    "actions",
    "verifiers",
    "rejected",
    "bench",
}
ZERO_SPLIT = {
    "current_version": None,
    "self": {"passed": 0, "total": 0},
    "maintainer": {"passed": 0, "total": 0},
    "ci": {"passed": 0, "total": 0},
    "independent": {"passed": 0, "total": 0},
    "previous_versions": {"passed": 0, "total": 0},
    "emulator": {"passed": 0, "total": 0, "unknown": 0},
    "independent_devices": 0,
    "device_grid": {"cells": [], "independent_cells": 0},
    "actions": {},
    "verifiers": [],
    "rejected": {"total": 0, "reasons": {}},
    "bench": 0,
}

YAML = """\
name: {slug}
version: {version}
author: {author}
description: "{slug} skill"
skill_class: {cls}
tos_risk: low
data_access: [storage]
fingerprint:
  os: android
  os_version: ">=14"
  hardware: "*"
  app_package: com.example.{slug}
  app_version: ">=1.0"
actions:
  - name: go
    ref_prompt: "Start the example workflow"
    steps: [{{action: sleep, duration_s: 1}}]
    end_state_validator: [{{kind: text_visible, text: ok}}]
  - name: stop
    ref_prompt: "Stop the example workflow"
    steps: [{{action: sleep, duration_s: 1}}]
    end_state_validator: [{{kind: text_visible, text: ok}}]
"""


def make(hub: Path, author: str, slug: str, *, version="1.0.0", cls="hard", extras=()):
    d = hub / author / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / "skill.yaml").write_text(YAML.format(author=author, slug=slug, version=version, cls=cls))
    for name in extras:
        f = d / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(f"# {name}\n")
    return d


NOW = "2026-10-05T12:00:00Z"


def _sig(**kw):
    base = {"manifest_valid": True, "static_scan_clean": True}
    base.update(kw)
    return base


def test_quality_draft_and_runs():
    q = quality_mod.quality
    assert q({}, now=NOW)["tier"] == "draft"
    docs = _sig(readme=True, demo=True)  # manifest 3 + readme 3 + demo_any 4 = 10 (v1.3), no self-run
    r = q(docs, now=NOW)
    assert (r["tier"], r["points"], r["categories"]["docs"]) == ("draft", 10, 10)  # points alone never make Runs
    assert q({**docs, "demo_all_actions": True}, now=NOW)["categories"]["docs"] == 13  # + demo_all_actions 3
    r = q({**docs, "self_runs": 1}, now=NOW)  # + first self-run 4 (v1.3)
    assert r["tier"] == "runs" and r["points"] == 14
    assert set(r) == {
        "tier",
        "score",
        "points",
        "categories",
        "freshness_multiplier",
        "provisional_until",
        "runs",
        "scoring_version",
    }
    assert r["scoring_version"] == "v1.3"
    assert set(r["categories"]) == {"docs", "self_evidence", "independent", "community_usage", "maintenance"}


def test_quality_caps_and_downloads_worth_zero():
    q = quality_mod.quality
    s = _sig(
        readme=True,
        failure_modes=True,
        demo=True,
        demo_all_actions=True,
        before_after=True,
        self_runs=5,
        self_devices=9,
        validators=50,
        bench_models=9,
        independent_device_classes=9,
        independent_verifier_classes=9,
        downloads=10**6,
        likes=10**5,
        runs_self_total=1000,
        runs_self_passed=1000,
        runs_self_min_action_total=1000,  # self-reliability needs 10+ own runs on every action (v1.3)
        bugs_responded_7d=9,
        last_verified="2026-10-04T00:00:00Z",
    )
    r = q(s, now=NOW)
    assert r["categories"] == {
        "docs": 20,
        "self_evidence": 30,
        "independent": 30,
        "community_usage": 0,
        "maintenance": 10,
    }
    assert r["points"] == 90  # community usage needs 10+ runs
    assert r["tier"] == "proven"  # 90 points, but Hardened needs community runs and 2+ OEM combos: points are not tiers


def test_quality_proven_needs_gates_not_just_points():
    q = quality_mod.quality
    s = _sig(
        readme=True,
        failure_modes=True,
        demo=True,
        demo_all_actions=True,
        self_runs=1,
        validators=3,
        bench_models=1,
        independent_device_classes=1,
        last_verified="2026-10-01T00:00:00Z",
    )
    r = q(s, now=NOW)
    assert (
        r["points"] == 17 + 14 + 12 + 6 and r["tier"] == "proven"
    )  # docs 3+3+4+4+3; self 4 + 6 + 4, no reliability yet; + re-verified within 30 days
    assert q({**s, "demo": False}, now=NOW)["tier"] == "runs"  # gate fails, points still >= 35
    assert q({**s, "validators": 2}, now=NOW)["tier"] == "runs"
    own = {**s, "independent_device_classes": 0, "last_verified": None}  # v1.3: Proven on own evidence alone
    assert q(own, now=NOW)["points"] == 17 + 14 and q(own, now=NOW)["tier"] == "runs"  # 31 < 35: points still count
    assert q({**own, "self_devices": 2}, now=NOW)["tier"] == "proven"  # + second own device 4 = 35
    assert q({**own, "self_devices": 2, "validators": 2}, now=NOW)["tier"] == "runs"  # 3 validator units per action


def test_quality_hardened_wilson_and_freshness():
    q = quality_mod.quality
    s = _sig(
        readme=True,
        failure_modes=True,
        demo=True,
        self_runs=1,
        validators=3,
        bench_models=2,
        independent_device_classes=3,
        oem_combos=2,
        community_runs=40,
        community_successes=39,
        last_verified="2026-09-01T00:00:00Z",
    )
    r = q(s, now=NOW)
    assert r["tier"] == "hardened" and r["freshness_multiplier"] == 1.0
    assert r["categories"]["community_usage"] == round(10 * quality_mod.wilson_lower_bound(39, 40))
    assert r["categories"]["independent"] == 12 + 8 + 4 + 4
    assert 0 < r["categories"]["maintenance"] < 6  # last verified 34 days ago: decaying toward 0 at day 60 (v1.2)
    assert q({**s, "community_successes": 30}, now=NOW)["tier"] == "proven"  # LB < 0.80
    stale = q({**s, "last_verified": "2026-05-01T00:00:00Z"}, now=NOW)
    assert stale["freshness_multiplier"] == 0.8 and stale["tier"] == "proven"
    assert q({**s, "last_verified": "2025-01-01T00:00:00Z"}, now=NOW)["freshness_multiplier"] == 0.5
    assert quality_mod.wilson_lower_bound(0, 0) == 0.0
    assert 0.80 < quality_mod.wilson_lower_bound(39, 40) < 0.9


def test_quality_reference_and_provisional_and_freeze():
    q = quality_mod.quality
    s = _sig(
        readme=True,
        failure_modes=True,
        demo=True,
        self_runs=1,
        validators=3,
        bench_models=3,
        demo_all_actions=True,
        before_after=True,
        self_devices=2,
        runs_self_total=200,
        runs_self_passed=200,
        runs_self_min_action_total=200,
        independent_device_classes=3,
        independent_verifier_classes=3,
        oem_combos=3,
        community_runs=200,
        community_successes=200,
        last_verified="2026-10-01T00:00:00Z",
        hardened_since="2026-07-01T00:00:00Z",
        curator_review=True,
        author_contributor=True,
    )
    r = q(s, now=NOW)
    assert r["points"] >= 90 and r["tier"] == "reference"
    assert q({**s, "open_p1_over_14d": True}, now=NOW)["tier"] == "hardened"
    moved = q(s, now=NOW, previous={"tier": "hardened"})
    assert moved["provisional_until"] == "2026-10-12T12:00:00Z"
    kept = q(s, now=NOW, previous={"tier": "reference", "provisional_until": "2026-10-08T00:00:00Z"})
    assert kept["provisional_until"] == "2026-10-08T00:00:00Z"
    assert q(s, now=NOW, previous={"tier": "C"})["provisional_until"] is None  # pre-Amendment tier ignored
    assert q({**s, "frozen_tier": "proven"}, now=NOW)["tier"] == "proven"


def test_registry_shape_matches_contract(tmp_path):
    hub = tmp_path / "skillhub"
    make(
        hub,
        "ghost",
        "demo",
        extras=[
            "README.md",
            "SOFT.md",
            "bench.yaml",
            "demo.gif",
            "helpers.py",
            "data/ref.txt",
            "__pycache__/helpers.cpython-310.pyc",
        ],
    )
    make(hub, "alice", "foo", version="0.2.0", cls="soft")
    (hub / "bob").mkdir()  # empty author: omitted
    (hub / "registry.json").write_text("{}")  # stale output file: ignored

    reg = build_registry.build_registry(hub, now="2026-10-05T12:00:00Z", repo_name="org/repo")

    assert set(reg) == TOP_KEYS
    assert reg["schema_version"] == 2
    assert reg["generated_at"] == "2026-10-05T12:00:00Z"
    assert reg["repo"] == "org/repo"
    assert reg["authors"] == {
        "alice": {"trust": "unverified", "github": "alice", "skills": 1},  # v1.2: verified needs skillhub/REVIEWED
        "ghost": {"trust": "official", "github": "ghost-in-the-droid", "skills": 1},
    }
    assert set(reg["skills"]) == {"ghost/demo", "alice/foo"}

    demo = reg["skills"]["ghost/demo"]
    assert set(demo) == SKILL_KEYS
    assert (demo["author"], demo["slug"], demo["name"], demo["trust"], demo["latest"]) == (
        "ghost",
        "demo",
        "demo",
        "official",
        "1.0.0",
    )
    v = demo["versions"]["1.0.0"]
    assert set(v) == VERSION_KEYS
    assert set(v["fingerprint"]) == FP_KEYS
    assert v["fingerprint"]["app_package"] == "com.example.demo"
    assert v["tag"] is None and v["commit"] is None  # not a git checkout
    assert v["actions"] == ["go", "stop"]
    assert v["data_access"] == ["storage"]
    assert v["has_python"] is True
    assert set(v["files"]) == {"skill.yaml", "README.md", "SOFT.md", "bench.yaml", "helpers.py", "data/ref.txt"}
    raw = (hub / "ghost" / "demo" / "skill.yaml").read_bytes()
    assert v["files"]["skill.yaml"] == "sha256:" + hashlib.sha256(raw).hexdigest()
    assert v["size_bytes"] == sum(len((hub / "ghost" / "demo" / n).read_bytes()) for n in v["files"])
    assert set(demo["quality"]) == QUALITY_KEYS
    assert set(demo["quality"]["signals"]) == SIGNAL_KEYS
    assert demo["quality"]["tier"] == "draft"  # no signed self-run yet
    assert demo["quality"]["signals"]["fingerprints_verified"] == 1
    assert demo["quality"]["signals"]["validators"] == 0  # v1.2: no action has a passing current run yet
    assert demo["quality"]["signals"]["validators_total"] == 2
    zero_action = {c: {"passed": 0, "total": 0} for c in ("self", "maintainer", "ci", "independent")}
    assert demo["quality"]["runs"] == {
        "passed": 0,
        "total": 0,
        "passed_90d": 0,
        "total_90d": 0,
        **ZERO_SPLIT,
        "current_version": "1.0.0",
        "actions": {"go": zero_action, "stop": zero_action},
    }
    assert demo["updated_at"] == "2026-10-05T12:00:00Z"

    foo = reg["skills"]["alice/foo"]
    assert foo["skill_class"] == "soft" and foo["trust"] == "unverified"
    assert foo["quality"]["tier"] == "draft"
    assert foo["versions"]["0.2.0"]["has_python"] is False


def _git(cwd, *args):
    subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True,
        capture_output=True,
        env={
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t",
            "PATH": "/usr/bin:/bin:/usr/local/bin",
            "HOME": str(cwd),
        },
    )


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_registry_reads_tagged_versions_from_git(tmp_path):
    repo = tmp_path / "repo"
    hub = repo / "skillhub"
    make(hub, "alice", "foo", version="1.0.0", extras=["helpers.py"])
    _git(repo, "init", "-q")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "v1")
    _git(repo, "tag", "alice/foo-v1.0.0")
    make(hub, "alice", "foo", version="1.1.0", extras=["helpers.py", "README.md"])
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "v1.1")
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    tagged = subprocess.run(
        ["git", "-C", str(repo), "rev-list", "-n", "1", "alice/foo-v1.0.0"], capture_output=True, text=True
    ).stdout.strip()

    reg = build_registry.build_registry(hub, now="2026-10-05T12:00:00Z")
    foo = reg["skills"]["alice/foo"]
    assert list(foo["versions"]) == ["1.0.0", "1.1.0"]
    assert foo["latest"] == "1.1.0"
    assert foo["versions"]["1.0.0"]["tag"] == "alice/foo-v1.0.0"
    assert foo["versions"]["1.0.0"]["commit"] == tagged
    assert "README.md" not in foo["versions"]["1.0.0"]["files"]
    assert foo["versions"]["1.1.0"]["tag"] is None
    assert foo["versions"]["1.1.0"]["commit"] == head
    assert foo["updated_at"].endswith("Z")

    side = {}
    build_registry.build_registry(hub, now="2026-10-05T12:00:00Z", side=side)
    idx = side["index"]["alice.foo"]
    assert idx["latest"] == "1.1.0" and [v["version"] for v in idx["versions"]] == ["1.0.0", "1.1.0"]
    old, new = idx["versions"]
    tree_at_tag = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "alice/foo-v1.0.0:skillhub/alice/foo"], capture_output=True, text=True
    ).stdout.strip()
    assert old["git_tree"] == tree_at_tag and old["released_at"].endswith("Z")
    assert new["git_tree"] is None and new["released_at"] is None  # untagged: no pin yet
    assert set(old) == {
        "version",
        "tag",
        "commit",
        "git_tree",
        "sha256",
        "size",
        "released_at",
        "attestation",
        "demo",
        "demos",
    }


def test_cli_writes_json_to_stdout(tmp_path):
    hub = tmp_path / "skillhub"
    make(hub, "alice", "foo")
    out = subprocess.run(
        [sys.executable, str(REPO / "tools" / "build_registry.py"), str(hub), "--now", "2026-10-05T12:00:00Z"],
        capture_output=True,
        text=True,
        check=True,
    )
    reg = json.loads(out.stdout)
    assert reg["generated_at"] == "2026-10-05T12:00:00Z"
    assert "alice/foo" in reg["skills"]



def test_underscore_dirs_are_skipped_at_every_level(tmp_path):
    hub = tmp_path / "skillhub"
    make(hub, "alice", "foo")
    make(hub, "alice", "_wip")
    make(hub / "_drafts", "androidworld", "clock")
    make(hub, "_wip", "bar")
    side: dict = {}
    reg = build_registry.build_registry(hub, now=NOW, side=side)
    assert list(reg["skills"]) == ["alice/foo"] and list(reg["authors"]) == ["alice"]
    assert set(side["index"]) == {"alice.foo"} and set(side["skill_md"]) == {"alice/foo"}


def test_committed_registry_carries_no_drafts():
    reg = json.loads((REPO / "skillhub" / "registry.json").read_text())
    assert not [k for k, s in reg["skills"].items() if s.get("status") == "draft"]
    assert not any(k.startswith("_") for k in reg["skills"])
    assert reg["authors"]["androidworld"]["skills"] == sum(1 for s in reg["skills"].values() if s["author"] == "androidworld")

def test_real_skillhub_builds():
    reg = build_registry.build_registry(REPO / "skillhub", now="2026-10-05T12:00:00Z")
    # Official skills live under ghost/; the AndroidWorld benchmark scaffolds under androidworld/ (never official).
    assert reg["authors"]["ghost"]["skills"] >= 9
    # The 19 AndroidWorld TODO scaffolds live under skillhub/_drafts/ and never reach the registry.
    assert reg["authors"]["androidworld"]["skills"] == 1
    assert "androidworld/pro-expense" in reg["skills"]
    assert not any(k.startswith("_") for k in reg["authors"])
    assert reg["authors"]["ghost"]["skills"] + reg["authors"]["androidworld"]["skills"] == len(reg["skills"])
    assert all(s["trust"] != "official" for s in reg["skills"].values() if s["author"] == "androidworld")
    tt = reg["skills"]["ghost/tiktok"]
    assert tt["trust"] == "official"
    assert "upload_video" in tt["versions"][tt["latest"]]["actions"]
    assert reg["skills"]["ghost/send_gmail_email"]["versions"]["1.0.0"]["actions"] == ["recorded"]


def _keypair(root: Path, name: str) -> tuple[Path, str]:
    """Fresh Ed25519 key for one signer: (private key path, 'ssh-ed25519 <base64>')."""
    private = root / f"{name}.key"
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(private)], check=True, capture_output=True, timeout=20
    )
    public = " ".join((root / f"{name}.key.pub").read_text().split()[:2])
    return private, public


def _signed(path: Path, private: Path, **payload) -> dict:
    """Write ``payload`` signed in the run namespace the way evidence.write_evidence does."""
    from gitd.skills.engine.evidence import canonical

    source = path.with_suffix(".payload")
    source.write_bytes(canonical(payload))
    subprocess.run(
        ["ssh-keygen", "-Y", "sign", "-f", str(private), "-n", "ghost-skill-run", str(source)],
        check=True,
        capture_output=True,
        timeout=20,
    )
    data = {
        **payload,
        "signature": {
            "algorithm": "ssh-ed25519",
            "namespace": "ghost-skill-run",
            "public_key": "ssh-ed25519 spoofed",
            "value": source.with_suffix(".payload.sig").read_text(),
        },
    }
    source.unlink()
    source.with_suffix(".payload.sig").unlink()
    path.write_text(json.dumps(data))
    return data


@pytest.mark.skipif(shutil.which("ssh-keygen") is None, reason="ssh-keygen not installed")
def test_run_artifacts_are_verified_before_they_drive_signals(tmp_path):
    hub = tmp_path / "skillhub"
    d = make(hub, "alice", "foo", extras=["README.md"])
    (d / "runs").mkdir()
    (d / "verifications").mkdir()
    keys = {name: _keypair(tmp_path, name) for name in ("alice", "bob", "carol", "dave", "ci")}
    (hub / "SIGNERS").write_text(
        "# comment line\n"
        + "".join(f'{name} namespaces="ghost-skill-run" {keys[name][1]}\n' for name in ("alice", "bob", "carol"))
    )
    (hub / "verifier-keys.yml").write_text(
        "version: 1\nprincipals:\n  ghost-ci-emulator:\n    tier: platform\n    keys: ['" + keys["ci"][1] + "']\n"
    )
    base = {
        "skill": "alice/foo",
        "version": "1.0.0",
        "device_backend": "device",
        "simulation": False,
        "app_version": "1.0",
    }

    def art(path, signer, **kw):
        ok = bool(kw.get("success"))
        acts = {"actions": [{"name": "go", "success": ok}, {"name": "stop", "success": ok}]}  # v1.2: per-action credit
        return _signed(d / path, keys[signer][0], **{**base, **acts, **kw})

    fp = {"manufacturer": "asus", "os_version": "14"}
    art("runs/aaa-1.json", "alice", success=True, finished_at="2026-10-01T00:00:00Z", fingerprint=fp)
    art("runs/fff-0.json", "alice", success=False, finished_at="2026-01-01T00:00:00Z")  # outside 90d
    art(
        "runs/ggg-3.json",
        "alice",
        success=True,
        finished_at="2026-10-02T00:00:00Z",
        bench={"suite": "androidworld", "task_id": "ExpenseAddSingle", "arm": "after_replay", "seed": 1},
    )
    (d / "runs/bbb-2.json").write_text(json.dumps({**base, "success": True}))  # unsigned
    art("runs/sim-4.json", "alice", success=True, simulation=True, device_backend="fake")  # fake device
    art("runs/other-5.json", "alice", success=True, skill="alice/bar")  # copied from another skill
    art("runs/dave-6.json", "dave", success=True)  # key not in SIGNERS
    art("runs/bench-7.json", "alice", success=True, bench={"suite": "androidworld", "arm": "sideways"})
    tampered = art("runs/tmp-8.json", "alice", success=False)
    tampered["success"] = True
    (d / "runs/tmp-8.json").write_text(json.dumps(tampered))
    art(
        "verifications/bob-ccc-1.json",
        "bob",
        verifier="bob",
        success=True,
        finished_at="2026-10-03T00:00:00Z",
        fingerprint={"manufacturer": "samsung", "os_version": "15"},
    )
    art("verifications/bob-ccc-2.json", "bob", verifier="bob", success=False, finished_at="2026-09-01T00:00:00Z")
    art("verifications/alice-ddd-1.json", "alice", verifier="alice", success=True, finished_at="2026-10-03T00:00:00Z")
    art(
        "verifications/carol-eee-1.json",
        "carol",
        verifier="carol",
        success=True,
        verifier_tier="master",
        finished_at="2026-10-04T00:00:00Z",
    )
    art("verifications/bob-hhh-1.json", "carol", verifier="bob", success=True)  # bob's name, carol's key
    art(
        "verifications/ghost-ci-emulator-iii-1.json",
        "ci",
        verifier="ghost-ci-emulator",
        success=True,
        verifier_tier="novice",
        finished_at="2026-10-04T00:00:00Z",
        device_class="emu/14",
    )

    warnings = []
    reg = build_registry.build_registry(hub, now="2026-10-05T12:00:00Z", warn=warnings.append)
    foo = reg["skills"]["alice/foo"]
    sig = foo["quality"]["signals"]
    assert sig["self_runs"] == 3  # aaa + ggg + alice's own verification, both actions
    assert sig["independent_runs"] == 2  # bob (latest per fp) + carol; ci is its own class
    assert sig["ci_runs"] == 1 and sig["maintainer_runs"] == 0
    assert sig["independent_device_classes"] == 2
    assert sig["independent_verifier_classes"] == 1  # carol (master); platform ci is not a human tier
    assert sig["community_runs"] == 2 and sig["community_successes"] == 2
    assert sig["oem_combos"] == 2
    assert sig["last_verified"] == "2026-10-04T00:00:00Z"  # last NON-self passing run
    assert sig["last_self_run"] == "2026-10-03T00:00:00Z"
    assert sig["runs_bench"] == 1
    assert foo["quality"]["tier"] == "runs"
    assert sig["runs_rejected"] == 7
    assert sig["runs_rejected_reasons"] == {
        "bad-bench-block": 1,
        "bad-signature": 3,
        "simulated": 1,
        "unsigned": 1,
        "wrong-skill": 1,
    }
    # quality.runs: every VERIFIED current artifact by class (no dedup)
    runs = foo["quality"]["runs"]
    assert (runs["passed"], runs["total"], runs["passed_90d"], runs["total_90d"]) == (6, 8, 6, 7)
    assert runs["self"] == {"passed": 3, "total": 4} and runs["independent"] == {"passed": 2, "total": 3}
    assert runs["ci"] == {"passed": 1, "total": 1} and runs["maintainer"] == {"passed": 0, "total": 0}
    assert runs["previous_versions"] == {"passed": 0, "total": 0} and runs["current_version"] == "1.0.0"
    assert runs["rejected"] == {"total": 7, "reasons": sig["runs_rejected_reasons"]} and runs["bench"] == 1
    assert runs["actions"]["go"]["independent"] == {"passed": 2, "total": 3}
    assert {v["principal"]: v["class"] for v in runs["verifiers"]} == {
        "bob": "independent",
        "carol": "independent",
        "ghost-ci-emulator": "ci",
    }
    assert any(m.startswith("evidence rejected: 7 artifact(s)") for m in warnings)
    assert any("bad-signature: alice/foo/runs/tmp-8.json" in m for m in warnings)
    files = foo["versions"]["1.0.0"]["files"]
    assert not any(n.startswith(("runs/", "verifications/")) for n in files)


def test_no_trust_files_means_no_evidence_counts(tmp_path):
    hub = tmp_path / "skillhub"
    d = make(hub, "alice", "foo", extras=["README.md"])
    (d / "runs").mkdir()
    (d / "runs/aaa-1.json").write_text(
        json.dumps(
            {
                "skill": "alice/foo",
                "app_version": "1.0",
                "success": True,
                "signature": {
                    "namespace": "ghost-skill-run",
                    "value": "-----BEGIN SSH SIGNATURE-----\nnope\n-----END SSH SIGNATURE-----\n",
                },
            }
        )
    )
    reg = build_registry.build_registry(hub, now="2026-10-05T12:00:00Z", warn=lambda m: None)
    q = reg["skills"]["alice/foo"]["quality"]
    assert q["tier"] == "draft" and q["runs"]["total"] == 0
    assert q["runs"]["rejected"] == {"total": 1, "reasons": {"bad-signature": 1}}


def test_rejected_counts_do_not_leak_into_later_skills(tmp_path):
    """The rejected list is shared across the whole build; each skill reports only its own entries."""
    hub = tmp_path / "skillhub"
    d = make(hub, "alice", "foo", extras=["README.md"])
    make(hub, "alice", "zzz", extras=["README.md"])
    (d / "runs").mkdir()
    (d / "runs/aaa-1.json").write_text(
        json.dumps(
            {
                "skill": "alice/foo",
                "app_version": "1.0",
                "success": True,
                "signature": {
                    "namespace": "ghost-skill-run",
                    "value": "-----BEGIN SSH SIGNATURE-----\nnope\n-----END SSH SIGNATURE-----\n",
                },
            }
        )
    )
    warnings = []
    reg = build_registry.build_registry(hub, now="2026-10-05T12:00:00Z", warn=warnings.append)
    assert reg["skills"]["alice/foo"]["quality"]["runs"]["rejected"] == {"total": 1, "reasons": {"bad-signature": 1}}
    assert reg["skills"]["alice/zzz"]["quality"]["runs"]["rejected"] == {"total": 0, "reasons": {}}
    assert reg["skills"]["alice/zzz"]["quality"]["signals"]["runs_rejected"] == 0
    assert any(m.startswith("evidence rejected: 1 artifact(s)") for m in warnings)


def test_index_and_skill_md_side_files(tmp_path):
    hub = tmp_path / "skillhub"
    make(hub, "alice", "foo", extras=["helpers.py"])
    make(hub, "ghost", "demo")
    stale = hub / "registry" / "index" / "gone.skill.json"
    stale.parent.mkdir(parents=True)
    stale.write_text("{}")

    side = {}
    reg = build_registry.build_registry(hub, now="2026-10-05T12:00:00Z", side=side)
    assert "registry" not in reg["authors"]  # reserved output dir, not an author
    assert set(side["index"]) == {"alice.foo", "ghost.demo"}
    entry = side["index"]["alice.foo"]["versions"][0]
    files = reg["skills"]["alice/foo"]["versions"]["1.0.0"]["files"]
    manifest = "".join(f"{h} {n}\n" for n, h in sorted(files.items()))
    assert entry["sha256"] == "sha256:" + hashlib.sha256(manifest.encode()).hexdigest()
    assert entry["size"] == reg["skills"]["alice/foo"]["versions"]["1.0.0"]["size_bytes"]
    assert entry["git_tree"] is None and entry["attestation"] is None  # not a git checkout

    written = build_registry.write_side_files(hub, side)
    assert not stale.exists()
    assert (hub / "registry" / "index" / "alice.foo.json") in written
    md = (hub / "alice" / "foo" / "SKILL.md").read_text()
    assert md.startswith(
        '---\nname: alice-foo\ndescription: "Start the example workflow | Stop the example workflow"\n---\n'
    )
    assert "ghost skill run alice/foo go --device <serial>" in md
    assert build_registry.write_side_files(hub, side) == []  # idempotent

    # generated SKILL.md is not shipped and does not change hashes
    reg2 = build_registry.build_registry(hub, now="2026-10-05T12:00:00Z")
    assert "SKILL.md" not in reg2["skills"]["alice/foo"]["versions"]["1.0.0"]["files"]
    assert reg2["skills"]["alice/foo"]["versions"] == reg["skills"]["alice/foo"]["versions"]


def test_cli_no_write_skips_side_files(tmp_path):
    hub = tmp_path / "skillhub"
    make(hub, "alice", "foo")
    subprocess.run(
        [sys.executable, str(REPO / "tools" / "build_registry.py"), str(hub), "--no-write"],
        capture_output=True,
        check=True,
    )
    assert not (hub / "registry").exists() and not (hub / "alice" / "foo" / "SKILL.md").exists()
    subprocess.run(
        [sys.executable, str(REPO / "tools" / "build_registry.py"), str(hub)], capture_output=True, check=True
    )
    assert (hub / "registry" / "index" / "alice.foo.json").is_file()
    assert (hub / "alice" / "foo" / "SKILL.md").is_file()


def test_quality_runs_is_pure_passthrough():
    q = quality_mod.quality
    assert set(q({}, now=NOW)["runs"]) == RUNS_KEYS
    assert q({}, now=NOW)["runs"] == {"passed": 0, "total": 0, "passed_90d": 0, "total_90d": 0, **ZERO_SPLIT}
    s = {"runs_passed": 7, "runs_total": 9, "runs_passed_90d": 3, "runs_total_90d": 4}
    assert q(s, now=NOW)["runs"] == {"passed": 7, "total": 9, "passed_90d": 3, "total_90d": 4, **ZERO_SPLIT}
    split = {"runs_self_passed": 5, "runs_self_total": 6, "runs_independent_passed": 2, "runs_independent_total": 3}
    r = q({**s, **split}, now=NOW)["runs"]
    assert r["self"] == {"passed": 5, "total": 6} and r["independent"] == {"passed": 2, "total": 3}
    assert s == {"runs_passed": 7, "runs_total": 9, "runs_passed_90d": 3, "runs_total_90d": 4}  # not mutated


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_unrelated_commit_leaves_outputs_byte_identical(tmp_path):
    repo = tmp_path / "repo"
    hub = repo / "skillhub"
    make(hub, "alice", "foo", extras=["helpers.py", "README.md"])
    make(hub, "ghost", "demo")
    _git(repo, "init", "-q")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "skills")
    skill_commit = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True
    ).stdout.strip()

    def build(out):
        subprocess.run(
            [sys.executable, str(REPO / "tools" / "build_registry.py"), str(hub), "-o", str(out)],
            capture_output=True,
            check=True,
        )
        side = {
            p.relative_to(hub).as_posix(): p.read_bytes()
            for p in sorted(hub.rglob("*"))
            if p.is_file() and (p.name == "SKILL.md" or "registry" in p.parts)
        }
        return out.read_bytes(), side

    first, side1 = build(tmp_path / "r1.json")
    (repo / "unrelated.txt").write_text("x\n")
    _git(repo, "add", "unrelated.txt")
    _git(repo, "commit", "-q", "-m", "unrelated")
    second, side2 = build(tmp_path / "r2.json")

    assert first == second
    assert side1 == side2 and "registry/index/alice.foo.json" in side1
    reg = json.loads(first)
    assert reg["skills"]["alice/foo"]["versions"]["1.0.0"]["commit"] == skill_commit

    # committing the generated SKILL.md wrappers does not move anything either
    _git(repo, "add", "skillhub/alice/foo/SKILL.md", "skillhub/ghost/demo/SKILL.md")
    _git(repo, "commit", "-q", "-m", "regen wrappers")
    after_regen, side3 = build(tmp_path / "r2b.json")
    assert after_regen == first and side3 == side1

    # touching the skill does move its commit
    (hub / "alice" / "foo" / "README.md").write_text("# changed\n")
    _git(repo, "add", "skillhub/alice/foo/README.md")
    _git(repo, "commit", "-q", "-m", "touch foo")
    third = json.loads(build(tmp_path / "r3.json")[0])
    assert third["skills"]["alice/foo"]["versions"]["1.0.0"]["commit"] != skill_commit
    assert third["skills"]["ghost/demo"]["versions"]["1.0.0"]["commit"] == skill_commit


def test_schema_marks_v1_legacy(tmp_path):
    hub = tmp_path / "skillhub"
    make(hub, "alice", "foo")
    legacy = hub / "ghost" / "old"
    legacy.mkdir(parents=True)
    (legacy / "skill.yaml").write_text("name: old\nversion: 1.0.0\ntos_risk: low\napp_package: com.x\n")
    reg = build_registry.build_registry(hub, now="2026-10-05T12:00:00Z")
    assert reg["skills"]["alice/foo"]["schema"] == "v2"
    assert reg["skills"]["ghost/old"]["schema"] == "v1"


def test_real_hub_is_all_v2_after_migrate():
    reg = build_registry.build_registry(REPO / "skillhub", now="2026-10-05T12:00:00Z")
    assert {k: v["schema"] for k, v in reg["skills"].items() if v["schema"] != "v2"} == {}


def test_demo_signal_accepts_webm_mp4_gif_and_none_ship_to_installs(tmp_path):
    hub = tmp_path / "skillhub"
    for slug, demo in (("w", "demo.webm"), ("m", "demo.mp4"), ("g", "demo.gif"), ("n", None)):
        make(hub, "ghost", slug, extras=["README.md"] + ([demo] if demo else []))
    reg = build_registry.build_registry(hub, now=NOW, repo_name="org/repo")
    for slug, want in (("w", True), ("m", True), ("g", True), ("n", False)):
        entry = reg["skills"][f"ghost/{slug}"]
        assert entry["quality"]["signals"]["demo"] is want
        files = entry["versions"]["1.0.0"]["files"]
        assert not any(name.startswith("demo.") for name in files)


def test_runs_split_sums_to_totals_on_real_registry():
    reg = build_registry.build_registry(REPO / "skillhub", now="2026-10-06T00:00:00Z")
    for key, entry in reg["skills"].items():
        r = entry["quality"]["runs"]
        classes = ("self", "maintainer", "ci", "independent")
        assert sum(r[c]["passed"] for c in classes) == r["passed"], key
        assert sum(r[c]["total"] for c in classes) == r["total"], key


@pytest.mark.parametrize(
    "prompt",
    [
        None,
        "",
        "   ",
        "TODO write prompt",
        "Please fixme here",
        "Need TBD content",
        "short text",
        "long_action_name",
        "LONG ACTION NAME",
    ],
)
def test_registry_rejects_placeholder_ref_prompts(tmp_path, capsys, prompt):
    import yaml

    hub = tmp_path / "hub"
    skill = make(hub, "alice", "sample")
    raw = yaml.safe_load((skill / "skill.yaml").read_text())
    raw["actions"][0].update(name="long_action_name", ref_prompt=prompt)
    (skill / "skill.yaml").write_text(yaml.safe_dump(raw))
    assert build_registry.main([str(hub), "--no-write"]) == 2
    assert "alice/sample/long_action_name: ref_prompt" in capsys.readouterr().err
    assert not (hub / "registry").exists()


def test_main_refuses_to_build_without_ssh_keygen(monkeypatch, capsys):
    """Without ssh-keygen every signature fails closed; the build must not publish a void registry."""
    hub = Path(__file__).resolve().parent.parent / "skillhub"
    assert any(hub.glob("*/*/runs/*.json"))
    monkeypatch.setattr(build_registry.shutil, "which", lambda name: None)
    assert build_registry.main([str(hub), "--no-write"]) == 2
    assert "ssh-keygen is required" in capsys.readouterr().err
    monkeypatch.setattr(build_registry.shutil, "which", lambda name: "/usr/bin/ssh-keygen")
    assert not build_registry.signing_tool_missing(hub)



def test_registry_accepts_descriptive_prompt_boundary():
    build_registry.validate_ref_prompts({"actions": [{"name": "read", "ref_prompt": "Read my note"}]}, "alice/sample")


def test_registry_fails_closed_on_missing_tos_risk(tmp_path, capsys):
    import yaml

    hub = tmp_path / "hub"
    skill = make(hub, "alice", "sample")
    raw = yaml.safe_load((skill / "skill.yaml").read_text())
    del raw["tos_risk"]
    (skill / "skill.yaml").write_text(yaml.safe_dump(raw))
    assert build_registry.main([str(hub), "--no-write"]) == 2
    assert "alice/sample: `tos_risk:` must be one of" in capsys.readouterr().err
    assert not (hub / "registry").exists()


def test_shipped_risky_skills_declare_tos_risk_high():
    import yaml

    root = REPO
    for slug in ("tiktok", "tiktok_ios"):
        raw = yaml.safe_load((root / "skillhub" / "ghost" / slug / "skill.yaml").read_text())
        assert raw["tos_risk"] == "high", slug
    assert yaml.safe_load((root / "registry" / "tiktok" / "skill.yaml").read_text())["tos_risk"] == "high"


def test_tos_risk_legacy_list_only_names_skills_without_the_field():
    import yaml

    root = REPO / "skillhub"
    for ref in build_registry.TOS_RISK_LEGACY_UNDECLARED:
        raw = yaml.safe_load((root / ref / "skill.yaml").read_text())
        assert "tos_risk" not in raw, f"{ref} declares tos_risk now: drop it from the legacy list"
