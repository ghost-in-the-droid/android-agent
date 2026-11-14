"""Scoring v1.2 "honest scoring": one test per audit item (briefs/QUALITY_AUDIT.md section 5)."""

import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(shutil.which("ssh-keygen") is None, reason="ssh-keygen not installed")


def _load(name):
    spec = importlib.util.spec_from_file_location(f"_honest_{name}", REPO / "tools" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


registry = _load("build_registry")
quality = _load("quality")
NOW = "2026-10-22T12:00:00Z"
KEY_LINE = 'namespaces="ghost-skill-run"'

SKILL_YAML = """\
name: {slug}
version: {version}
author: {author}
description: "{slug}"
skill_class: hard
tos_risk: low
license: MIT
generated_with: hand
status: {status}
data_access: []
fingerprint: {{os: android, os_version: ">=14", hardware: "*", app_package: com.example.{slug}, app_version: ">=1"}}
actions:
  - name: go
    ref_prompt: Start the example workflow
    steps: [{{action: sleep, duration_s: 1}}]
    end_state_validator: [{{kind: custom_python, function: "validators:go_ok"}}, {{kind: text_visible, text: ok}}]
  - name: stop
    ref_prompt: Stop the example workflow
    steps: [{{action: sleep, duration_s: 1}}]
    end_state_validator: [{{kind: text_visible, text: "{{query}} done"}}, {{kind: element_present, resource_id: x}}]
"""


def keypair(root: Path, name: str):
    private = root / f"{name}.key"
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(private)], check=True, capture_output=True)
    return private, " ".join((root / f"{name}.key.pub").read_text().split()[:2])


def signed(path: Path, private: Path, **payload):
    from gitd.skills.engine.evidence import canonical

    source = path.with_suffix(".payload")
    source.write_bytes(canonical(payload))
    subprocess.run(
        ["ssh-keygen", "-Y", "sign", "-f", str(private), "-n", "ghost-skill-run", str(source)],
        check=True,
        capture_output=True,
    )
    data = {
        **payload,
        "signature": {
            "algorithm": "ssh-ed25519",
            "namespace": "ghost-skill-run",
            "public_key": "x",
            "value": source.with_suffix(".payload.sig").read_text(),
        },
    }
    source.unlink()
    source.with_suffix(".payload.sig").unlink()
    path.write_text(json.dumps(data))
    return data


@pytest.fixture
def hub(tmp_path):
    """alice/foo at version 1.1.0 with two actions; keys for alice, the maintainer, carol (community), ci."""
    hub = tmp_path / "skillhub"
    skill = hub / "alice" / "foo"
    (skill / "runs").mkdir(parents=True)
    (skill / "verifications").mkdir()
    (skill / "skill.yaml").write_text(SKILL_YAML.format(slug="foo", version="1.1.0", author="alice", status="active"))
    (skill / "README.md").write_text("# foo\n")
    (skill / "validators.py").write_text("def go_ok(device, context):\n    return True\n")
    keys = {n: keypair(tmp_path, n) for n in ("alice", "maint", "carol", "ci")}
    (hub / "SIGNERS").write_text("".join(f"{n} {KEY_LINE} {keys[n][1]}\n" for n in ("alice", "carol")))
    (hub / "verifier-keys.yml").write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "principals": {
                    "ghost": {"tier": "maintainer", "operator": "maintainers", "keys": [keys["maint"][1]]},
                    "ghost-aw-replay": {
                        "tier": "platform",
                        "operator": "AndroidWorld replay on the lab emulator",
                        "keys": [],
                    },
                    "ghost-ci-emulator": {"tier": "platform", "operator": "hosted CI", "keys": [keys["ci"][1]]},
                },
            }
        )
    )
    from gitd.skills.engine.manifest import skill_content_digest

    base = {
        "skill": "alice/foo",
        "version": "1.1.0",
        "device_backend": "device",
        "simulation": False,
        "app_version": "1.0",
        "finished_at": "2026-10-20T00:00:00Z",
        "fingerprint": {
            "hardware": "Pixel/8",
            "os_version": "14",
            "app_version": "1.0",
            "screen_wxh": "1080x2400",
            "density": 420,
            "locale": "en-US",
        },
        "fingerprint_hash": "f" * 64,
        "device_class": "Pixel/8/14",
        "emulator": False,
    }

    def art(sub, name, signer, actions=("go", "stop"), ok=True, **kw):
        acts = [{"name": a, "success": ok} for a in actions]
        current = {"skill_sha256": skill_content_digest(skill)}  # digest of the skill dir as it is NOW
        return signed(skill / sub / name, keys[signer][0], **{**base, **current, "success": ok, "actions": acts, **kw})

    return hub, skill, keys, art


