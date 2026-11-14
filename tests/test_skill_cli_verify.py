import importlib.util
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from gitd.skills.engine import cli, evidence, submission
from gitd.skills.engine.runner import RunResult, TraceEntry

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def environment(tmp_path, monkeypatch):
    root = tmp_path / "checkout"
    skill = root / "skillhub/ghost/tiktok"
    skill.parent.mkdir(parents=True)
    shutil.copytree(
        REPO / "skillhub/ghost/tiktok", skill, ignore=shutil.ignore_patterns("runs", "verifications")
    )  # start from a clean evidence state
    (root / ".git").touch()
    monkeypatch.chdir(root)
    monkeypatch.setenv("GHOST_SKILLS_DIR", str(tmp_path / "installed"))
    monkeypatch.delenv("GHOST_HUB_REPO", raising=False)
    monkeypatch.delenv("DEFAULT_DEVICE", raising=False)
    fingerprint = {
        "os": "android",
        "os_version": "14",
        "hardware": "ASUS/ROG",
        "app_package": "com.zhiliaoapp.musically",
        "app_version": "44.3.3",
    }
    fp = tmp_path / "fingerprint.json"
    fp.write_text(json.dumps(fingerprint))
    calls = []
    state = {"login": "verifier-user", "fail": None, "success": True}

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        if state["fail"] and args[: len(state["fail"])] == state["fail"]:
            raise subprocess.CalledProcessError(1, args, stderr="mock submission failure")
        if args[:3] == ["gh", "api", "user"]:
            return SimpleNamespace(stdout=state["login"])
        if args[:4] == ["adb", "-s", "mock", "shell"] and "ro.kernel.qemu" in args[4]:
            return SimpleNamespace(stdout="0\n0\n")  # emulator probe: hardware
        if args[:3] == ["gh", "repo", "view"]:
            return SimpleNamespace(stdout="main")
        if args[:3] == ["gh", "pr", "create"]:
            body = Path(args[args.index("--body-file") + 1]).read_text()
            state["body"] = body
            return SimpleNamespace(stdout="https://github.com/example/repo/pull/123")
        if args[:2] in [["git", "rev-parse"], ["git", "hash-object"], ["git", "write-tree"], ["git", "commit-tree"]]:
            return SimpleNamespace(stdout="a" * 40)
        if args[0] == "git":
            return SimpleNamespace(stdout="")
        pytest.fail("Unexpected external command: " + repr(args))

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **kw: pytest.fail("No real network"))
    monkeypatch.setattr(evidence, "_sign", lambda payload: {"algorithm": "mock-signature"})

    def run_action(skill, action, **kwargs):
        return RunResult(
            state["success"],
            skill.name,
            action,
            error=None if state["success"] else {"kind": "ValidatorFailedError"},
            trace=[TraceEntry(0, {}, 0, 1)],
        )

    monkeypatch.setattr(cli, "run_action", run_action)
    args = ["verify", "ghost/tiktok", "--action", "open_inbox", "--device", "mock", "--fingerprint", str(fp)]
    return SimpleNamespace(root=root, skill=skill, calls=calls, state=state, args=args, fingerprint=fingerprint)


def artifacts(env):
    return list((env.skill / "verifications").glob("*.json"))


def test_preview_default_creates_registry_compatible_artifact(environment, capsys, monkeypatch):
    env = environment
    assert cli.main(env.args) == 0
    assert [args[:3] for args, kwargs in env.calls if args[0] == "gh"] == [
        ["gh", "api", "user"]
    ]  # plus the adb emulator probe
    (artifact,) = artifacts(env)
    assert artifact.name.startswith("verifier-user-" + evidence.fingerprint_hash(env.fingerprint))
    payload = json.loads(artifact.read_text())
    assert payload["verifier"] == "verifier-user"  # Hyphenated login is not inferred from filename.
    assert payload["verifier_tier"] == "novice"
    assert payload["device_class"] == "ASUS/ROG/14"
    assert payload["finished_at"]
    assert payload["fingerprint_hash"] == evidence.fingerprint_hash(env.fingerprint)
    assert "PR preview only" in capsys.readouterr().out
    spec = importlib.util.spec_from_file_location("test_verify_registry", REPO / "tools/build_registry.py")
    registry = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(registry)
    # The signature is mocked here; registry-side verification is covered by test_evidence_verify.py.
    monkeypatch.setattr(registry, "artifact_rejection", lambda data, **kw: None)
    signals = registry.run_signals(env.skill, "ghost", datetime.now(timezone.utc).isoformat())
    assert signals["runs_independent_passed"] == 1
    # This recorded fingerprint lacks screen, density and locale: no complete device cell.
    assert signals["independent_devices"] == signals["device_grid"]["independent_cells"] == 0
    assert signals["independent_runs"] == 0  # v1.2: per-action credit; one of tiktok's 8 actions was verified
    assert signals["community_runs"] == 1
    assert signals["runs_total_90d"] == 1
    assert signals["last_verified"] is not None


