"""Signed evidence must bind to the target app and shipped skill code; no network."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from gitd.skills.engine import evidence
from gitd.skills.engine.manifest import skill_content_digest
from tools import build_registry
from tools.ci.verify_evidence import verify_artifact

pytestmark = pytest.mark.skipif(shutil.which("ssh-keygen") is None, reason="ssh-keygen required")
NOW = "2026-10-22T12:00:00Z"


@pytest.fixture
def signed_run(tmp_path, monkeypatch):
    monkeypatch.setenv("GHOST_CONFIG_DIR", str(tmp_path / "config"))
    hub = tmp_path / "hub"
    directory = hub / "alice" / "notes"
    directory.mkdir(parents=True)
    metadata = {
        "name": "notes",
        "author": "alice",
        "version": "1.0.0",
        "fingerprint": {"app_package": "org.example.notes", "app_version": "2.0.0"},
        "actions": [{"name": "open"}],
    }
    (directory / "skill.yaml").write_text(yaml.safe_dump(metadata))

    def write(gate, *, fingerprint=None, bound=True, **overrides):
        principal = "alice" if gate == "self" else "reviewer"
        public = evidence.signing_public_key()
        (hub / "SIGNERS").write_text(evidence.signers_line(principal, public))
        fp = fingerprint if fingerprint is not None else dict(metadata["fingerprint"])
        payload = {
            "skill": "alice/notes",
            "version": "1.0.0",
            "verifier": principal,
            "success": True,
            "device_backend": "device",
            "fingerprint": fp,
            "fingerprint_hash": evidence.fingerprint_hash(fp),
            "finished_at": NOW,
            "actions": [{"name": "open", "success": True}],
            "skill_sha256": skill_content_digest(directory),
        }
        payload.update(overrides)
        if not bound:
            payload.pop("skill_sha256")
        payload["signature"] = evidence._sign(payload)
        sub = directory / ("runs" if gate == "self" else "verifications")
        sub.mkdir(exist_ok=True)
        path = sub / f"{principal}-{payload['fingerprint_hash']}-now.json"
        path.write_text(json.dumps(payload))
        return path, public

    return directory, metadata, write


def assert_rejected(gate, directory, path, public, reason):
    if gate == "pr":
        with pytest.raises(ValueError, match=reason):
            verify_artifact(path, "reviewer", [public], "alice")
    else:
        signals = build_registry.run_signals(directory, "alice", NOW)
        assert signals["runs_total"] == 0
        assert signals["runs_rejected_reasons"] == {reason: 1}


@pytest.mark.parametrize("gate", ["self", "independent", "pr"])
@pytest.mark.parametrize("location", ["fingerprint", "top_level"])
def test_wrong_app_rejected(signed_run, gate, location):
    directory, metadata, write = signed_run
    fp = dict(metadata["fingerprint"])
    overrides = {}
    if location == "fingerprint":
        fp["app_package"] = "org.example.other"
    else:
        overrides["app_package"] = "org.example.other"
    path, public = write(gate, fingerprint=fp, **overrides)
    assert_rejected(gate, directory, path, public, "wrong-app")


@pytest.mark.parametrize("gate", ["self", "independent", "pr"])
@pytest.mark.parametrize(
    "declared,recorded", [("2.0.0", "1.9.9"), (">=2.10", "2.9"), (">2.0", "2.0.0"), (">=2.0, <4", "1.9")]
)
def test_stale_app_rejected(signed_run, gate, declared, recorded):
    directory, metadata, write = signed_run
    metadata["fingerprint"]["app_version"] = declared
    (directory / "skill.yaml").write_text(yaml.safe_dump(metadata))
    fp = {**metadata["fingerprint"], "app_version": recorded}
    path, public = write(gate, fingerprint=fp)
    assert_rejected(gate, directory, path, public, "stale-app")


@pytest.mark.parametrize("gate", ["self", "independent", "pr"])
@pytest.mark.parametrize("actual", ["4.0", "unknown"], ids=["above-range", "non-numeric"])
def test_outside_app_version_range_rejected(signed_run, gate, actual):
    directory, metadata, write = signed_run
    metadata["fingerprint"]["app_version"] = ">=2.0 <3.0"
    (directory / "skill.yaml").write_text(yaml.safe_dump(metadata))
    path, public = write(gate, fingerprint={**metadata["fingerprint"], "app_version": actual})
    assert_rejected(gate, directory, path, public, "stale-app")


@pytest.mark.parametrize("gate", ["self", "independent", "pr"])
def test_unbound_helper_rejected(signed_run, gate):
    directory, _, write = signed_run
    (directory / "helpers").mkdir()
    (directory / "helpers" / "actions.py").write_text("def identity(value):\n    return value\n")
    path, public = write(gate, bound=False)
    assert_rejected(gate, directory, path, public, "unbound-helper")


@pytest.mark.parametrize("gate", ["self", "independent", "pr"])
@pytest.mark.parametrize("variant", ["bound-helper", "legacy-yaml", "companion", "alternative", "newer"])
def test_valid_evidence_still_counts(signed_run, gate, variant):
    directory, metadata, write = signed_run
    fp = dict(metadata["fingerprint"])
    if variant == "bound-helper":
        (directory / "helpers.py").write_text("VALUE = 1\n")
    elif variant == "companion":
        metadata["fingerprint"]["apps"] = ["org.example.viewer"]
        fp.update(app_package="org.example.viewer", app_version="1.0")
    elif variant == "alternative":
        metadata["fingerprint"] = [metadata["fingerprint"], {**fp, "app_version": ">=1.0"}]
        fp["app_version"] = "1.5"
    elif variant == "newer":
        metadata["fingerprint"]["app_version"] = ">=2.0"
        fp["app_version"] = "3.0"
    (directory / "skill.yaml").write_text(yaml.safe_dump(metadata))
    path, public = write(gate, fingerprint=fp, bound=variant != "legacy-yaml")
    if gate == "pr":
        assert verify_artifact(path, "reviewer", [public], "alice") == path.as_posix()
    else:
        signals = build_registry.run_signals(directory, "alice", NOW, digest=skill_content_digest(directory))
        assert signals["runs_total"] == 1
        assert signals["runs_rejected"] == 0


@pytest.mark.parametrize("gate", ["self", "independent", "pr"])
def test_malformed_app_identity_rejected_without_crashing(signed_run, gate):
    directory, _, write = signed_run
    path, public = write(gate, app_package=["org.example.notes"])
    assert_rejected(gate, directory, path, public, "wrong-app")


def test_verifier_imports_from_trusted_ci_snapshot(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    workflow = yaml.safe_load((repo / ".github/workflows/skill-submission.yml").read_text())
    step = next(
        step
        for job in workflow["jobs"].values()
        for step in job["steps"]
        if step.get("name") == "Preserve trusted detection helpers"
    )
    snapshot = tmp_path / "trusted"
    subprocess.run(
        ["bash", "-ec", step["run"].replace("/tmp/skill-detect", str(snapshot))],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    result = subprocess.run(
        [sys.executable, str(snapshot / "tools/ci/verify_evidence.py"), "--help"],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(snapshot)},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