def build(hub, **kw):
    return registry.build_registry(hub, now=NOW, warn=lambda m: None, **kw)["skills"]["alice/foo"]


# ── P0-1: a maintainer key never counts as independent, whatever the label says
def test_p0_1_maintainer_key_under_a_platform_label_is_maintainer_evidence(hub):
    hub_dir, skill, keys, art = hub
    art(
        "verifications",
        "ghost-aw-replay-a.json",
        "maint",
        verifier="ghost-aw-replay",
        fingerprint_hash="a" * 64,
        device_class="emu/13",
    )
    art(
        "verifications",
        "ghost-aw-replay-b.json",
        "alice",
        verifier="ghost-aw-replay",  # author key, same label
        fingerprint_hash="b" * 64,
        device_class="emu/14",
    )
    art(
        "verifications",
        "carol-c.json",
        "carol",
        verifier="carol",
        fingerprint_hash="c" * 64,
        device_class="Fairphone/5/14",
    )
    art("verifications", "ghost-ci-emulator-d.json", "ci", verifier="ghost-ci-emulator", fingerprint_hash="d" * 64)
    q = build(hub_dir)["quality"]
    runs, sig = q["runs"], q["signals"]
    assert runs["maintainer"] == {"passed": 2, "total": 2}
    assert runs["independent"] == {"passed": 1, "total": 1} and sig["independent_runs"] == 1
    assert runs["ci"] == {"passed": 1, "total": 1} and sig["ci_runs"] == 1
    assert sig["maintainer_runs"] == 2 and sig["independent_device_classes"] == 1
    assert q["categories"]["independent"] == 12  # carol only
    labels = {v["principal"]: (v["class"], v["label"]) for v in runs["verifiers"]}
    assert labels["ghost-aw-replay"] == ("maintainer", "AndroidWorld replay on the lab emulator")
    assert labels["carol"] == ("independent", "@carol") and labels["ghost-ci-emulator"] == ("ci", "hosted CI")


def test_p0_1_trust_files_refuse_a_key_under_two_principals(tmp_path):
    hub = tmp_path / "skillhub"
    hub.mkdir()
    _, pub = keypair(tmp_path, "k")
    (hub / "SIGNERS").write_text(f"alice {KEY_LINE} {pub}\n")
    (hub / "verifier-keys.yml").write_text(
        yaml.safe_dump({"version": 1, "principals": {"ghost": {"tier": "maintainer", "keys": [pub]}}})
    )
    with pytest.raises(ValueError, match="listed for both"):
        registry.TrustStore(hub)
    (hub / "SIGNERS").write_text("")
    (hub / "verifier-keys.yml").write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "principals": {
                    "ghost": {"tier": "maintainer", "keys": [pub]},
                    "ghost-aw-replay": {"tier": "platform", "keys": [pub]},
                },
            }
        )
    )
    with pytest.raises(ValueError, match="listed for both"):
        registry.TrustStore(hub)


def test_p0_1_committed_trust_files_have_unique_keys_and_empty_platform_verifiers():
    data = yaml.safe_load((REPO / "skillhub" / "verifier-keys.yml").read_text())
    assert data["principals"]["ghost-aw-replay"]["keys"] == [] and data["principals"]["ghost-ci-emulator"]["keys"] == []
    registry.TrustStore(REPO / "skillhub")  # raises on any duplicate


