"""Offline tests for Skill Hub workflow helpers. No device or network."""

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from tools.build_codeowners import build_codeowners
from tools.ci import (
    common,
    drift,
    emulator_actions,
    emulator_report,
    registry,
    report,
    review_guard,
    submission,
    trusted_vendor,
)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("Network is forbidden in CI helper tests")

    monkeypatch.setattr(common.urllib.request, "urlopen", denied)
    monkeypatch.setattr(submission, "changed_paths", lambda base, head="HEAD": [])


def test_changed_dirs_include_deletions_and_ignore_registry():
    assert common.skill_dirs(
        [
            "skillhub/alice/chat/skill.yaml",
            "skillhub/alice/chat/README.md",
            "skillhub/bob/maps/helpers.py",
            "skillhub/registry.json",
            "gitd/skills/foo/skill.yaml",
            "skillhub/../bad/file",
        ]
    ) == ["skillhub/alice/chat", "skillhub/bob/maps"]


def test_diff_uses_nul_delimiters_and_disables_rename_detection(monkeypatch):
    seen = []

    def output(command):
        seen.append(command)
        return b"skillhub/alice/chat/deleted.py\0skillhub/bob/new/skill.yaml\0"

    monkeypatch.setattr(common.subprocess, "check_output", output)
    assert len(common.changed_skills("base", "head")) == 2
    assert "--no-renames" in seen[0] and "-z" in seen[0]


def test_codeowners(tmp_path):
    for author in ("bob", "ghost", "alice"):
        (tmp_path / author).mkdir()
    (tmp_path / "androidworld").mkdir()  # reference namespace, not a GitHub login: must not become @androidworld
    lines = build_codeowners(tmp_path).splitlines()
    assert lines[1:5] == [
        "* @C-K-Loan",
        "/skillhub/ghost/ @C-K-Loan",
        "/skillhub/androidworld/ @C-K-Loan",
        "/skillhub/scoring/ @C-K-Loan",
    ]
    assert "@androidworld" not in build_codeowners(tmp_path)
    assert {
        "/.github/ @C-K-Loan",
        "/tools/ci/ @C-K-Loan",
        "/skillhub/verifier-keys.yml @C-K-Loan",
        "/skillhub/trusted-vendors.yml @C-K-Loan",
    } <= set(lines)
    assert lines[-2:] == [
        "/skillhub/alice/ @alice",
        "/skillhub/bob/ @bob",
    ]  # author lines last: they win for their folder
    (tmp_path / "bad name").mkdir()
    with pytest.raises(ValueError):
        build_codeowners(tmp_path)


def test_committed_codeowners_is_the_generator_output_at_the_path_github_reads():
    repo = Path(__file__).resolve().parents[1]
    assert (repo / ".github" / "CODEOWNERS").read_text() == build_codeowners(repo / "skillhub")
    assert not (repo / "skillhub" / "CODEOWNERS").exists()  # GitHub ignores that location
    registry_py = (repo / "tools" / "ci" / "registry.py").read_text()
    assert ".github/CODEOWNERS" in registry_py and "skillhub/CODEOWNERS" not in registry_py


@pytest.mark.parametrize(
    "new,old,expected",
    [
        ("1.0.1", "1.0.0", True),
        ("1.0.0", "1.0.0", False),
        ("1.0.0+new", "1.0.0+old", False),
        ("2.0.0", "1.9.9", True),
        ("1.0.0", "1.0.0-rc.1", True),
        ("1.0.0-beta.2", "1.0.0-beta.11", False),
        ("1.0.0-beta", "1.0.0-alpha", True),
        ("1.0.0-rc.1", "1.0.0", False),
        ("1.0.0-alpha.1", "1.0.0-alpha", True),
    ],
)
def test_version_increase(new, old, expected):
    assert submission.version_increased(new, old) is expected


@pytest.mark.parametrize("value", ["1.0", "01.0.0", "1.0.0-01", "1.0.0-a..b", None])
def test_invalid_semver(value):
    with pytest.raises(ValueError):
        submission.semver(value)


@pytest.mark.parametrize(
    "code,output,soft,optional,expected",
    [
        (2, "high finding", False, True, "fail"),
        (2, "invalid choice: analyze", False, True, "warning"),
        (2, "Unknown subcommand: analyze", False, True, "warning"),
        (1, "lint issues", True, True, "warning"),
        (1, "parse error", False, False, "fail"),
        (0, "", False, False, "pass"),
        (1, "analyzer crashed", False, True, "fail"),
    ],
)
def test_command_policy(monkeypatch, code, output, soft, optional, expected):
    monkeypatch.setattr(
        submission.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=code, stdout=output, stderr="")
    )
    assert (
        submission.run_check(["ghost", "skill", "analyze", "dir"], soft=soft, optional=optional)["status"] == expected
    )


def test_timeout_blocks_required_checks(monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("ghost", 180)

    monkeypatch.setattr(submission.subprocess, "run", timeout)
    assert submission.run_check(["ghost"])["status"] == "fail"


def make_skill(tmp_path, monkeypatch, author="alice"):
    monkeypatch.chdir(tmp_path)
    path = Path("skillhub") / author / "chat"
    path.mkdir(parents=True)
    (path / "skill.yaml").write_text("version: 1.1.0\nskill_class: soft\nfingerprint:\n  os: android\n")
    (path / "helpers.py").write_text("")
    (path / "README.md").write_text("Usage")
    (path / "SOFT.md").write_text("Narrative")
    return path


def test_checks_block_ownership_and_version_and_remain_dry(tmp_path, monkeypatch):
    path = make_skill(tmp_path, monkeypatch)
    monkeypatch.setattr(
        submission.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0, stdout="version: 1.1.0", stderr="")
    )
    commands = []

    def check(command, **kwargs):
        commands.append(command)
        return {"status": "pass", "exit_code": 0, "output": ""}

    monkeypatch.setattr(submission, "run_check", check)
    monkeypatch.setattr(submission.shutil, "which", lambda name: None)
    result = submission.check_skill(path, "base", "bob")
    assert result["checks"]["ownership"]["status"] == "fail"
    assert result["checks"]["version"]["status"] == "fail"
    assert {"has-python", "soft-skill", "size/small"} <= set(result["labels"])
    assert ["ghost", "skill", "test", str(path)] in commands
    assert all("--live" not in command for command in commands)


def test_medium_security_and_official_ownership(tmp_path, monkeypatch):
    path = make_skill(tmp_path, monkeypatch, "ghost")
    monkeypatch.setattr(
        submission.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=1, stdout="", stderr="")
    )
    monkeypatch.setattr(submission.shutil, "which", lambda name: None)
    monkeypatch.setattr(
        submission,
        "run_check",
        lambda command, **kw: {
            "status": "fail" if command[2] == "analyze" else "pass",
            "exit_code": 1 if command[2] == "analyze" else 0,
            "output": "medium" if command[2] == "analyze" else "",
        },
    )
    result = submission.check_skill(path, "base", "ghost")
    assert result["checks"]["ownership"]["status"] == "fail"
    assert result["checks"]["analyze"]["status"] == "warning"
    assert "needs-security-review" in result["labels"]
    assert submission.check_skill(path, "base", "bob", maintainer=True)["checks"]["ownership"]["status"] == "pass"


