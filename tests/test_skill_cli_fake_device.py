import importlib.util
import json
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from gitd.skills.engine import cli
from gitd.skills.engine.dispatch import _fast_dump
from gitd.skills.engine.fake_device import FakeDevice
from gitd.skills.engine.runner import _get_device

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests/fixtures/fake_google_maps"


@pytest.fixture
def environment(tmp_path, monkeypatch):
    skill = tmp_path / "skillhub/ghost/google_maps"
    skill.parent.mkdir(parents=True)
    # Start with skill code only; real hub recordings are not test output.
    shutil.copytree(REPO / "skillhub/ghost/google_maps", skill, ignore=shutil.ignore_patterns("runs", "verifications"))
    monkeypatch.setenv("GHOST_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("GHOST_SKILLS_DIR", str(tmp_path / "installed"))
    monkeypatch.delenv("GHOST_DEVICE", raising=False)
    monkeypatch.delenv("DEFAULT_DEVICE", raising=False)
    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    original_run = subprocess.run
    external = []

    def guarded_run(args, **kwargs):
        external.append(args)
        if args[0] == "ssh-keygen":
            return original_run(args, **kwargs)
        pytest.fail("Fake run attempted an external operation: " + repr(args))

    monkeypatch.setattr(subprocess, "run", guarded_run)
    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: pytest.fail("Network prohibited"))
    return skill, external