# ── P0-3: only the current version (and matching content digest) counts
def test_p0_3_only_current_version_and_matching_digest_count(hub):
    hub_dir, skill, keys, art = hub
    art("runs", "cur.json", "alice")
    art("runs", "old.json", "alice", version="1.0.0")
    art("runs", "stale.json", "alice", skill_sha256="sha256:" + "0" * 64)  # same version, different bytes
    art("runs", "legacy.json", "alice", skill_sha256=None)  # unbound helper evidence is rejected
    q = build(hub_dir)["quality"]
    assert q["runs"]["current_version"] == "1.1.0"
    assert q["runs"]["self"] == {"passed": 1, "total": 1}
    assert q["runs"]["previous_versions"] == {"passed": 2, "total": 2}
    assert q["signals"]["self_runs"] == 1 and q["tier"] == "runs"
    assert q["runs"]["rejected"] == {"total": 1, "reasons": {"unbound-helper": 1}}
    (skill / "skill.yaml").write_text(SKILL_YAML.format(slug="foo", version="1.2.0", author="alice", status="active"))
    q = build(hub_dir)["quality"]
    assert q["runs"]["self"] == {"passed": 0, "total": 0} and q["runs"]["previous_versions"]["total"] == 3
    assert q["tier"] == "draft"


# ── P1-4: trust values
def test_p1_4_trust_is_never_verified_without_a_recorded_review(hub, tmp_path):
    hub_dir, skill, keys, art = hub
    assert build(hub_dir)["trust"] == "unverified"
    (hub_dir / "REVIEWED").write_text("# reviews\nalice/foo C-K-Loan 0123456\n")
    assert build(hub_dir)["trust"] == "verified"
    assert (
        registry.author_trust("ghost") == "official" and registry.author_trust("androidworld", "x", {}) == "benchmark"
    )
    assert registry.author_trust("bob", "y", {"alice/foo": {}}) == "unverified"
    assert (REPO / "skillhub" / "REVIEWED").is_file()
    assert not [
        ln for ln in (REPO / "skillhub" / "REVIEWED").read_text().splitlines() if ln.strip() and not ln.startswith("#")
    ]


# ── P1-5: validators count only on exercised actions, never for drafts
def test_p1_5_validators_need_a_passing_run_on_every_action(hub):
    hub_dir, skill, keys, art = hub
    assert build(hub_dir)["quality"]["signals"]["validators"] == 0  # no runs at all
    art("runs", "go-only.json", "alice", actions=("go",))
    assert build(hub_dir)["quality"]["signals"]["validators"] == 0  # stop never passed
    art("runs", "both.json", "alice")
    sig = build(hub_dir)["quality"]["signals"]
    assert sig["validators"] == 3 and sig["validators_total"] == 4  # weakest action: stop = 2 + 1
    (skill / "skill.yaml").write_text(SKILL_YAML.format(slug="foo", version="1.1.0", author="alice", status="draft"))
    art("runs", "draft.json", "alice")  # digest changed with the yaml
    assert build(hub_dir)["quality"]["signals"]["validators"] == 0


# ── P1-7: maintenance from non-self runs, decaying against the real build date
def test_p1_7_reverified_ignores_self_runs_and_decays(hub):
    hub_dir, skill, keys, art = hub
    art("runs", "self.json", "alice", finished_at="2026-10-21T00:00:00Z")
    q = build(hub_dir)["quality"]
    assert q["signals"]["last_verified"] is None and q["signals"]["last_self_run"] == "2026-10-21T00:00:00Z"
    assert q["categories"]["maintenance"] == 0
    art(
        "verifications",
        "ghost-aw-replay-m.json",
        "maint",
        verifier="ghost-aw-replay",
        finished_at="2026-10-20T00:00:00Z",
    )
    assert build(hub_dir)["quality"]["categories"]["maintenance"] == 6
    sig = {"last_verified": "2026-10-20T00:00:00Z", "manifest_valid": True}
    assert quality.quality(sig, now="2026-11-04T00:00:00Z")["categories"]["maintenance"] == 6  # day 15: full
    assert quality.quality(sig, now="2026-12-04T00:00:00Z")["categories"]["maintenance"] == 3  # day 45: half
    assert quality.quality(sig, now="2026-12-19T00:00:00Z")["categories"]["maintenance"] == 0  # day 60: gone
    assert json.loads((REPO / "skillhub/scoring/v1.json").read_text())["categories"]["maintenance"]["decay_days"] == 60
    text = (REPO / "tools" / "ci" / "registry.py").read_text()
    assert '"--now", now' in text and "datetime.now(timezone.utc)" in text