def test_deleted_skill_needs_owner(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = submission.check_skill("skillhub/alice/removed", "base", "bob")
    assert result["checks"]["ownership"]["status"] == "fail"
    assert result["checks"]["deleted"]["status"] == "pass"


def test_registry_tags_skip_existing_and_deleted(tmp_path, monkeypatch):
    path = make_skill(tmp_path, monkeypatch)
    monkeypatch.setattr(registry, "git", lambda *args: "alice/other-v1.0.0")
    assert registry.missing_tags([str(path), "skillhub/bob/deleted"]) == ["alice/chat-v1.1.0"]
    monkeypatch.setattr(registry, "git", lambda *args: "alice/chat-v1.1.0")
    assert registry.missing_tags([str(path)]) == []


@pytest.mark.parametrize(
    "version,expression,expected",
    [
        ("44.3.3", ">=44.0", True),
        ("45.0", ">=44.0 <45.0", False),
        ("2.4.0", "2.4.*", True),
        ("2.5", "2.4.x", False),
        ("3.0", "^2.4.0", False),
        ("2.4.9", "~2.4.0", True),
        ("2.5.0", "~2.4.0", False),
        ("0.2.9", "^0.2.3", True),
        ("0.3", "^0.2.3", False),
        ("2.0", "1.0 || >=2.0", True),
        ("44.0.0", "44.0", True),
        ("99", "*", True),
    ],
)
def test_app_ranges(version, expression, expected):
    assert drift.covered(version, expression) is expected


@pytest.mark.parametrize(
    "version,expression", [("Varies with device", ">=44"), ("44", "latest"), ("44", ">=44 garbage"), ("44", ">=44.*")]
)
def test_unknown_app_ranges_skip(version, expression):
    with pytest.raises(ValueError):
        drift.covered(version, expression)


def test_drift_only_latest_android_and_outside_range():
    def skill(os, expression):
        return {
            "latest": "1.0.0",
            "versions": {"1.0.0": {"fingerprint": {"os": os, "app_package": "app", "app_version": expression}}},
        }

    data = {
        "skills": {
            "alice/chat": skill("android", "<2.0"),
            "ghost/ios": skill("ios", "<2.0"),
            "bob/maps": skill("android", ">=2.0"),
        }
    }
    assert drift.drift_candidates(data, {"app": "2.1"}) == [
        {"skill": "alice/chat", "package": "app", "version": "2.1", "range": "<2.0"}
    ]
    assert drift.drift_candidates(data, {"app": "Varies with device"}) == []


def test_sticky_comment_updates_and_preserves_other_labels(monkeypatch):
    calls = []
    monkeypatch.setattr(
        report,
        "pages",
        lambda repo, endpoint, token: (
            [{"id": 7, "user": {"login": "github-actions[bot]"}, "body": report.MARKER}]
            if "comments" in endpoint
            else [{"name": "skill-submission"}]
        ),
    )

    def api(repo, endpoint, token, method="GET", data=None):
        calls.append((endpoint, method, data))
        return {"labels": [{"name": "human-review"}, {"name": "has-python"}]}

    monkeypatch.setattr(report, "api", api)
    report.publish(
        "org/repo",
        9,
        [
            {
                "skill": "skillhub/alice/chat",
                "checks": {"validate": {"status": "pass"}},
                "labels": ["skill-submission", "evil"],
            }
        ],
        "token",
    )
    assert calls[0][0:2] == ("issues/comments/7", "PATCH")
    assert calls[-1][2]["labels"] == ["human-review", "skill-submission"]


def test_render_escapes_mentions_and_code_fences():
    result = {
        "skill": "skillhub/alice/chat",
        "checks": {"lint": {"status": "warning", "output": "``` @everyone"}},
        "signals": {"bench": False},
    }
    body = report.render([result])
    assert "@everyone" not in body
    assert "| lint | warning |" in body


def test_drift_issue_reopens_existing_skill_issue(monkeypatch):
    calls = []
    monkeypatch.setattr(
        drift,
        "pages",
        lambda repo, endpoint, token: (
            [{"number": 3, "body": "<!-- ghost-skill-drift:alice/chat -->"}]
            if endpoint.startswith("issues")
            else [{"name": "skill-drift"}]
        ),
    )
    monkeypatch.setattr(drift, "api", lambda *a, **k: calls.append(a))
    drift.sync_issues(
        "org/repo", [{"skill": "alice/chat", "version": "2.0", "range": "<2.0", "package": "app"}], "token"
    )
    assert calls[0][1] == "issues/3" and calls[0][3] == "PATCH"
    assert calls[0][4]["state"] == "open"


def test_github_pagination(monkeypatch):
    monkeypatch.setattr(
        common, "api", lambda repo, endpoint, token: list(range(100)) if endpoint.endswith("&page=1") else [101]
    )
    assert len(common.pages("org/repo", "issues?state=all", "token")) == 101


def test_workflow_yaml_and_fork_credentials():
    root = Path(__file__).resolve().parents[1]
    for filename in ("skill-submission.yml", "skillhub-registry.yml", "skill-drift.yml"):
        document = yaml.safe_load((root / ".github/workflows" / filename).read_text())
        assert document["jobs"]
        assert "on" in document or True in document
    submission_yaml = yaml.safe_load((root / ".github/workflows/skill-submission.yml").read_text())
    assert submission_yaml["jobs"]["checks"]["permissions"] == {"contents": "read"}
    reporting = yaml.safe_load((root / ".github/workflows/skill-submission-report.yml").read_text())
    assert reporting["jobs"]["report"]["permissions"]["issues"] == "write"


def test_registry_publish_uses_builder_and_explicit_tag_refs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("skillhub").mkdir()
    monkeypatch.setattr(registry, "changed_skills", lambda base: ["skillhub/alice/chat"])
    monkeypatch.setattr(registry, "missing_tags", lambda paths: ["alice/chat-v1.1.0"])
    monkeypatch.setattr(
        registry.subprocess,
        "check_output",
        lambda command: b"{}" if "tools/build_registry.py" in command else b"# owners\n",
    )
    calls = []
    monkeypatch.setattr(
        registry.subprocess,
        "run",
        lambda command, **kw: calls.append(command) or SimpleNamespace(returncode=1 if "--quiet" in command else 0),
    )
    monkeypatch.setenv("GITHUB_REPOSITORY", "org/repo")
    monkeypatch.setattr("sys.argv", ["registry", "--base", "base"])
    registry.main()
    assert ["git", "push", "origin", "refs/tags/alice/chat-v1.1.0"] in calls
    assert Path("skillhub/registry.json").read_text() == "{}"
    assert any("[skip ci]" in argument for command in calls for argument in command)


def test_registry_failed_builder_does_not_truncate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("skillhub").mkdir()
    Path("skillhub/registry.json").write_text("existing")
    monkeypatch.setattr(registry, "changed_skills", lambda base: [])
    monkeypatch.setattr(registry, "missing_tags", lambda paths: [])

    def failed(command):
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(registry.subprocess, "check_output", failed)
    monkeypatch.setattr("sys.argv", ["registry", "--base", "base"])
    with pytest.raises(subprocess.CalledProcessError):
        registry.main()
    assert Path("skillhub/registry.json").read_text() == "existing"


def test_drift_dry_run_does_not_write_issues(tmp_path, monkeypatch):
    registry_path = tmp_path / "registry.json"
    versions_path = tmp_path / "versions.json"
    registry_path.write_text(
        json.dumps(
            {
                "skills": {
                    "alice/chat": {
                        "latest": "1.0.0",
                        "versions": {
                            "1.0.0": {"fingerprint": {"os": "android", "app_package": "app", "app_version": "<2.0"}}
                        },
                    }
                }
            }
        )
    )
    versions_path.write_text('{"app": "2.1"}')
    monkeypatch.setattr(
        "sys.argv", ["drift", "--registry", str(registry_path), "--versions", str(versions_path), "--dry-run"]
    )
    monkeypatch.setattr(drift, "sync_issues", lambda *a: pytest.fail("Dry run wrote issues"))
    drift.main()


def test_submission_detect_outputs_matrix(monkeypatch, capsys):
    monkeypatch.setattr(submission, "changed_skills", lambda base, head: ["skillhub/alice/chat"])
    monkeypatch.setattr(submission, "changed_paths", lambda base, head: ["skillhub/alice/chat/skill.yaml"])
    monkeypatch.setattr("sys.argv", ["submission", "detect", "--base", "base"])
    assert submission.main() == 0
    assert json.loads(capsys.readouterr().out) == {"skill": ["skillhub/alice/chat"]}


def test_report_resolves_fork_pr_and_rejects_stale_run(monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "org/repo")
    monkeypatch.setenv("GH_TOKEN", "token")
    monkeypatch.setattr("sys.argv", ["report", "--run", "7"])
    calls = []

    def api(repo, endpoint, token, *args):
        calls.append(endpoint)
        if endpoint == "actions/runs/7":
            return {"event": "pull_request", "pull_requests": [], "head_sha": "a" * 40}
        return {"head": {"sha": "b" * 40}, "state": "open"}

    monkeypatch.setattr(report, "api", api)
    monkeypatch.setattr(report, "pages", lambda *a: [{"number": 4, "head": {"sha": "a" * 40}}])
    report.main()
    assert calls == ["actions/runs/7", "pulls/4"]


def test_api_request_has_timeout_and_json_body(monkeypatch):
    requests = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            return b'{"ok": true}'

    def urlopen(request, **kwargs):
        requests.append((request, kwargs))
        return Response()

    monkeypatch.setattr(common.urllib.request, "urlopen", urlopen)
    assert common.api("org/repo", "issues", "token", "POST", {"title": "Skill"}) == {"ok": True}
    request, options = requests[0]
    assert options["timeout"] == 20
    assert request.method == "POST"
    assert json.loads(request.data) == {"title": "Skill"}


@pytest.mark.parametrize(
    "paths",
    [
        ["skillhub/alice/chat/skill.yaml", "skillhub/bob/maps/README.md"],
        ["registry/index/alice.chat.json"],
        ["skillhub/registry.json"],
        ["skillhub/registry/index/alice.chat.json"],
    ],
)
def test_submission_scope_blocks_multiple_authors_and_generated_registry(paths):
    with pytest.raises(ValueError):
        common.submission_scope(paths)


def test_submission_scope_allows_one_author_with_multiple_skills():
    assert common.submission_scope(
        ["skillhub/alice/chat/skill.yaml", "skillhub/alice/maps/README.md", ".github/workflows/skill-submission.yml"]
    ) == ["alice"]


def test_container_dry_checks_disable_network_and_writes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GHOST_CI_SANDBOX_IMAGE", "ghost-skill-ci")
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(submission.subprocess, "run", run)
    assert submission.run_check(["ghost", "skill", "test", "skillhub/alice/chat"])["status"] == "pass"
    command = commands[0]
    assert command[:3] == ["docker", "run", "--rm"]
    assert command[command.index("--network") + 1] == "none"
    assert "--read-only" in command and "--cap-drop=ALL" in command
    assert f"{tmp_path}:/workspace:ro" in command
    assert command[-4:] == ["ghost", "skill", "test", "skillhub/alice/chat"]


def test_release_archives_pin_commit_and_tree(tmp_path, monkeypatch):
    import hashlib

    path = make_skill(tmp_path, monkeypatch)
    calls = []

    def git(*args):
        calls.append(args)
        return {"rev-parse": "a" * 40, "show": "2026-10-05T00:00:00Z"}[args[0]]

    monkeypatch.setattr(registry, "git", git)
    monkeypatch.setattr(registry, "missing_tags", lambda paths: ["alice/chat-v1.1.0"])
    archives = []
    monkeypatch.setattr(registry.subprocess, "check_output", lambda command: archives.append(command) or b"tarball")
    output = tmp_path / "releases"
    records = registry.prepare_releases([str(path)], output)
    assert records[0]["commit"] == "a" * 40 and records[0]["git_tree"] == "a" * 40
    assert records[0]["sha256"] == hashlib.sha256(b"tarball").hexdigest()
    assert records[0]["attestation"] == "alice.chat-v1.1.0.tar.gz.sigstore.json"
    assert archives == [["git", "archive", "--format=tar.gz", f"{'a' * 40}:{path}"]]
    indexes = registry.write_indexes(records, tmp_path / "indexes")
    index = json.loads(Path(indexes[0]).read_text())
    assert set(index) == {"version", "tag", "commit", "git_tree", "sha256", "size", "released_at", "attestation"}
    assert index["size"] == 7


def release_fixture(tmp_path):
    import hashlib

    archive = tmp_path / "alice.chat-v1.1.0.tar.gz"
    archive.write_bytes(b"tarball")
    record = {
        "asset": archive.name,
        "attestation": archive.name + ".sigstore.json",
        "sha256": hashlib.sha256(b"tarball").hexdigest(),
        "tag": "alice/chat-v1.1.0",
        "commit": "a" * 40,
    }
    (tmp_path / "manifest.json").write_text(json.dumps([record]))
    return record


def test_signed_publish_verifies_before_tag_or_release(tmp_path, monkeypatch):
    record = release_fixture(tmp_path)
    (tmp_path / record["attestation"]).write_text("bundle")
    calls = []
    monkeypatch.setattr(registry.subprocess, "run", lambda command, **kw: calls.append(command))
    assert registry.publish_signed(tmp_path, "org/repo") == [record]
    assert calls[0][:2] == ["cosign", "verify-blob"]
    assert "--certificate-identity" in calls[0]
    assert "https://github.com/org/repo/.github/workflows/skillhub-registry.yml@refs/heads/main" in calls[0]
    assert calls[1] == ["git", "tag", "alice/chat-v1.1.0", "a" * 40]
    assert calls[2] == ["git", "push", "origin", "refs/tags/alice/chat-v1.1.0"]
    assert calls[3][:4] == ["gh", "release", "create", "alice/chat-v1.1.0"]
    assert "--verify-tag" in calls[3]


@pytest.mark.parametrize("corrupt", [False, True])
def test_missing_or_mismatched_bundle_blocks_publication(tmp_path, monkeypatch, corrupt):
    record = release_fixture(tmp_path)
    if corrupt:
        (tmp_path / record["attestation"]).write_text("bundle")
        (tmp_path / record["asset"]).write_bytes(b"changed")
    monkeypatch.setattr(
        registry.subprocess, "run", lambda *a, **k: pytest.fail("Published an unsigned or altered release")
    )
    with pytest.raises(ValueError):
        registry.publish_signed(tmp_path, "org/repo")


def test_signature_verification_failure_prevents_tags(tmp_path, monkeypatch):
    record = release_fixture(tmp_path)
    (tmp_path / record["attestation"]).write_text("bundle")
    calls = []

    def reject(command, **kwargs):
        calls.append(command)
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(registry.subprocess, "run", reject)
    with pytest.raises(subprocess.CalledProcessError):
        registry.publish_signed(tmp_path, "org/repo")
    assert len(calls) == 1 and calls[0][0] == "cosign"


def test_builder_without_commit_pin_is_rejected(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("skillhub").mkdir()
    Path("skillhub/registry.json").write_text("existing")
    monkeypatch.setattr(registry, "changed_skills", lambda base: [])
    monkeypatch.setattr(registry, "missing_tags", lambda paths: [])
    monkeypatch.setattr(
        registry.subprocess,
        "check_output",
        lambda command: json.dumps(
            {"skills": {"alice/chat": {"versions": {"1.0.0": {"tag": "alice/chat-v1.0.0"}}}}}
        ).encode(),
    )
    monkeypatch.setattr("sys.argv", ["registry", "--base", "base"])
    with pytest.raises(ValueError, match="commit SHA"):
        registry.main()
    assert Path("skillhub/registry.json").read_text() == "existing"


def test_amendment_actions_pinned_and_emulator_optional():
    import re

    root = Path(__file__).resolve().parents[1]
    for filename in (
        "skill-submission.yml",
        "skillhub-registry.yml",
        "skill-drift.yml",
        "skillhub-security.yml",
        "skillhub-stale.yml",
    ):
        document = yaml.safe_load((root / ".github/workflows" / filename).read_text())
        for job in document["jobs"].values():
            for step in job.get("steps", []):
                if "uses" in step:
                    assert re.fullmatch(r"[^@]+@[0-9a-f]{40}", step["uses"])
        assert "pull_request_target" not in (root / ".github/workflows" / filename).read_text()
    submission_yaml = yaml.safe_load((root / ".github/workflows/skill-submission.yml").read_text())
    emulator_yaml = yaml.safe_load((root / ".github/workflows/skill-emulator-run.yml").read_text())
    assert not emulator_yaml["jobs"]["emulator"].get("continue-on-error", False)
    assert submission_yaml["jobs"]["trust"]["needs"] == ["detect", "checks"]
    registry_yaml = yaml.safe_load((root / ".github/workflows/skillhub-registry.yml").read_text())
    assert registry_yaml["jobs"]["publish"]["permissions"]["id-token"] == "write"
    assert registry_yaml["jobs"]["publish"]["permissions"]["attestations"] == "write"


def test_workflow_audit_includes_changed_legacy_and_new_workflows(tmp_path, monkeypatch):
    from tools.ci import workflow_security

    monkeypatch.chdir(tmp_path)
    root = Path(".github/workflows")
    root.mkdir(parents=True)
    for name in ("skill-submission.yml", "ci.yml", "new.yml"):
        (root / name).write_text("name: test")
    selected = workflow_security.audit_paths(
        [".github/workflows/new.yml", ".github/ISSUE_TEMPLATE/skill_bug.yml", ".github/workflows/deleted.yml"]
    )
    assert selected == [".github/workflows/new.yml", ".github/workflows/skill-submission.yml"]
    assert ".github/workflows/ci.yml" in workflow_security.audit_paths([".github/workflows/ci.yml"])


def test_workflow_security_runs_both_required_scanners(monkeypatch):
    from tools.ci import workflow_security

    calls = []
    monkeypatch.setattr("sys.argv", ["workflow_security", "--base", "base"])
    monkeypatch.setattr(workflow_security, "changed_paths", lambda base: [])
    monkeypatch.setattr(workflow_security, "audit_paths", lambda paths: [".github/workflows/skill-submission.yml"])
    monkeypatch.setattr(workflow_security.subprocess, "run", lambda command, **kwargs: calls.append((command, kwargs)))
    workflow_security.main()
    assert calls == [
        (["actionlint"], {"check": True}),
        (["zizmor", "--no-progress", ".github/workflows/skill-submission.yml"], {"check": True}),
    ]


def test_codeowners_skips_generated_registry_namespace(tmp_path):
    (tmp_path / "registry").mkdir()
    (tmp_path / "registry" / "index").mkdir()
    (tmp_path / ".cache").mkdir()
    (tmp_path / "alice").mkdir()
    assert "@registry" not in build_codeowners(tmp_path)
    assert "/skillhub/alice/ @alice" in build_codeowners(tmp_path)


def test_generated_wrappers_are_committed_before_release_tree(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = Path("skillhub/alice/chat/SKILL.md")
    path.parent.mkdir(parents=True)
    path.write_text("wrapper")
    calls = []
    monkeypatch.setattr(registry.subprocess, "check_output", lambda command: calls.append(command) or b"{}")
    monkeypatch.setattr(
        registry.subprocess,
        "run",
        lambda command, **kw: calls.append(command) or SimpleNamespace(returncode=1 if "--quiet" in command else 0),
    )
    registry.commit_generated_wrappers()
    assert calls[0] == ["python3", "tools/build_registry.py", "skillhub/"]
    assert calls[1] == ["git", "add", "--", str(path)]
    assert calls[3] == ["git", "commit", "-m", "Generate Skill Hub wrappers [skip ci]", "--", str(path)]


@pytest.fixture
def registry_change_set():
    return [
        "skillhub/registry/index/ghost.tiktok.json",
        "skillhub/ghost/tiktok/skill.yaml",
        "skillhub/registry.json",
        "skillhub/registry/index/alice.chat.json",
        "skillhub/registry/index/ghost.tiktok.json",
        "skillhub/registry/index/ghost.removed.json",
        "skillhub/registry/index/notes.md",
        "skillhub/registry/index/nested/ignored.json",
        "registry/index/outside.json",
    ]


def test_registry_purge_exact_urls_for_fixture(registry_change_set):
    from tools.registry_purge_urls import purge_urls

    assert purge_urls("ghost-in-the-droid/android-agent", registry_change_set) == [
        "https://purge.jsdelivr.net/gh/ghost-in-the-droid/android-agent@main/skillhub/registry.json",
        "https://purge.jsdelivr.net/gh/ghost-in-the-droid/android-agent@main/skillhub/registry/index/alice.chat.json",
        "https://purge.jsdelivr.net/gh/ghost-in-the-droid/android-agent@main/skillhub/registry/index/ghost.removed.json",
        "https://purge.jsdelivr.net/gh/ghost-in-the-droid/android-agent@main/skillhub/registry/index/ghost.tiktok.json",
    ]
    assert purge_urls("org/repo", []) == ["https://purge.jsdelivr.net/gh/org/repo@main/skillhub/registry.json"]


def test_registry_purge_cli_diffs_through_generated_commit(monkeypatch, capsys, registry_change_set):
    from tools import registry_purge_urls

    commands = []

    def output(command):
        commands.append(command)
        return "\0".join(registry_change_set).encode()

    monkeypatch.setattr(registry_purge_urls.subprocess, "check_output", output)
    monkeypatch.setattr("sys.argv", ["registry_purge_urls", "--base", "before", "--repo", "org/repo"])
    registry_purge_urls.main()
    assert commands == [["git", "diff", "--name-only", "--no-renames", "-z", "before", "HEAD", "--"]]
    assert capsys.readouterr().out.splitlines() == registry_purge_urls.purge_urls("org/repo", registry_change_set)


def test_registry_purge_initial_push_uses_all_indexes(monkeypatch, capsys):
    from tools import registry_purge_urls

    commands = []
    monkeypatch.setenv("GITHUB_REPOSITORY", "org/repo")
    monkeypatch.setattr("sys.argv", ["registry_purge_urls", "--base", "0" * 40])
    monkeypatch.setattr(
        registry_purge_urls.subprocess,
        "check_output",
        lambda command: commands.append(command) or b"skillhub/registry/index/alice.chat.json\0",
    )
    registry_purge_urls.main()
    assert commands == [["git", "ls-tree", "-r", "--name-only", "-z", "HEAD"]]
    assert capsys.readouterr().out.splitlines() == [
        "https://purge.jsdelivr.net/gh/org/repo@main/skillhub/registry.json",
        "https://purge.jsdelivr.net/gh/org/repo@main/skillhub/registry/index/alice.chat.json",
    ]


def test_independent_evidence_only_pr_skips_owner_and_version_bump(tmp_path, monkeypatch):
    path = make_skill(tmp_path, monkeypatch)
    evidence = path / "verifications" / "bob.json"
    evidence.parent.mkdir()
    evidence.write_text("{}")
    monkeypatch.setattr(submission, "changed_paths", lambda base: [str(evidence)])
    monkeypatch.setattr(
        submission.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0, stdout="version: 1.1.0", stderr="")
    )
    monkeypatch.setattr(submission, "run_check", lambda *a, **k: {"status": "pass", "exit_code": 0, "output": ""})
    monkeypatch.setattr(submission.shutil, "which", lambda name: None)
    result = submission.check_skill(path, "base", "bob")
    assert result["checks"]["ownership"]["status"] == "pass"
    assert result["checks"]["version"]["status"] == "pass"
    # Signature authentication is a required predecessor in the trusted detect job.
    workflow = yaml.safe_load(
        (Path(__file__).resolve().parents[1] / ".github/workflows/skill-submission.yml").read_text()
    )
    auth = next(
        step
        for step in workflow["jobs"]["detect"]["steps"]
        if step.get("name") == "Authenticate independent verification artifacts"
    )
    # Every PR except a same-repo release/integration PR (tests/test_ci_release_pr_exemption.py).
    assert auth["if"] == "github.event_name == 'pull_request' && steps.changed.outputs.release != 'true'"
    assert "/tmp/skill-detect/tools/ci/verify_evidence.py" in auth["run"]
    assert workflow["jobs"]["checks"]["needs"] == "detect"
    monkeypatch.setattr(submission, "changed_paths", lambda base: [str(evidence), str(path / "helpers.py")])
    assert submission.check_skill(path, "base", "bob")["checks"]["ownership"]["status"] == "fail"
    evidence.unlink()
    monkeypatch.setattr(submission, "changed_paths", lambda base: [str(evidence)])
    assert submission.check_skill(path, "base", "bob")["checks"]["ownership"]["status"] == "fail"


def test_skill_dirs_skip_reserved_and_underscore_dirs():
    import pathlib
    import sys

    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools" / "ci"))
    import common

    paths = [
        "skillhub/alice/uber/skill.yaml",
        "skillhub/_guides/skill-creation-guide/SKILL.md",
        "skillhub/registry/index/alice.uber.json",
        "skillhub/scoring/v1.json",
        "skillhub/ghost/tiktok/demos/upload_video.webm",
    ]
    assert common.skill_dirs(paths) == ["skillhub/alice/uber", "skillhub/ghost/tiktok"]


# Phase 2 emulator helpers are device-free in this suite.


def test_emulator_matrix_changed_paths(tmp_path):
    for path in ("skillhub/alice/chat", "skillhub/alice/maps"):
        (tmp_path / path).mkdir(parents=True)
        (tmp_path / path / "skill.yaml").touch()
    assert emulator_actions.matrix(
        [
            "skillhub/alice/chat/skill.yaml",
            "skillhub/alice/chat/x.py",
            "skillhub/alice/maps/README.md",
            "skillhub/alice/gone/skill.yaml",
            "skillhub/registry.json",
        ],
        tmp_path,
    ) == {"skill": ["skillhub/alice/chat", "skillhub/alice/maps"]}


@pytest.mark.parametrize(
    "action, expected",
    [
        ({"demo_params": {"x": 1}, "test_case": {"params": {"x": 2}}}, {"x": 1}),
        ({"demo_params": {}, "test_case": {"params": {"x": 2}}}, {}),
        ({"test_case": {"params": {"x": False}}}, {"x": False}),
        ({"test_case": {"expected_success": True}}, {}),
        ({}, {}),
    ],
)
def test_emulator_params_precedence(action, expected):
    assert emulator_actions.params(action) == expected


def test_emulator_invalid_params():
    with pytest.raises(ValueError, match="mapping"):
        emulator_actions.params({"demo_params": ["unsafe"]})


def test_emulator_fingerprint_skips():
    actual = {"os": "android", "os_version": "14", "app_version": "2.3", "hardware": "Google/Pixel 6"}
    assert not emulator_actions.mismatch({"os": "android", "os_version": ">=14", "hardware": "Google/*"}, actual)
    assert "os:" in emulator_actions.mismatch({"os": "ios"}, actual)
    assert "app_version:" in emulator_actions.mismatch({"app_version": ">=3"}, actual)
    assert "unavailable" in emulator_actions.mismatch({"theme": "dark"}, actual)


def test_emulator_comment_rows_and_escape():
    body = emulator_report.render(
        [
            {
                "skill": "skillhub/alice/chat",
                "_artifact_id": 7,
                "actions": [
                    {"name": "open", "status": "pass", "steps": 4, "seconds": 2.5, "fingerprint": {"os": "android"}},
                    {"name": "@everyone|<script>", "status": "skip", "reason": "missing app"},
                    {"name": "failed", "status": "fail", "seconds": 180},
                ],
            }
        ],
        "owner/repo",
        123,
    )
    assert emulator_report.MARKER in body and "| 🟢 pass | 4 | 2.5 s |" in body
    assert "/actions/runs/123/artifacts/7" in body and "android" in body
    assert "@everyone" not in body and "<script>" not in body
    assert "| 🟡 skip |" in body and "| 🔴 fail |" in body


def test_emulator_sticky_updates_in_place(monkeypatch):
    calls = []
    monkeypatch.setattr(
        emulator_report,
        "pages",
        lambda *a: [{"id": 8, "user": {"login": "github-actions[bot]"}, "body": emulator_report.MARKER}],
    )

    def api_mock(repo, endpoint, token, method="GET", data=None):
        calls.append((endpoint, method, data))
        return {"artifacts": []}

    monkeypatch.setattr(emulator_report, "api", api_mock)
    emulator_report.publish_run("owner/repo", 123, 9, "token")
    assert calls[-1][0:2] == ("issues/comments/8", "PATCH")
    assert "No run result" in calls[-1][2]["body"]


def test_emulator_workflow_dependencies_and_limits():
    workflow = yaml.safe_load(Path(".github/workflows/skill-submission.yml").read_text())
    assert workflow["jobs"]["trust"]["needs"] == ["detect", "checks"]
    assert "emulator" not in workflow["jobs"]
    reusable = yaml.safe_load(Path(".github/workflows/skill-emulator-run.yml").read_text())
    job = reusable["jobs"]["emulator"]
    assert job["strategy"]["max-parallel"] == 2 and not job.get("continue-on-error", False)
    assert job["timeout-minutes"] == 15
    # Hosted default stays ubuntu-24.04 (kvm udev rule); vars.CI_RUNS_ON reroutes the mirror.
    assert job["runs-on"] == "${{ vars.CI_RUNS_ON || 'ubuntu-24.04' }}"
    assert reusable["permissions"] == {"contents": "read"}
    assert not Path("tools/ci/emulator_run.py").exists()


@pytest.mark.parametrize(
    "action_exit, emit_record, emit_video, expected",
    [(0, True, True, 0), (1, True, True, 1), (0, False, True, 1), (0, True, False, 1)],
)
def test_emulator_execution_records_video_and_evidence(
    tmp_path, monkeypatch, action_exit, emit_record, emit_video, expected
):
    from gitd.skills.engine import evidence, loader

    monkeypatch.chdir(tmp_path)
    path = Path("skillhub/alice/chat")
    path.mkdir(parents=True)
    (path / "skill.yaml").write_text(
        yaml.safe_dump({"fingerprint": {"os": "android"}, "actions": {"open": {"demo_params": {"message": "hello"}}}})
    )
    monkeypatch.setattr(loader, "load_skill", lambda p: SimpleNamespace())
    monkeypatch.setattr(
        evidence,
        "collect_fingerprint",
        lambda *a: {
            "os": "android",
            "os_version": "14",
            "hardware": "Google/Pixel 6",
            "app_package": "com.example.chat",
            "app_version": "1",
        },
    )
    monkeypatch.setattr(emulator_actions, "boot", lambda: None)
    adb_calls = []

    def adb_mock(*args, **kwargs):
        adb_calls.append(args)
        if args[0] == "pull" and emit_video:
            Path(args[-1]).write_bytes(b"fixture mp4")
        return "Physical size: 1080x2400" if args[-1] == "size" else "en-US"

    monkeypatch.setattr(emulator_actions, "adb", adb_mock)
    commands = []

    def run_mock(command, **kwargs):
        commands.append((command, kwargs))
        if "run" in command and emit_record:
            (path / "runs").mkdir()
            (path / "runs/new.json").write_text(
                json.dumps({"signature": "fixture", "actions": [{"name": "open", "steps": [{}, {}]}]})
            )
        return SimpleNamespace(returncode=action_exit)

    monkeypatch.setattr(emulator_actions.subprocess, "run", run_mock)
    popen_calls = []

    class Recorder:
        def __init__(self, command, **kwargs):
            popen_calls.append(command)

        def wait(self, timeout):
            return 0

    monkeypatch.setattr(emulator_actions.subprocess, "Popen", Recorder)
    assert emulator_actions.execute(str(path), tmp_path / "output") == expected
    row = json.loads((tmp_path / "output/result.json").read_text())["actions"][0]
    assert row["status"] == ("pass" if expected == 0 else "fail")
    assert row["steps"] == (2 if emit_record else 0)
    emulator_report.validate_result(json.loads((tmp_path / "output/result.json").read_text()))
    assert "--live" in commands[0][0] and "--action" in commands[0][0]
    assert "--record" in commands[1][0] and "message=hello" in commands[1][0]
    assert all(c[1]["env"]["PYTHONPATH"] == "." and c[1]["timeout"] <= 180 for c in commands)
    assert "--time-limit" in popen_calls[0] and "170" in popen_calls[0]
    assert any(c[0] == "pull" for c in adb_calls)
    assert (tmp_path / "output/runs/new.json").exists() is emit_record


def test_emulator_boot_failure_leaves_report(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(emulator_actions, "boot", lambda: (_ for _ in ()).throw(RuntimeError("never booted")))
    with pytest.raises(RuntimeError, match="never booted"):
        emulator_actions.execute("skillhub/alice/chat", tmp_path / "output")
    assert json.loads((tmp_path / "output/result.json").read_text()) == {"skill": "skillhub/alice/chat", "actions": []}


def test_emulator_report_reads_only_bounded_json_and_links_media(monkeypatch):
    import io
    import zipfile

    payload = valid_emulator_result()
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        archive.writestr("result.json", json.dumps(payload))
    artifacts = [
        {
            "name": "skill-emulator-result-0",
            "id": 1,
            "expired": False,
            "size_in_bytes": len(data.getvalue()),
            "archive_download_url": "https://example.invalid/archive",
        },
        {"name": "skill-emulator-media-0", "id": 2, "expired": False, "size_in_bytes": 999999999},
    ]
    calls = []

    def api_mock(repo, endpoint, token, method="GET", data=None):
        calls.append((endpoint, method, data))
        return {"artifacts": artifacts}

    monkeypatch.setattr(emulator_report, "api", api_mock)
    monkeypatch.setattr(emulator_report, "pages", lambda *a: [])
    monkeypatch.setattr(emulator_report.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(data.getvalue()))
    emulator_report.publish_run("owner/repo", 123, 9, "token")
    assert calls[-1][0:2] == ("issues/9/comments", "POST")
    assert "/artifacts/2" in calls[-1][2]["body"]
    assert "| 🟢 pass | 3 |" in calls[-1][2]["body"]


def test_emulator_report_rejects_oversized_archive(monkeypatch):
    monkeypatch.setattr(
        emulator_report,
        "api",
        lambda *a: {"artifacts": [{"name": "skill-emulator-result-0", "expired": False, "size_in_bytes": 1000001}]},
    )
    with pytest.raises(ValueError, match="too large"):
        emulator_report.publish_run("owner/repo", 123, 9, "token")


# Vendor trust checks never access HTTP or GitHub in tests.


def valid_emulator_result():
    return {
        "skill": "skillhub/alice/chat",
        "actions": [
            {
                "name": "open",
                "status": "pass",
                "steps": 3,
                "seconds": 2.5,
                "reason": "",
                "fingerprint": {
                    "os": "android",
                    "os_version": "14",
                    "hardware": "Google/Pixel 6",
                    "app_package": "com.example.chat",
                    "app_version": "1.0",
                },
            }
        ],
    }


def test_vendor_fdroid_http_200(monkeypatch):
    from contextlib import nullcontext

    seen = []

    def urlopen(url, timeout):
        seen.append((url, timeout))
        return nullcontext(SimpleNamespace(status=200))

    monkeypatch.setattr(trusted_vendor.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(trusted_vendor, "gh", lambda *a: pytest.fail("GitHub should not run"))
    assert trusted_vendor.check_vendor("org.fdroid.app") == {"trusted": True, "signal": "fdroid"}
    assert seen == [("https://f-droid.org/en/packages/org.fdroid.app/", 10)]


@pytest.mark.parametrize(
    "package, trusted", [("com.whatsapp", True), ("com.whatsapp.business", True), ("com.whatsappevil", False)]
)
def test_vendor_prefix_boundaries(monkeypatch, package, trusted):
    monkeypatch.setattr(
        trusted_vendor.urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(OSError("offline"))
    )
    assert trusted_vendor.check_vendor(package, [{"prefix": "com.whatsapp"}])["trusted"] is trusted


@pytest.mark.parametrize(
    "stars, releases, expected",
    [(1000, [{"id": 1}], True), (999, [{"id": 1}], False), (1000, [], False), (True, [{"id": 1}], False)],
)
def test_vendor_github_signals_with_mocked_gh(monkeypatch, stars, releases, expected):
    monkeypatch.setattr(
        trusted_vendor.urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(OSError("not listed"))
    )
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        value = releases if "/releases?" in command[-1] else {"stargazers_count": stars}
        return SimpleNamespace(stdout=json.dumps(value))

    monkeypatch.setattr(trusted_vendor.subprocess, "run", run)
    assert (
        trusted_vendor.check_vendor("com.example.app", [{"prefix": "com.example", "vendor_repo": "vendor/app"}])[
            "trusted"
        ]
        is expected
    )
    assert calls[0][0] == ["gh", "api", "repos/vendor/app"]
    assert calls[0][1]["timeout"] == 20 and calls[0][1]["check"] is True
    if type(stars) is int and stars >= 1000:
        assert calls[1][0][-1] == "repos/vendor/app/releases?per_page=1"


def test_vendor_fail_closed_on_http_and_gh_errors(monkeypatch):
    monkeypatch.setattr(
        trusted_vendor.urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(OSError("offline"))
    )
    monkeypatch.setattr(
        trusted_vendor.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(subprocess.TimeoutExpired("gh", 20))
    )
    assert trusted_vendor.check_vendor("com.example.app", [{"prefix": "com.example", "vendor_repo": "vendor/app"}]) == {
        "trusted": False,
        "signal": "none",
    }
    assert trusted_vendor.check_vendor("com.example.app", [])["trusted"] is False
    assert trusted_vendor.check_vendor("../../evil")["trusted"] is False


def test_vendor_policy_and_manual_approval(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    policy = tmp_path / "trusted-vendors.yml"
    policy.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "prefixes": [{"prefix": "com.whatsapp", "vendor": "Meta", "category": "messaging"}],
                "apk_sources": {},
            }
        )
    )
    path = Path("skillhub/alice/chat")
    path.mkdir(parents=True)
    (path / "skill.yaml").write_text(yaml.safe_dump({"fingerprint": {"app_package": "com.unknown.app"}}))
    monkeypatch.setattr(trusted_vendor, "check_vendor", lambda *a: {"trusted": False, "signal": "none"})
    assert trusted_vendor.load_policy(policy)[0]["prefix"] == "com.whatsapp"
    assert not trusted_vendor.check_skills([str(path)], policy, "a" * 40)["allowed"]
    result = trusted_vendor.check_skills([str(path)], policy, "a" * 40, "sha-label")
    assert result["allowed"] and result["approval_source"] == "sha-label" and not result["skills"][0]["trusted"]
    assert trusted_vendor.load_policy(tmp_path / "missing.yml") == []


def test_vendor_failure_adds_pending_label_only(monkeypatch):
    verdict = {"allowed": False, "approval_source": "none"}
    monkeypatch.setattr(report, "pages", lambda *a: [{"name": "pending-security-review"}])
    calls = []
    monkeypatch.setattr(report, "api", lambda *a: calls.append(a))
    report.apply_vendor_label("owner/repo", 9, verdict, "token")
    assert calls[-1][1:] == ("issues/9/labels", "token", "POST", {"labels": ["pending-security-review"]})
    calls.clear()
    report.apply_vendor_label("owner/repo", 9, {"allowed": True, "approval_source": "sha-label"}, "token")
    assert not calls


@pytest.mark.parametrize(
    "mutation",
    [
        lambda r: r.update(extra="unknown"),
        lambda r: r["actions"][0].update(status="unknown"),
        lambda r: r["actions"][0].update(reason="<script>bad</script>"),
        lambda r: r["actions"][0].update(reason="x" * 501),
        lambda r: r["actions"][0].update(seconds=float("nan")),
        lambda r: r["actions"][0].update(seconds=-1),
        lambda r: r["actions"][0].update(steps=True),
        lambda r: r["actions"][0].update(fingerprint={}),
        lambda r: r["actions"][0]["fingerprint"].update(html="<b>"),
        lambda r: r.update(actions=[r["actions"][0]] * 101),
    ],
)
def test_strict_emulator_schema_rejects_untrusted_shapes(mutation):
    result = valid_emulator_result()
    mutation(result)
    with pytest.raises(ValueError):
        emulator_report.validate_result(result)


def test_strict_emulator_schema_valid_and_failed_video_link():
    result = emulator_report.validate_result(valid_emulator_result())
    result["actions"][0]["status"] = "fail"
    result["_artifact_id"] = 42
    body = emulator_report.render([result], "owner/repo", 123, "failure")
    assert "🔴" in body and "| 🔴 fail |" in body and "/artifacts/42" in body


def test_reporter_rejects_extra_archive_entries(monkeypatch):
    import io
    import zipfile

    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        archive.writestr("result.json", json.dumps(valid_emulator_result()))
        archive.writestr("evil.py", "raise RuntimeError()")
    monkeypatch.setattr(emulator_report.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(data.getvalue()))
    with pytest.raises(ValueError, match="only bounded result.json"):
        emulator_report.read_summary("owner/repo", {"id": 1, "size_in_bytes": len(data.getvalue())}, "token")


def test_pr_workflow_has_no_secrets_or_write_permissions():
    path = Path(".github/workflows/skill-emulator-run.yml")
    workflow = yaml.safe_load(path.read_text())
    triggers = workflow.get("on", workflow.get(True))
    assert set(triggers) == {"pull_request"}
    assert triggers["pull_request"]["paths"] == ["skillhub/**"]
    assert workflow["permissions"] == {"contents": "read"}
    assert "secrets." not in path.read_text() and "secrets: inherit" not in path.read_text()
    assert workflow["jobs"]["submission"]["uses"] == "./.github/workflows/skill-submission.yml"
    assert workflow["jobs"]["plan"]["needs"] == "submission"
    assert workflow["jobs"]["proof"]["name"] == "skill-emulator-proof"
    reporter = yaml.safe_load(Path(".github/workflows/skill-emulator-report.yml").read_text())
    trigger = reporter.get("on", reporter.get(True))
    assert trigger["workflow_run"]["workflows"] == ["Optional skill emulator runs"]
    permissions = reporter["jobs"]["report"]["permissions"]
    assert permissions["pull-requests"] == "write" and "issues" not in permissions
    checkout = reporter["jobs"]["report"]["steps"][0]
    assert checkout["with"]["ref"] == "${{ github.event.repository.default_branch }}"


def test_emulator_report_rejects_duplicate_json_keys(monkeypatch):
    import io
    import zipfile

    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        archive.writestr("result.json", '{"skill":"skillhub/alice/chat","skill":"skillhub/bob/chat","actions":[]}')
    monkeypatch.setattr(emulator_report.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(data.getvalue()))
    with pytest.raises(ValueError, match="Duplicate JSON key"):
        emulator_report.read_summary("owner/repo", {"id": 1, "size_in_bytes": len(data.getvalue())}, "token")


def test_emulator_report_rejects_expanded_json_size(monkeypatch):
    import io
    import zipfile

    data = io.BytesIO()
    with zipfile.ZipFile(data, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("result.json", " " * 200001)
    monkeypatch.setattr(emulator_report.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(data.getvalue()))
    with pytest.raises(ValueError, match="bounded result.json"):
        emulator_report.read_summary("owner/repo", {"id": 1, "size_in_bytes": len(data.getvalue())}, "token")


@pytest.mark.parametrize("state, head", [("closed", "current"), ("open", "old")])
def test_emulator_report_never_comments_on_stale_or_closed_pr(monkeypatch, state, head):
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GH_TOKEN", "token")
    monkeypatch.setattr("sys.argv", ["emulator_report", "--run", "123"])

    def api_mock(repo, endpoint, token):
        if endpoint.startswith("actions/"):
            return {
                "event": "pull_request",
                "name": "Optional skill emulator runs",
                "head_sha": "current",
                "pull_requests": [],
                "conclusion": "success",
            }
        return {"state": state, "head": {"sha": head}}

    monkeypatch.setattr(emulator_report, "api", api_mock)
    monkeypatch.setattr(emulator_report, "pages", lambda *a: [{"number": 9, "head": {"sha": "current"}}])
    monkeypatch.setattr(emulator_report, "publish_run", lambda *a: pytest.fail("Stale PR was reported"))
    emulator_report.main()


def test_vendor_fdroid_non_200_does_not_grant_trust(monkeypatch):
    from contextlib import nullcontext

    monkeypatch.setattr(
        trusted_vendor.urllib.request, "urlopen", lambda *a, **k: nullcontext(SimpleNamespace(status=201))
    )
    assert not trusted_vendor.check_vendor("com.example.app")["trusted"]


def test_vendor_cli_outputs_false_without_failing_static_checks(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        "sys.argv",
        [
            "trusted_vendor",
            "--matrix",
            '{"skill":["skillhub/alice/chat"]}',
            "--policy",
            "policy.yml",
            "--output",
            str(tmp_path / "result.json"),
            "--head",
            "a" * 40,
        ],
    )
    monkeypatch.setattr(trusted_vendor, "check_skills", lambda *a: {"allowed": False, "skills": []})
    assert trusted_vendor.main() == 0
    assert capsys.readouterr().out.strip() == "false"
    assert json.loads((tmp_path / "result.json").read_text())["allowed"] is False


def test_passing_fingerprint_cannot_contain_wildcards():
    result = valid_emulator_result()
    result["actions"][0]["fingerprint"]["app_version"] = "*"
    with pytest.raises(ValueError, match="concrete fingerprint"):
        emulator_report.validate_result(result)


HEAD = "a" * 40


@pytest.mark.parametrize("path", [".github/workflows/run.yml", "tools/ci/forged.py", "skillhub/trusted-vendors.yml"])
def test_ci_modification_guard_protected_paths(path):
    run = {"name": "Optional skill emulator runs", "path": ".github/workflows/skill-emulator-run.yml"}
    assert review_guard.modified_ci([{"filename": path}], run)
    assert review_guard.modified_ci([{"filename": "removed.txt", "previous_filename": path}], run)
    assert not review_guard.modified_ci([{"filename": "skillhub/alice/chat/skill.yaml"}], run)
    assert review_guard.modified_ci([], {**run, "path": ".github/workflows/forged.yml"})


@pytest.mark.parametrize("kind", ["proof", "submission"])
@pytest.mark.parametrize("branch", ["changed-ci", "wrong-workflow", "runtime", "docs", "registry"])
def test_both_reporters_never_publish_green_for_forged_ci(monkeypatch, kind, branch):
    module = emulator_report if kind == "proof" else report
    name = "Optional skill emulator runs" if kind == "proof" else "Skill submission"
    run = {
        "event": "pull_request",
        "name": name,
        "path": review_guard.EXPECTED[name],
        "head_sha": HEAD,
        "pull_requests": [{"number": 9}],
        "conclusion": "success",
    }
    files = [{"filename": "skillhub/alice/chat/skill.yaml"}]
    extra = {
        "changed-ci": "tools/ci/forged.py",
        "runtime": "gitd/skills/engine/cli.py",
        "docs": "docs/guide.md",
        "registry": "skillhub/registry.json",
    }.get(branch)
    if extra:
        files.append({"filename": extra})
    if branch == "wrong-workflow":
        run["path"] = ".github/workflows/forged.yml"
    pr = {"number": 9, "state": "open", "head": {"sha": HEAD}, "labels": []}
    calls = []

    def api_mock(repo, endpoint, token, method="GET", data=None):
        calls.append((endpoint, method, data))
        if endpoint == "actions/runs/123":
            return run
        if endpoint == "pulls/9":
            return pr
        return {}

    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GH_TOKEN", "token")
    monkeypatch.setattr("sys.argv", ["report", "--run", "123"])
    monkeypatch.setattr(module, "api", api_mock)
    monkeypatch.setattr(module, "pages", lambda *a: [])
    inspected = []
    monkeypatch.setattr(review_guard, "changed_files", lambda *a: inspected.append(a) or files)
    monkeypatch.setattr(emulator_report, "artifact_list", lambda *a: pytest.fail("Forged artifact was downloaded"))
    recomputed = []
    monkeypatch.setattr(
        trusted_vendor,
        "origin_verdict",
        lambda *a: recomputed.append(a) or {"allowed": True, "skills": [], "approval_source": "none"},
    )
    module.main()
    bodies = [data["body"] for _, method, data in calls if method in ("POST", "PATCH") and data and "body" in data]
    assert len(bodies) == 1 and review_guard.WARNING in bodies[0]
    assert "🟢" not in bodies[0] and "gate: allowed" not in bodies[0]
    assert len(inspected) == 1
    if kind == "submission":
        assert len(recomputed) == 1  # Origin decision is still recomputed, never read from the run.


def test_guard_fetches_all_pr_files(monkeypatch):
    seen = []
    monkeypatch.setattr(
        review_guard,
        "pages",
        lambda repo, endpoint, token: seen.append(endpoint) or [{"filename": "skillhub/alice/chat/skill.yaml"}],
    )
    review_guard.changed_files("owner/repo", 9, {"changed_files": 1}, "token")
    assert seen == ["pulls/9/files"]
    with pytest.raises(ValueError, match="incomplete"):
        review_guard.changed_files("owner/repo", 9, {"changed_files": 2}, "token")


@pytest.mark.parametrize(
    "paths, manifest",
    [
        (["skillhub/alice/chat/helpers.py"], {}),
        (["skillhub/alice/chat/validators.py"], {}),
        ([], {"actions": {"open": {"steps": [{"python_action": "helpers:run"}]}}}),
        ([], {"end_state_validator": {"custom_python": {"function": "validators:ok"}}}),
    ],
)
def test_vendor_trust_does_not_authorize_submitter_python(monkeypatch, paths, manifest):
    monkeypatch.setattr(trusted_vendor, "check_vendor", lambda *a: {"trusted": True, "signal": "prefix"})
    raw = {"fingerprint": {"app_package": "com.whatsapp"}, **manifest}
    result = trusted_vendor.verdict({"skillhub/alice/chat": raw}, paths, [], HEAD)
    assert not result["allowed"]
    assert result["skills"][0]["has_submitter_python"] and result["skills"][0]["branch"] == "blocked"
    approved = trusted_vendor.verdict({"skillhub/alice/chat": raw}, paths, [], HEAD, "sha-label")
    assert approved["allowed"] and approved["skills"][0]["branch"] == "sha-approval"


def test_base_python_exception_and_declarative_vendor_branch(monkeypatch):
    raw = {
        "fingerprint": {"app_package": "com.whatsapp"},
        "steps": [{"python_action": "skillhub/_base/helpers.py:run"}],
    }
    monkeypatch.setattr(trusted_vendor, "check_vendor", lambda *a: {"trusted": True, "signal": "prefix"})
    result = trusted_vendor.verdict({"skillhub/alice/chat": raw}, ["skillhub/_base/helpers.py"], [], HEAD)
    assert result["allowed"] and result["skills"][0]["branch"] == "vendor-no-python"
    raw["steps"][0]["python_action"] = "skillhub/_base/../evil.py:run"
    assert trusted_vendor.has_submitter_python(raw, [], "skillhub/alice/chat")


@pytest.mark.parametrize(
    "label, role, expected",
    [
        ("approved:" + HEAD, "admin", "sha-label"),
        ("approved:" + HEAD, "maintain", "sha-label"),
        ("approved:" + HEAD, "write", "none"),
        ("approved:" + HEAD[:7], "admin", "none"),
        ("approved:" + "b" * 40, "admin", "none"),
        ("security-approved:aaaaaaa", "admin", "none"),
    ],
)
def test_commit_bound_approval_labels(label, role, expected):
    events = [{"event": "labeled", "label": {"name": label}, "actor": {"login": "reviewer"}}]
    assert review_guard.approval(HEAD, [label], permission=lambda login: role, events=events) == expected
    assert review_guard.approval(HEAD, [label]) == "none"


@pytest.mark.parametrize(
    "role, sha, expected",
    [
        ("maintain", HEAD, "maintainer-comment"),
        ("admin", HEAD, "maintainer-comment"),
        ("write", HEAD, "none"),
        ("maintain", "b" * 40, "none"),
    ],
)
def test_maintainer_comment_approval_is_commit_bound(role, sha, expected):
    comments = [{"body": "security-approved " + sha, "user": {"login": "reviewer"}}]
    assert review_guard.approval(HEAD, [], comments, lambda login: role) == expected


def test_managed_label_step_removes_every_stale_approval(monkeypatch):
    calls = []
    monkeypatch.setattr(review_guard, "api", lambda *a: calls.append(a))
    pr = {
        "head": {"sha": HEAD},
        "labels": [
            {"name": name}
            for name in (
                "security-approved",
                "security-approved:bbbbbbb",
                "approved:" + HEAD,
                "approved:" + "b" * 40,
                "ordinary",
            )
        ],
    }
    review_guard.remove_stale_approvals("owner/repo", 9, pr, "token")
    assert len(calls) == 3 and all(call[-1] == "DELETE" for call in calls)
    assert calls[1][1].endswith("security-approved%3Abbbbbbb")


def test_origin_recomputes_manifest_at_head_without_executing_submitter_code(tmp_path, monkeypatch):
    import base64

    policy = tmp_path / "trusted-vendors.yml"
    policy.write_text(
        yaml.safe_dump(
            {"version": 1, "prefixes": [{"prefix": "com.whatsapp", "vendor": "Meta", "category": "messaging"}]}
        )
    )
    raw = {"fingerprint": {"app_package": "com.whatsapp"}, "vendor_repo": "attacker/popular"}
    body = yaml.safe_dump(raw).encode()
    seen = []

    def api_mock(repo, endpoint, token):
        seen.append(endpoint)
        if "/skill.yaml?" in endpoint:
            return {"type": "file", "encoding": "base64", "size": len(body), "content": base64.b64encode(body).decode()}
        return [{"path": "skillhub/alice/chat/helpers.py", "type": "file"}]

    monkeypatch.setattr(common, "api", api_mock)
    monkeypatch.setattr(review_guard, "approved_from_api", lambda *a: "none")
    monkeypatch.setattr(
        trusted_vendor.subprocess, "run", lambda *a, **k: pytest.fail("PR code or submitter repository was executed")
    )
    pr = {"number": 9, "head": {"sha": HEAD}}
    result = trusted_vendor.origin_verdict(
        "owner/repo", pr, [{"filename": "skillhub/alice/chat/skill.yaml"}], "token", policy
    )
    assert not result["allowed"] and result["skills"][0]["trusted"]
    assert result["skills"][0]["has_submitter_python"]
    assert result["skills"][0]["warnings"] == ["skill.yaml vendor_repo ignored; only curated mappings are used"]
    assert seen == [f"contents/skillhub/alice/chat/skill.yaml?ref={HEAD}", f"contents/skillhub/alice/chat?ref={HEAD}"]


def valid_submission_result():
    return {
        "skill": "skillhub/alice/chat",
        "checks": {"validate": {"status": "pass", "exit_code": 0, "output": "OK\n", "missing_subcommand": False}},
        "signals": {"readme": True, "tests_pass": None, "fingerprints_verified": 1, "last_verified": None},
        "labels": ["skill-submission"],
    }


@pytest.mark.parametrize(
    "mutation",
    [
        lambda r: r.update(extra=True),
        lambda r: r["checks"]["validate"].update(status="green"),
        lambda r: r["checks"]["validate"].update(exit_code=True),
        lambda r: r["checks"]["validate"].update(output="<script>"),
        lambda r: r["checks"]["validate"].update(output="x" * 16001),
        lambda r: r["labels"].append("security-approved:aaaaaaa"),
        lambda r: r["signals"].update(extra=True),
        lambda r: r["signals"].update(fingerprints_verified=True),
    ],
)
def test_submission_schema_rejects_forged_results(mutation):
    result = valid_submission_result()
    mutation(result)
    with pytest.raises(ValueError):
        report.validate_submission_result(result)


def test_submission_schema_accepts_producer_and_zip_entry_cap(monkeypatch):
    import io
    import zipfile

    result = valid_submission_result()
    assert report.validate_submission_result(result) is result
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        archive.writestr("result.json", json.dumps(result))
        archive.writestr("second.json", json.dumps(result))
    monkeypatch.setattr(emulator_report.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(data.getvalue()))
    with pytest.raises(ValueError, match="only bounded result.json"):
        emulator_report.bounded_json("owner/repo", {"id": 1, "size_in_bytes": len(data.getvalue())}, "token")


def test_settle_flow_uses_v2_cache_and_verbatim_phone_script():
    workflow = yaml.safe_load(Path(".github/workflows/skill-emulator-run.yml").read_text())
    steps = workflow["jobs"]["emulator"]["steps"]
    cache = next(s for s in steps if s.get("name") == "AVD cache")
    assert cache["with"]["key"].endswith("-v2")
    snapshot = next(s for s in steps if s.get("name") == "Create AVD snapshot")
    assert snapshot["with"]["script"] == "bash /tmp/skill-emulator/phone_smoke.sh --settle-only"
    record = next(s for s in steps if s.get("name") == "Test and record skill actions")
    assert record["with"]["script"].startswith("bash /tmp/skill-emulator/phone_smoke.sh --settle-only &&")
    script = Path("scripts/ci/phone_smoke.sh").read_text()
    assert "wait_ui_idle" in script and "((ok >= 2))" in script and "dt <= 6" in script
    assert "AVD snapshot created" not in Path(".github/workflows/skill-emulator-run.yml").read_text()


def test_forged_pr_trust_artifact_is_informational_only(monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GH_TOKEN", "token")
    monkeypatch.setattr("sys.argv", ["report", "--run", "123"])
    run = {
        "event": "pull_request",
        "name": "Optional skill emulator runs",
        "path": ".github/workflows/skill-emulator-run.yml",
        "head_sha": HEAD,
        "pull_requests": [{"number": 9}],
    }
    pr = {"number": 9, "head": {"sha": HEAD}, "state": "open", "labels": []}
    calls = []

    def api_mock(repo, endpoint, token, method="GET", data=None):
        calls.append((endpoint, method, data))
        if endpoint == "actions/runs/123":
            return run
        if endpoint == "pulls/9":
            return pr
        if endpoint == "issues/9":
            return {"labels": []}
        return {}

    monkeypatch.setattr(report, "api", api_mock)
    monkeypatch.setattr(report, "pages", lambda *a: [])
    monkeypatch.setattr(review_guard, "changed_files", lambda *a: [{"filename": "skillhub/alice/chat/helpers.py"}])
    monkeypatch.setattr(
        trusted_vendor,
        "origin_verdict",
        lambda *a: {
            "allowed": False,
            "approval_source": "none",
            "skills": [{"skill": "skillhub/alice/chat", "branch": "blocked", "warnings": []}],
        },
    )
    monkeypatch.setattr(
        emulator_report,
        "artifact_list",
        lambda *a: [{"name": "skill-vendor-trust", "expired": False, "forged_allowed": True}],
    )
    monkeypatch.setattr(emulator_report, "bounded_json", lambda *a: pytest.fail("PR trust artifact was used"))
    report.main()
    body = next(data["body"] for _, method, data in calls if method == "POST" and data and "body" in data)
    assert "gate: blocked" in body and "🟢" not in body
    assert any(data == {"labels": ["pending-security-review"]} for _, _, data in calls)


def test_maintainer_comment_does_not_create_approval_label(monkeypatch):
    calls = []
    monkeypatch.setattr(report, "pages", lambda *a: [])
    monkeypatch.setattr(report, "api", lambda *a: calls.append(a))
    verdict = {"allowed": True, "approval_source": "maintainer-comment", "head_sha": HEAD}
    report.apply_vendor_label("owner/repo", 9, verdict, "token")
    assert calls == []


def test_missing_changed_file_metadata_never_produces_green(monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GH_TOKEN", "token")
    monkeypatch.setattr("sys.argv", ["emulator_report", "--run", "123"])

    def api_mock(repo, endpoint, token):
        if endpoint.startswith("actions/"):
            return {
                "event": "pull_request",
                "name": "Optional skill emulator runs",
                "head_sha": HEAD,
                "pull_requests": [{"number": 9}],
                "conclusion": "success",
            }
        return {"number": 9, "state": "open", "head": {"sha": HEAD}}

    monkeypatch.setattr(emulator_report, "api", api_mock)
    monkeypatch.setattr(review_guard, "changed_files", lambda *a: (_ for _ in ()).throw(ValueError("incomplete")))
    calls = []
    monkeypatch.setattr(emulator_report, "publish_run", lambda *a: calls.append(a))
    emulator_report.main()
    assert calls[-1][-1] is False


def test_submission_scope_skips_registry_rule_for_platform_only_prs():
    import pathlib
    import sys

    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools" / "ci"))
    import common

    # platform PR: workflows + policy + regenerated registry, no skill dirs -> allowed, no authors
    assert (
        common.submission_scope(
            [
                ".github/workflows/x.yml",
                "tools/ci/common.py",
                "skillhub/registry.json",
                "skillhub/registry/index/a.b.json",
            ]
        )
        == []
    )
    import pytest

    # skill submission that also edits the registry -> still rejected
    with pytest.raises(ValueError):
        common.submission_scope(["skillhub/alice/uber/skill.yaml", "skillhub/registry.json"])
    # registry-only PR with no platform files -> still rejected
    with pytest.raises(ValueError):
        common.submission_scope(["skillhub/registry.json"])


def test_emulator_proof_reads_submission_count_without_default():
    import pathlib

    import yaml

    wf = yaml.safe_load(
        (pathlib.Path(__file__).resolve().parents[1] / ".github/workflows/skill-emulator-run.yml").read_text()
    )
    proof = next(
        j for j in wf["jobs"].values() if j.get("name") == "skill-emulator-proof" or "proof" in str(j.get("name", ""))
    )
    step = next(st for st in proof["steps"] if "COUNT" in (st.get("env") or {}))
    assert step["env"]["COUNT"] == "${{ needs.submission.outputs.count }}"
    run = step["run"]
    assert ":-0" not in run and ":-" not in run.split("COUNT")[1][:4]
    assert run.index('[ -z "$COUNT" ]') < run.index('[ "$COUNT" = 0 ]') < run.index("PLAN_RESULT")


@pytest.mark.parametrize(
    "extra, untrusted",
    [
        (None, False),
        ("gitd/skills/engine/cli.py", True),
        ("docs/guide.md", True),
        ("scripts/run.sh", True),
        ("tools/build.py", True),
        ("pyproject.toml", True),
        ("site/index.html", True),
        ("skillhub/registry.json", True),
        ("skillhub/alice/chat/../evil.py", True),
    ],
)
@pytest.mark.parametrize("name, workflow", list(review_guard.EXPECTED.items()))
def test_reporter_skill_path_allowlist(extra, untrusted, name, workflow):
    files = [{"filename": "skillhub/alice/chat/skill.yaml"}]
    if extra:
        files.append({"filename": extra})
    assert review_guard.modified_ci(files, {"name": name, "path": workflow}) is untrusted


def test_registry_only_is_untrusted():
    run = {"name": "Skill submission", "path": review_guard.EXPECTED["Skill submission"]}
    assert review_guard.modified_ci([{"filename": "skillhub/registry/index/alice.chat.json"}], run)
    assert review_guard.modified_ci(
        [{"filename": "skillhub/alice/chat/skill.yaml", "previous_filename": "gitd/evil.py"}], run
    )


@pytest.mark.parametrize("role, source", [("admin", "sha-label"), ("maintain", "sha-label"), ("write", "none")])
def test_origin_approval_fetches_label_actor_permission(monkeypatch, role, source):
    calls = []
    label = "approved:" + HEAD

    def pages(repo, endpoint, token):
        calls.append(endpoint)
        if endpoint.endswith("/events"):
            return [{"event": "labeled", "label": {"name": label}, "actor": {"login": "approver"}}]
        return []

    def api(repo, endpoint, token):
        calls.append(endpoint)
        return {"permission": role}

    monkeypatch.setattr(review_guard, "pages", pages)
    monkeypatch.setattr(review_guard, "api", api)
    pr = {"number": 9, "head": {"sha": HEAD}, "labels": [{"name": label}]}
    assert review_guard.approved_from_api("owner/repo", pr, "token") == source
    assert "issues/9/events" in calls
    assert "collaborators/approver/permission" in calls


@pytest.mark.parametrize("role, source", [("maintain", "maintainer-comment"), ("write", "none")])
def test_origin_comment_checks_permission(monkeypatch, role, source):
    monkeypatch.setattr(
        review_guard,
        "pages",
        lambda repo, endpoint, token: (
            []
            if endpoint.endswith("/events")
            else [{"body": "security-approved " + HEAD, "user": {"login": "reviewer"}}]
        ),
    )
    monkeypatch.setattr(review_guard, "api", lambda *a: {"permission": role})
    assert (
        review_guard.approved_from_api("owner/repo", {"number": 9, "head": {"sha": HEAD}, "labels": []}, "token")
        == source
    )


def test_label_reapplication_does_not_inherit_admin_authority():
    label = "approved:" + HEAD
    events = [
        {"event": event, "label": {"name": label}, "actor": {"login": actor}}
        for event, actor in [("labeled", "admin"), ("unlabeled", "writer"), ("labeled", "writer")]
    ]
    assert (
        review_guard.approval(
            HEAD, [label], permission=lambda actor: "admin" if actor == "admin" else "write", events=events
        )
        == "none"
    )


@pytest.mark.parametrize("head, source", [(HEAD, "maintainer-comment"), ("b" * 40, "none")])
def test_early_gate_uses_api_approval_only_for_current_head(tmp_path, monkeypatch, head, source):
    calls = []
    monkeypatch.setattr(
        "sys.argv",
        [
            "trusted_vendor",
            "--matrix",
            '{"skill": ["skillhub/alice/chat"]}',
            "--policy",
            "policy.yml",
            "--output",
            str(tmp_path / "result.json"),
            "--head",
            HEAD,
            "--repo",
            "owner/repo",
            "--pr",
            "9",
        ],
    )
    monkeypatch.setenv("GH_TOKEN", "token")
    monkeypatch.setattr("tools.ci.common.api", lambda *a: {"number": 9, "head": {"sha": head}})
    monkeypatch.setattr(review_guard, "approved_from_api", lambda *a: "maintainer-comment")

    def check(skills, policy, sha, approval):
        calls.append(approval)
        return {"skills": [], "allowed": approval != "none"}

    monkeypatch.setattr(trusted_vendor, "check_skills", check)
    assert trusted_vendor.main() == 0
    assert calls == [source]


def test_trusted_vendor_main_survives_api_403(tmp_path, monkeypatch, capsys):
    import json
    import pathlib
    import sys
    import urllib.error

    root = pathlib.Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    import tools.ci.common as common
    import tools.ci.trusted_vendor as tv

    def boom(*a, **k):
        raise urllib.error.HTTPError("https://api.github.com/x", 403, "Forbidden", {}, None)

    monkeypatch.setattr(common, "api", boom)
    monkeypatch.setattr(
        tv,
        "check_skills",
        lambda skills, policy, head, source: {
            "allowed": False,
            "skills": [{"skill": skills[0], "branch": f"source={source}", "warnings": []}],
        },
    )
    out = tmp_path / "trust.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "trusted_vendor",
            "--matrix",
            json.dumps({"skill": ["skillhub/alice/uber"]}),
            "--policy",
            str(root / "skillhub/trusted-vendors.yml"),
            "--head",
            "0" * 40,
            "--repo",
            "o/r",
            "--pr",
            "7",
            "--output",
            str(out),
        ],
    )
    rc = tv.main()
    assert rc == 0
    assert json.loads(out.read_text())["allowed"] is False
    assert "source=none" in json.loads(out.read_text())["skills"][0]["branch"]
    assert "approval lookup unavailable" in capsys.readouterr().err


def test_reusable_workflow_callers_grant_what_callees_need():
    """A reusable workflow's jobs cannot exceed the caller job's permissions (GitHub rule)."""
    import pathlib

    import yaml

    root = pathlib.Path(__file__).resolve().parents[1] / ".github/workflows"
    for wf_path in root.glob("*.yml"):
        wf = yaml.safe_load(wf_path.read_text()) or {}
        for job_id, job in (wf.get("jobs") or {}).items():
            uses = job.get("uses", "")
            if not uses.startswith("./.github/workflows/"):
                continue
            callee = yaml.safe_load((root.parent.parent / uses[2:]).read_text()) or {}
            caller_perms = job.get("permissions") or wf.get("permissions") or {}
            if isinstance(caller_perms, str):
                caller_perms = {"*": caller_perms}
            for cj_id, cj in (callee.get("jobs") or {}).items():
                need = cj.get("permissions") or callee.get("permissions") or {}
                if isinstance(need, str):
                    continue
                for scope, level in need.items():
                    assert scope in caller_perms or "*" in caller_perms, (
                        f"{wf_path.name}:{job_id} calls {uses} whose job {cj_id} needs {scope}: {level}, "
                        f"but the caller grants only {caller_perms}"
                    )


def test_emulator_actions_iter_actions_accepts_list_and_mapping_forms():
    import pathlib
    import sys

    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
    from tools.ci.emulator_actions import iter_actions

    as_list = {"actions": [{"name": "open_url", "steps": []}, {"name": "open_incognito_tab", "steps": []}]}
    as_map = {"actions": {"open_url": {"steps": []}}}
    assert [n for n, _ in iter_actions(as_list)] == ["open_url", "open_incognito_tab"]
    assert iter_actions(as_map) == [("open_url", {"steps": []})]
    assert iter_actions({}) == []
    import pytest

    with pytest.raises(ValueError):
        iter_actions({"actions": [{"steps": []}]})


def test_emulator_actions_failure_reason_is_short_and_informative():
    import pathlib
    import sys

    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
    from tools.ci.emulator_actions import failure_reason

    r = failure_reason(
        ["test", "skillhub/a/b"],
        1,
        "...\n✗ ValidatorFailedError: end_state_validator returned False\n  hint: check the screen\n",
    )
    assert r.startswith("ghost skill test exit 1: ")
    assert "ValidatorFailedError" in r and len(r) <= 500
    assert failure_reason(["run", "x", "y"], 2, "") == "ghost skill run exit 2: no output"


def test_quality_signals_come_from_the_registry_implementation(tmp_path, monkeypatch):
    """submission.py no longer carries its own copy of the signal rules (review F14)."""
    import importlib.util

    repo = Path(__file__).resolve().parents[1]
    hub = tmp_path / "skillhub"
    skill = hub / "alice" / "chat"
    (skill / "demos").mkdir(parents=True)
    (skill / "skill.yaml").write_text(
        "name: chat\nversion: 1.0.0\nauthor: alice\ndescription: d\nskill_class: hard\ndata_access: []\n"
        'fingerprint: {os: android, os_version: "*", hardware: "*", app_package: com.example.chat, app_version: "*"}\n'
        "actions:\n  - name: go\n    ref_prompt: go\n    steps: [{action: sleep, duration_s: 1}]\n"
        "    end_state_validator: [{kind: text_visible, text: ok}, {kind: element_present, resource_id: x}]\n"
    )
    (skill / "README.md").write_text("# chat\n\n## Known failure modes\n\n- none\n")
    (skill / "demos" / "go.webm").write_bytes(b"\x1a\x45\xdf\xa3" + b"0" * 100)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GHOST_CI_SANDBOX_IMAGE", raising=False)
    monkeypatch.setenv("PYTHONPATH", str(repo))
    signals = submission.quality_signals(
        Path("skillhub/alice/chat"), yaml.safe_load((skill / "skill.yaml").read_text())
    )
    spec = importlib.util.spec_from_file_location("_reg_for_signals", repo / "tools" / "build_registry.py")
    registry = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(registry)
    expected = registry.doc_signals(skill, yaml.safe_load((skill / "skill.yaml").read_text()))
    units = expected.pop("validator_units")
    expected.pop("status")
    assert signals == {**expected, "validators_static": min(units.values()), "tests_pass": None, "last_verified": None}
    assert signals["demo"] is True and signals["demo_all_actions"] is True and signals["failure_modes"] is True
    assert (
        signals["validators_static"] == 2
    )  # static YAML units; the registry awards validators only on exercised actions
    report.validate_submission_result(
        {"skill": "skillhub/alice/chat", "checks": {}, "signals": signals, "labels": ["skill-submission"]}
    )


def test_quality_signals_fall_back_when_the_helper_fails(tmp_path, monkeypatch):
    skill = tmp_path / "skillhub" / "alice" / "chat"
    skill.mkdir(parents=True)
    (skill / "README.md").write_text("x")
    (skill / "demo.webm").write_bytes(b"x")
    monkeypatch.setattr(
        submission, "run_check", lambda command, **kw: {"status": "fail", "exit_code": 1, "output": "boom"}
    )
    signals = submission.quality_signals(skill, {"fingerprint": {"os": "android"}})
    assert signals == {
        "readme": True,
        "soft_md": False,
        "demo": True,
        "bench": False,
        "fingerprints_verified": 1,
        "tests_pass": None,
        "last_verified": None,
    }


def test_sandbox_mounts_trusted_tools_read_only(monkeypatch):
    seen = {}

    def fake_run(command, **kwargs):
        seen["command"] = command
        return SimpleNamespace(returncode=0, stdout="{}", stderr="")

    monkeypatch.setattr(submission.subprocess, "run", fake_run)
    monkeypatch.setenv("GHOST_CI_SANDBOX_IMAGE", "img")
    monkeypatch.setenv("GHOST_CI_TOOLS", "/tmp/skill-ci")
    submission.run_check(["python3", "/ci/tools/ci/skill_signals.py", "skillhub/a/b"])
    command = seen["command"]
    assert "--volume" in command and "/tmp/skill-ci:/ci:ro" in command
    assert command[command.index("img") + 1 :] == ["python3", "/ci/tools/ci/skill_signals.py", "skillhub/a/b"]
    monkeypatch.delenv("GHOST_CI_TOOLS")
    submission.run_check(["true"])
    assert "/tmp/skill-ci:/ci:ro" not in seen["command"]


def test_submission_workflow_preserves_registry_tools_and_mounts_them():
    text = (Path(__file__).resolve().parents[1] / ".github/workflows/skill-submission.yml").read_text()
    assert "cp tools/build_registry.py tools/quality.py /tmp/skill-ci/tools/" in text
    assert "GHOST_CI_TOOLS: /tmp/skill-ci" in text