def registry_for(skill, monkeypatch):
    spec = importlib.util.spec_from_file_location("fake_device_registry", REPO / "tools/build_registry.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "_git", lambda *args: None)
    registry = module.build_registry(skill.parents[1], now=datetime.now(timezone.utc).isoformat())
    return registry["skills"]["ghost/google_maps"]


@pytest.mark.parametrize("command", ["run", "test"])
def test_migrated_search_runs_end_to_end_and_signed_evidence_counts(environment, monkeypatch, capsys, command):
    if not shutil.which("ssh-keygen"):
        pytest.skip("SSH signing unavailable")
    skill, external = environment
    ref = "fake:" + str(FIXTURE)
    if command == "run":
        args = ["run", str(skill), "search_place", "--record", "--device", ref, "--param", "query=Fixture Cafe"]
    else:
        monkeypatch.setenv("GHOST_DEVICE", ref)
        args = ["test", str(skill), "--live", "--record", "--action", "search_place", "--param", "query=Fixture Cafe"]
    # Execute the real runner, dispatch, generated adapter, v1 action, and validator.
    assert cli.main(args) == 0
    assert "place_card" in capsys.readouterr().out
    (artifact,) = (skill / "runs").glob("*.json")
    data = json.loads(artifact.read_text())
    assert data["success"] is True
    assert data["device_backend"] == "fake" and data["simulation"] is True
    assert data["actions"][0]["name"] == "search_place"
    assert data["actions"][0]["steps"] == [
        {"index": 0, "success": True, "duration_ms": data["actions"][0]["steps"][0]["duration_ms"]}
    ]
    assert data["fingerprint"]["app_package"] == "com.google.android.apps.maps"
    assert data["fingerprint"]["hardware"] == "Fixture/GoogleMaps"
    assert artifact.name.startswith(data["fingerprint_hash"] + "-")
    signature = data.pop("signature")
    assert signature["algorithm"] == "ssh-ed25519" and signature["value"].startswith("-----BEGIN SSH SIGNATURE-----")
    allowed = skill.parent / "allowed-signers"
    allowed.write_text("recorder " + signature["public_key"] + "\n")
    signature_file = skill.parent / "signature"
    signature_file.write_text(signature["value"])
    from gitd.skills.engine.evidence import canonical

    assert (
        subprocess.run(
            [
                "ssh-keygen",
                "-Y",
                "verify",
                "-f",
                str(allowed),
                "-I",
                "recorder",
                "-n",
                signature["namespace"],
                "-s",
                str(signature_file),
            ],
            input=canonical(data),
            capture_output=True,
        ).returncode
        == 0
    )
    # Fake-device recordings are flagged simulation=true and the registry rejects them as evidence.
    entry = registry_for(skill, monkeypatch)
    runs = entry["quality"]["runs"]
    assert (runs["total"], runs["self"], runs["rejected"]) == (
        0,
        {"passed": 0, "total": 0},
        {"total": 1, "reasons": {"simulated": 1}},
    )
    assert data["emulator"] is None and data["skill_sha256"].startswith("sha256:")  # fake device: emulator unknown
    assert entry["quality"]["tier"] == "draft"
    assert all(args[0] == "ssh-keygen" for args in external)


def test_failed_live_search_records_a_failed_run_only_with_record(environment, tmp_path, monkeypatch):
    if not shutil.which("ssh-keygen"):
        pytest.skip("SSH signing unavailable")
    skill, external = environment
    fixture = tmp_path / "failed_fixture"
    shutil.copytree(FIXTURE, fixture)
    profile = json.loads((fixture / "device.json").read_text())
    profile["transitions"] = []
    (fixture / "device.json").write_text(json.dumps(profile))
    assert (
        cli.main(
            [
                "test",
                str(skill),
                "--live",
                "--action",
                "search_place",
                "--device",
                "fake:" + str(fixture),
                "--param",
                "query=Fixture Cafe",
            ]
        )
        == 1
    )
    assert not list((skill / "runs").glob("*.json"))  # test --live writes nothing without --record
    assert (
        cli.main(
            [
                "run",
                str(skill),
                "search_place",
                "--record",
                "--device",
                "fake:" + str(fixture),
                "--param",
                "query=Fixture Cafe",
            ]
        )
        == 1
    )
    (artifact,) = (skill / "runs").glob("*.json")  # run --record keeps failures: evidence for the Wilson rating
    data = json.loads(artifact.read_text())
    assert data["success"] is False
    assert data["actions"][0]["steps"][0]["success"] is False
    assert data["actions"][0]["error_kind"] == "StepFailedError"
    assert data["simulation"] is True
    assert registry_for(skill, monkeypatch)["quality"]["runs"]["rejected"] == {"total": 1, "reasons": {"simulated": 1}}


def test_fixture_transitions_fast_dump_and_no_external_fallback(environment, monkeypatch):
    monkeypatch.setenv("GHOST_DEVICE", "fake:" + str(FIXTURE))
    device = _get_device("")
    assert isinstance(device, FakeDevice)
    assert "Search here" in _fast_dump(device)
    bounds = device.find_bounds(
        device.dump_xml(), resource_id="com.google.android.apps.maps:id/search_omnibox_text_box"
    )
    assert device.bounds_center(bounds) == (505, 95)
    device.tap(505, 95)
    device.adb("shell", "input", "text", "Fixture%sCafe")
    device.press_enter()
    assert "Directions to Fixture Cafe" in _fast_dump(device)
    assert [operation for operation, args in device.operations if operation != "dump_xml"] == [
        "tap",
        "type_text",
        "press_enter",
    ]
    with pytest.raises(RuntimeError, match="cannot replay"):
        device.adb("install", "outside.apk")


def test_dry_test_does_not_record(environment):
    skill, external = environment
    assert cli.main(["test", str(skill)]) == 0
    assert not (skill / "runs").exists()
    assert external == []


def test_fixture_validation_and_explicit_flag_precedence(environment, tmp_path, monkeypatch):
    skill, external = environment
    fixture = tmp_path / "bad_fixture"
    shutil.copytree(FIXTURE, fixture)
    profile = json.loads((fixture / "device.json").read_text())
    profile["frames"] = ["../outside.xml"]
    (fixture / "device.json").write_text(json.dumps(profile))
    with pytest.raises(ValueError, match="inside the fixture"):
        FakeDevice("fake:" + str(fixture))
    if not shutil.which("ssh-keygen"):
        pytest.skip("SSH signing unavailable")
    args = [
        "run",
        str(skill),
        "search_place",
        "--record",
        "--device",
        "fake:" + str(FIXTURE),
        "--param",
        "query=Fixture Cafe",
    ]
    # Fable S1: a session scope is strict, so an explicit --device outside GHOST_DEVICE is refused, not preferred.
    monkeypatch.setenv("GHOST_DEVICE", "fake:" + str(fixture))
    assert cli.main(args) != 0
    monkeypatch.setenv("GHOST_DEVICE", "fake:" + str(FIXTURE))
    assert cli.main(args) == 0


def test_producer_verification_matches_ci_guard_and_rejects_tampered_verifier(environment):
    from gitd.ghostcli.config import ghost_dir
    from gitd.skills.engine.evidence import write_evidence
    from gitd.skills.engine.loader import load_skill
    from gitd.skills.engine.runner import run_action
    from tools.ci.verify_evidence import verify_artifact

    assert shutil.which("ssh-keygen"), "Producer/CI contract needs SSH signing support"
    skill_path, external = environment
    config = ghost_dir()
    config.mkdir(parents=True)
    key = config / "run-signing-key"
    # Generate the trusted fixture identity locally; no GitHub key lookup occurs.
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)], check=True, capture_output=True, timeout=20
    )
    public_key = Path(str(key) + ".pub").read_text().strip()
    skill = load_skill(skill_path)
    serial = "fake:" + str(FIXTURE)
    outcome = run_action(skill, "search_place", params={"query": "Fixture Cafe"}, device_serial=serial)
    assert outcome.success
    fingerprint = FakeDevice(serial).fingerprint
    artifact = write_evidence(skill, [outcome], fingerprint, login="verifier-user", simulated=True)
    original = json.loads(artifact.read_text())
    assert original["verifier"] == "verifier-user"
    assert verify_artifact(artifact, "verifier-user", [public_key], "ghost") == artifact.as_posix()

    changed = dict(original, verifier="attacker-user")
    artifact.write_text(json.dumps(changed))
    with pytest.raises(ValueError, match="verifier field must equal"):
        verify_artifact(artifact, "verifier-user", [public_key], "ghost")

    # Align both identity fields and filename to isolate cryptographic tampering.
    changed["github_login"] = "attacker-user"
    tampered = artifact.with_name(artifact.name.replace("verifier-user-", "attacker-user-", 1))
    tampered.write_text(json.dumps(changed))
    with pytest.raises(ValueError, match="SSH signature does not verify"):
        verify_artifact(tampered, "attacker-user", [public_key], "ghost")