# ── P1-8: per-action run credit
def test_p1_8_run_credit_is_the_weakest_action(hub):
    hub_dir, skill, keys, art = hub
    for i in range(3):
        art("runs", f"go{i}.json", "alice", actions=("go",))
    art("runs", "stop0.json", "alice", actions=("stop",))
    art("runs", "fail.json", "alice", ok=False)
    q = build(hub_dir)["quality"]
    assert q["signals"]["self_runs"] == 1 and q["runs"]["self"] == {"passed": 4, "total": 5}
    assert q["runs"]["actions"]["go"]["self"] == {"passed": 3, "total": 4}
    assert q["runs"]["actions"]["stop"]["self"] == {"passed": 1, "total": 2}


# ── P2-10: bench models come from artifacts, not bench.yaml
def test_p2_10_bench_models_from_verified_artifacts_only(hub):
    hub_dir, skill, keys, art = hub
    (skill / "bench.yaml").write_text("benches:\n  - with_skill: {brain: gpt}\n  - with_skill: {brain: claude}\n")
    assert build(hub_dir)["quality"]["signals"]["bench_models"] == 0
    bench = {"suite": "androidworld", "task_id": "T", "arm": "after_mcp"}
    art("runs", "b1.json", "alice", bench=bench, model="claude-haiku-5-5")
    art("runs", "b2.json", "alice", bench=bench, model="claude-haiku-5-5")
    art("runs", "b3.json", "alice", bench={**bench, "arm": "after_replay"}, model="deterministic")
    assert build(hub_dir)["quality"]["signals"]["bench_models"] == 1


# ── P2-11: official skills no longer get manifest points for missing required fields
def test_p2_11_manifest_invalid_when_required_fields_are_missing(tmp_path):
    hub = tmp_path / "skillhub"
    skill = hub / "ghost" / "bar"
    skill.mkdir(parents=True)
    text = SKILL_YAML.format(slug="bar", version="1.0.0", author="ghost", status="active")
    (skill / "skill.yaml").write_text(
        "\n".join(ln for ln in text.splitlines() if not ln.startswith(("license:", "generated_with:"))) + "\n"
    )
    (skill / "validators.py").write_text("def go_ok(device, context):\n    return True\n")
    assert registry._manifest_valid(skill) is False
    (skill / "skill.yaml").write_text(text)
    assert registry._manifest_valid(skill) is True


# ── P2-13: the verifier field is required
def test_p2_13_verification_without_verifier_field_is_rejected(hub):
    hub_dir, skill, keys, art = hub
    art("verifications", "carol-x.json", "carol", fingerprint_hash="c" * 64)  # no verifier field
    q = build(hub_dir)["quality"]
    assert q["runs"]["independent"]["total"] == 0 and q["runs"]["rejected"] == {
        "total": 1,
        "reasons": {"no-verifier": 1},
    }


# ── P2-14: emulator flag recorded and surfaced; missing = unknown
def test_p2_14_emulator_runs_are_counted_and_unknown_is_not_hardware(hub, tmp_path, monkeypatch):
    hub_dir, skill, keys, art = hub
    art("runs", "emu.json", "alice", emulator=True)
    art("runs", "hw.json", "alice", emulator=False)
    art("runs", "old.json", "alice", emulator=None)
    assert build(hub_dir)["quality"]["runs"]["emulator"] == {"passed": 1, "total": 1, "unknown": 1}
    from gitd.skills.engine import evidence

    calls = []

    def fake_run(args, **kw):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, stdout="1\n\n", stderr="")

    monkeypatch.setattr(evidence.subprocess, "run", fake_run)
    assert evidence.detect_emulator("emulator-5554") is True
    assert "getprop ro.kernel.qemu; getprop ro.boot.qemu" in calls[-1]
    assert evidence.detect_emulator("fake:x") is None and evidence.detect_emulator("ios:x") is None


