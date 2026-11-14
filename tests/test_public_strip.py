"""scripts/public-strip.txt names the internal-only paths release.sh removes before anything goes public."""

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
HAS_STRIP_LIST = (REPO / "scripts/public-strip.txt").exists()
needs_strip_list = pytest.mark.skipif(not HAS_STRIP_LIST, reason="the strip list is removed from the public tree by release.sh")


def strip_paths():
    lines = (REPO / "scripts/public-strip.txt").read_text().splitlines()
    return [line.strip() for line in lines if line.strip() and not line.startswith("#")]


@needs_strip_list
def test_strip_list_covers_internal_docs_and_every_entry_exists():
    paths = strip_paths()
    assert "docs/reports/" in paths and "docs/HUMAN/" in paths and "skillhub/_drafts/" in paths and "premium/" in paths
    missing = [p for p in paths if not (REPO / p.lstrip("!")).exists()]
    assert not missing, f"strip list names paths that do not exist: {missing}"


def test_release_script_applies_the_strip_list():
    script = (REPO / "scripts/release.sh").read_text()
    assert "scripts/public-strip.txt" in script
    # The strip runs after the private diff is applied and before the release commit on the public branch.
    assert (
        script.index("git apply")
        < script.index("public-strip.txt")
        < script.rindex('git commit -m "Release v$NEW_VERSION"')
    )


def test_release_script_runs_the_gate_before_the_release_commit():
    script = (REPO / "scripts/release.sh").read_text()
    strip_end = script.index("done < scripts/public-strip.txt")
    gate = script.index("bash scripts/release_gate.sh")
    release_commit = script.index('git commit -m "Release v$NEW_VERSION"', strip_end)
    assert strip_end < gate < release_commit


def _gate_repo(tmp_path, files):
    import subprocess

    repo = tmp_path / "repo"
    repo.mkdir()
    for rel, text in files.items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    env = {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.com",
        "PATH": "/usr/bin:/bin",
    }
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, env=env)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, env=env)
    return subprocess.run(
        ["bash", str(REPO / "scripts/release_gate.sh"), "strip.txt"], cwd=repo, env=env, capture_output=True, text=True
    )


def test_release_gate_passes_a_clean_tree(tmp_path):
    result = _gate_repo(tmp_path, {"strip.txt": "docs/HUMAN/\n", "README.md": "public\n"})
    assert result.returncode == 0, result.stderr


def test_release_gate_fails_on_a_surviving_strip_path(tmp_path):
    result = _gate_repo(tmp_path, {"strip.txt": "docs/HUMAN/\n", "docs/HUMAN/notes.md": "x\n"})
    assert result.returncode == 1 and "docs/HUMAN/" in result.stderr


def test_release_gate_fails_on_a_mailbox_address(tmp_path):
    # Construct the fixture at runtime so the release gate does not flag its own test.
    mailbox = "someone" + "@" + "proton.me"
    result = _gate_repo(tmp_path, {"strip.txt": "docs/HUMAN/\n", "docs/a.md": f"mail {mailbox} now\n"})
    assert result.returncode == 1 and "proton.me" in result.stderr


def test_release_gate_ignores_the_public_signup_url(tmp_path):
    result = _gate_repo(
        tmp_path, {"strip.txt": "docs/HUMAN/\n", "docs/a.md": "https://account.proton.me/mail/signup\n"}
    )
    assert result.returncode == 0, result.stderr


def test_release_gate_allows_a_kept_file_inside_a_stripped_directory(tmp_path):
    ok = _gate_repo(tmp_path, {"strip.txt": "docs/reports/\n!docs/reports/kept.md\n", "docs/reports/kept.md": "public\n"})
    assert ok.returncode == 0, ok.stderr
    (tmp_path / "b").mkdir()
    bad = _gate_repo(
        tmp_path / "b",
        {"strip.txt": "docs/reports/\n!docs/reports/kept.md\n", "docs/reports/kept.md": "x\n", "docs/reports/other.md": "x\n"},
    )
    assert bad.returncode == 1 and "docs/reports/" in bad.stderr