@pytest.mark.parametrize("repo_source", ["default", "env", "flag"])
def test_push_only_commits_artifact_and_uses_explicit_target(environment, monkeypatch, repo_source, capsys):
    env = environment
    expected = submission.DEFAULT_VERIFY_REPO
    args = env.args + ["--push"]
    if repo_source in {"env", "flag"}:
        monkeypatch.setenv("GHOST_HUB_REPO", "environment/hub")
        expected = "environment/hub"
    if repo_source == "flag":
        args += ["--repo", "explicit/hub"]
        expected = "explicit/hub"
    assert cli.main(args) == 0
    commands = [args for args, kwargs in env.calls]
    (fetch,) = [command for command in commands if command[:2] == ["git", "fetch"]]
    (push,) = [command for command in commands if command[:2] == ["git", "push"]]
    (pr,) = [command for command in commands if command[:3] == ["gh", "pr", "create"]]
    (update_index,) = [command for command in commands if command[:2] == ["git", "update-index"]]
    (artifact,) = artifacts(env)
    relative = artifact.relative_to(env.root).as_posix()
    assert update_index[-1] == relative
    assert "--cacheinfo" in update_index
    assert fetch == ["git", "fetch", "--no-tags", f"https://github.com/{expected}.git", "refs/heads/main"]
    assert push[2] == f"https://github.com/{expected}.git"
    assert "origin" not in push
    assert push[3].startswith("refs/heads/verify/verifier-user-ghost-tiktok-")
    assert pr[pr.index("--repo") + 1] == expected
    assert pr[pr.index("--base") + 1] == "main"
    assert pr[pr.index("--head") + 1] == push[3].split(":")[0].removeprefix("refs/heads/")
    assert "\n\n" in env.state["body"]
    assert not any(
        command[1] in {"checkout", "switch", "add", "reset", "tag"} for command in commands if command[0] == "git"
    )
    isolated = [
        kwargs["env"]["GIT_INDEX_FILE"]
        for command, kwargs in env.calls
        if command[:2] in [["git", "read-tree"], ["git", "update-index"], ["git", "write-tree"]]
    ]
    assert len(set(isolated)) == 1 and not Path(isolated[0]).exists()
    assert "Verification PR:" in capsys.readouterr().out


def test_installed_skill_artifact_goes_to_checkout(environment, monkeypatch):
    env = environment
    loaded = cli.load_skill(env.skill)
    installed = env.root.parent / "installed/ghost/tiktok/2.0.0"
    installed.mkdir(parents=True)
    loaded.skill_dir = installed
    monkeypatch.setattr(cli, "load_skill", lambda ref: loaded)
    assert cli.main(env.args) == 0
    assert len(artifacts(env)) == 1
    assert not (installed / "verifications").exists()


@pytest.mark.parametrize("push", [False, True])
def test_self_verification_refused_before_artifact_or_git(environment, push, capsys):
    env = environment
    env.state["login"] = "Ghost"
    assert cli.main(env.args + (["--push"] if push else [])) == 1
    assert artifacts(env) == []
    assert all(args[:3] == ["gh", "api", "user"] for args, kwargs in env.calls)
    assert "other than the skill author" in capsys.readouterr().err


@pytest.mark.parametrize("failure", [["git", "fetch"], ["git", "push"], ["gh", "pr", "create"]])
def test_submission_failure_is_reported_and_artifact_retained(environment, failure, capsys):
    env = environment
    env.state["fail"] = failure
    assert cli.main(env.args + ["--push"]) == 1
    assert len(artifacts(env)) == 1
    assert "mock submission failure" in capsys.readouterr().err
    if failure == ["git", "fetch"]:
        assert not any(args[:3] == ["gh", "pr", "create"] for args, kwargs in env.calls)


def test_failed_run_can_submit_regression_evidence(environment):
    env = environment
    env.state["success"] = False
    assert cli.main(env.args + ["--push"]) == 1
    assert json.loads(artifacts(env)[0].read_text())["success"] is False
    assert any(args[:3] == ["gh", "pr", "create"] for args, kwargs in env.calls)


def test_invalid_repo_and_conflicting_modes_refused(environment):
    env = environment
    assert cli.main(env.args + ["--push", "--repo", "origin"]) == 1
    assert env.calls == []
    with pytest.raises(SystemExit):
        cli.main(env.args + ["--push", "--dry-run"])
    assert env.calls == []