def test_write_evidence_records_skill_digest_and_emulator(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from gitd.skills.engine import evidence
    from gitd.skills.engine.manifest import skill_content_digest

    monkeypatch.setenv("GHOST_CONFIG_DIR", str(tmp_path / "config"))
    skill_dir = tmp_path / "skillhub" / "alice" / "foo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "skill.yaml").write_text("name: foo\nversion: 1.0.0\n")
    skill = SimpleNamespace(
        author="alice",
        name="foo",
        version="1.0.0",
        skill_dir=skill_dir,
        fingerprint=SimpleNamespace(app_package="com.example.foo"),
    )
    result = SimpleNamespace(action="go", success=True, duration_ms=1.0, error=None, data={}, trace=[])
    fp = {
        "os": "android",
        "os_version": "14",
        "hardware": "Pixel/8",
        "app_package": "com.example.foo",
        "app_version": "1",
    }
    path = evidence.write_evidence(skill, [result], fp, emulator=True)
    data = json.loads(path.read_text())
    assert data["skill_sha256"] == skill_content_digest(skill_dir) and data["emulator"] is True
    assert data["skill_sha256"].startswith("sha256:")


# ── P2-12: an independent fingerprint the author also recorded on is not a new device class
def test_p2_12_independent_fingerprint_in_self_set_is_not_a_device_class(hub):
    hub_dir, skill, keys, art = hub
    art("runs", "self.json", "alice", fingerprint_hash="s" * 64, device_class="Pixel/8/14")
    art(
        "verifications",
        "carol-same.json",
        "carol",
        verifier="carol",
        fingerprint_hash="s" * 64,
        device_class="Pixel/8/14",
    )
    q = build(hub_dir)["quality"]
    assert q["runs"]["independent"] == {"passed": 1, "total": 1}
    assert q["signals"]["independent_devices"] == 0 and q["signals"]["independent_device_classes"] == 0
    assert q["categories"]["independent"] == 0
    art(
        "verifications",
        "carol-new.json",
        "carol",
        verifier="carol",
        fingerprint_hash="n" * 64,
        device_class="Fairphone/5/14",
    )
    q = build(hub_dir)["quality"]
    assert q["signals"]["independent_devices"] == 1 and q["categories"]["independent"] == 12


def test_scoring_table_is_v1_3_keeps_every_v1_2_rule_and_history():
    table = json.loads((REPO / "skillhub/scoring/v1.json").read_text())
    assert table["version"] == "v1.3" and len(table["rules"]) >= 15
    assert all(isinstance(r, str) and r.endswith(".") for r in table["rules"])
    v12 = json.loads((REPO / "skillhub/scoring/history/v1.2.json").read_text())
    assert v12["version"] == "v1.2" and json.loads((REPO / "skillhub/scoring/history/v1.1.json").read_text())["version"] == "v1.1"
    missing = [r for r in v12["rules"] if r not in table["rules"]]
    assert not missing, missing  # every trust rule survives verbatim
    assert table["freshness"] == v12["freshness"]
    # v1.3 gates: the independent gate moved from Proven to Hardened; every v1.2 gate value is unchanged
    assert table["gates"] == {**v12["gates"], "hardened_min_independent_device_classes": 1}


# Four axes, with screen size and density jointly describing the screen axis.
GRID_FP = {"app_version": "1.0", "os_version": "14", "screen_wxh": "1080x2400", "density": 420, "locale": "en-US"}


def test_device_grid_key_and_missing_axes_cover_no_cell():
    run = {"_class": "independent", "fingerprint": GRID_FP}
    assert registry.device_cell_key(run) == ("1.0", "14", "1080x2400", "420", "en-US")
    assert registry.device_grid([run])["independent_cells"] == 1
    for axis in GRID_FP:
        for missing in (None, "", "*", "  "):
            incomplete = {**run, "fingerprint": {**GRID_FP, axis: missing}}
            assert "*" in registry.device_cell_key(incomplete)
            grid = registry.device_grid([incomplete])
            assert grid["independent_cells"] == 0
            assert grid["cells"][0]["independent"] == 1  # visible, but no coverage
        changed = {**run, "fingerprint": {**GRID_FP, axis: "different"}}
        assert registry.device_grid([run, changed])["independent_cells"] == 2


def test_device_grid_counts_independent_only_per_cell_and_keeps_failures():
    run = {"fingerprint": GRID_FP, "success": True}
    insiders = [{**run, "_class": klass} for klass in ("maintainer", "self", "ci")]
    assert registry.device_grid(insiders) == {
        "cells": [
            {
                "app_version": "1.0",
                "os_version": "14",
                "screen": "1080x2400",
                "density": "420",
                "locale": "en-US",
                "independent": 0,
                "maintainer": 2,
            }
        ],
        "independent_cells": 0,
    }
    independent = {**run, "_class": "independent", "success": False}
    grid = registry.device_grid(insiders + [independent, independent])
    assert grid["independent_cells"] == 1
    assert grid["cells"][0]["independent"] == 2
    assert grid["cells"][0]["maintainer"] == 2


def test_device_labels_are_allowlisted_and_do_not_split_coverage_cells():
    runs = [
        {"_class": "maintainer", "fingerprint": {**GRID_FP, "hardware": hardware}}
        for hardware in ["samsung/SM-A037F", "Google/sdk_gphone64_x86_64", "samsung/SM-A037F"]
    ]
    grid = registry.device_grid(runs)
    assert grid["independent_cells"] == 0
    assert len(grid["cells"]) == 1
    assert grid["cells"][0]["maintainer"] == 3
    assert grid["cells"][0]["device_labels"] == ["Android emulator", "Samsung Galaxy A03s"]


@pytest.mark.parametrize("hardware", ["unknown-model", "FAKE-DEVICE-SERIAL", "samsung/SM-A037F/FAKE-DEVICE-SERIAL"])
def test_device_labels_never_copy_arbitrary_identifiers(hardware):
    fp = {**GRID_FP, "hardware": hardware, "serial": "FAKE-DEVICE-SERIAL", "device_label": "FAKE-DEVICE-SERIAL"}
    grid = registry.device_grid([{"_class": "independent", "fingerprint": fp}])
    assert "device_labels" not in grid["cells"][0]
    assert "FAKE-DEVICE-SERIAL" not in json.dumps(grid)
    assert grid["independent_cells"] == 1


def test_device_grid_emitted_and_legacy_devices_alias_counts_cells(hub):
    hub_dir, _, _, art = hub
    for i in range(2):
        art(
            "verifications",
            f"carol-{i}.json",
            "carol",
            verifier="carol",
            fingerprint_hash=str(i) * 64,
            fingerprint=GRID_FP,
        )
    # Another locale on the same physical fingerprint is another cell, not another device.
    art(
        "verifications",
        "carol-locale.json",
        "carol",
        verifier="carol",
        fingerprint_hash="0" * 64,
        fingerprint={**GRID_FP, "locale": "de-DE"},
        ok=False,
    )
    art(
        "verifications",
        "carol-old.json",
        "carol",
        verifier="carol",
        version="0.1.0",
        fingerprint={**GRID_FP, "locale": "fr-FR"},
    )
    q = build(hub_dir)["quality"]
    grid = q["runs"]["device_grid"]
    assert grid["independent_cells"] == 2
    assert sorted(c["independent"] for c in grid["cells"]) == [1, 2]
    assert q["runs"]["independent_devices"] == q["signals"]["independent_devices"] == grid["independent_cells"]
