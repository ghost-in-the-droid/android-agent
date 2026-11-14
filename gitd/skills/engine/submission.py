"""Opt-in PR submission (verification artifacts and whole skills) on an isolated git index.

All remote operations run only behind --push. The caller's checkout and index are
untouched; every commit is parented on the target's default branch.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path

DEFAULT_VERIFY_REPO = "ghost-in-the-droid/android-agent"


def target_repo(explicit: str | None) -> str:
    repo = explicit or os.environ.get("GHOST_HUB_REPO") or DEFAULT_VERIFY_REPO
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*", repo):
        raise ValueError("Verification repo must be <owner>/<repo>, not a URL or remote name")
    return repo


def checkout_root(skill_dir: Path) -> Path:
    for candidate in [Path.cwd(), *Path.cwd().parents, skill_dir.resolve(), *skill_dir.resolve().parents]:
        if (candidate / ".git").exists() and (candidate / "skillhub").is_dir():
            return candidate.resolve()
    raise ValueError("Verification requires a source checkout containing .git and skillhub/")


def verification_dir(root: Path, skill) -> Path:
    destination = root / "skillhub" / skill.author / skill.name / "verifications"
    if not destination.resolve().is_relative_to(root.resolve()):
        raise ValueError("Verification path escapes the source checkout")
    return destination


def _command(argv: list[str], root: Path, *, env=None, input=None) -> str:
    try:
        return subprocess.run(
            argv, cwd=root, env=env, input=input, check=True, capture_output=True, text=True, timeout=120
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        detail = getattr(exc, "stderr", None) or str(exc)
        raise RuntimeError(f"Verification submission failed ({argv[0]} {argv[1]}): {detail}") from exc


def push_verification(root: Path, artifact: Path, plan: dict) -> str:
    """Commit only the artifact, push to the explicit target, and open its PR."""
    repo = target_repo(plan["repo"])
    relative = artifact.resolve().relative_to(root.resolve()).as_posix()
    if relative not in plan["files"] or len(plan["files"]) != 1:
        raise ValueError("Submission must contain exactly the verification artifact")
    if not re.fullmatch(r"skillhub/[^/]+/[^/]+/verifications/[^/]+\.json", relative):
        raise ValueError("Submission artifact must be under skillhub/<author>/<slug>/verifications/")
    branch = plan["branch"]
    _command(["git", "check-ref-format", "--branch", branch], root)
    base = _command(["gh", "repo", "view", repo, "--json", "defaultBranchRef", "--jq", ".defaultBranchRef.name"], root)
    if not base or base == "null":
        raise ValueError("Target repository has no default branch")
    _command(["git", "check-ref-format", "--branch", base], root)
    url = f"https://github.com/{repo}.git"
    _command(["git", "fetch", "--no-tags", url, f"refs/heads/{base}"], root)
    parent = _command(["git", "rev-parse", "FETCH_HEAD^{commit}"], root)
    if not re.fullmatch(r"[0-9a-f]{40,64}", parent):
        raise ValueError("Fetched target does not resolve to a commit")
    skill_yaml = "/".join(relative.split("/")[:3]) + "/skill.yaml"
    _command(["git", "cat-file", "-e", f"{parent}:{skill_yaml}"], root)
    with tempfile.TemporaryDirectory(prefix=".ghost-verification-", dir=root) as temporary:
        directory = Path(temporary)
        environment = dict(os.environ, GIT_INDEX_FILE=str(directory / "index"))
        _command(["git", "read-tree", parent], root, env=environment)
        blob = _command(["git", "hash-object", "-w", "--", relative], root)
        _command(["git", "update-index", "--add", "--cacheinfo", "100644", blob, relative], root, env=environment)
        tree = _command(["git", "write-tree"], root, env=environment)
        commit = _command(["git", "commit-tree", tree, "-p", parent], root, input=plan["title"] + "\n")
        if not re.fullmatch(r"[0-9a-f]{40,64}", commit):
            raise ValueError("Verification commit was not created")
        reference = f"refs/heads/{branch}"
        _command(["git", "update-ref", reference, commit, "0" * len(commit)], root)
        _command(["git", "push", url, f"{reference}:{reference}"], root)
        body = directory / "pr-body.md"
        body.write_text(plan["body"], encoding="utf-8")
        return _command(
            [
                "gh",
                "pr",
                "create",
                "--repo",
                repo,
                "--base",
                base,
                "--head",
                branch,
                "--title",
                plan["title"],
                "--body-file",
                str(body),
            ],
            root,
        )


def _login(root: Path) -> str:
    login = _command(["gh", "api", "user", "--jq", ".login"], root)
    if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?", login):
        raise ValueError("gh is not logged in (gh auth login) or returned an unexpected login")
    return login


def _can_push(root: Path, repo: str) -> bool:
    """True when the caller may push branches to ``repo`` itself (maintainer, org member): no fork needed."""
    try:
        return _command(["gh", "api", f"repos/{repo}", "--jq", ".permissions.push"], root) == "true"
    except Exception:  # no access or API error: fall back to the fork path
        return False


def _default_branch(root: Path, repo: str) -> str:
    base = _command(["gh", "repo", "view", repo, "--json", "defaultBranchRef", "--jq", ".defaultBranchRef.name"], root)
    if not base or base == "null":
        raise ValueError("Target repository has no default branch")
    _command(["git", "check-ref-format", "--branch", base], root)
    return base


def _fetch_base(root: Path, repo: str, base: str) -> str:
    _command(["git", "fetch", "--no-tags", f"https://github.com/{repo}.git", f"refs/heads/{base}"], root)
    parent = _command(["git", "rev-parse", "FETCH_HEAD^{commit}"], root)
    if not re.fullmatch(r"[0-9a-f]{40,64}", parent):
        raise ValueError("Fetched target does not resolve to a commit")
    return parent


def skill_submission_files(root: Path, skill_dir: Path) -> list[str]:
    """Regular files of one skillhub/<author>/<slug>/ directory, relative to the checkout root."""
    relative_dir = skill_dir.resolve().relative_to(root.resolve()).as_posix()
    if not re.fullmatch(r"skillhub/[^/]+/[^/]+", relative_dir):
        raise ValueError("Submission must be a skillhub/<author>/<slug> directory inside the checkout")
    files = []
    for path in sorted(skill_dir.resolve().rglob("*")):
        if "__pycache__" in path.parts or path.suffix == ".pyc" or path.is_dir():
            continue
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Submission refuses symlinks and special files: {path.name}")
        files.append(path.relative_to(root.resolve()).as_posix())
    if not any(f.endswith("/skill.yaml") for f in files):
        raise ValueError("Submission directory has no skill.yaml")
    return files


def push_skill(root: Path, skill_dir: Path, plan: dict) -> str:
    """Commit the skill directory on an isolated index, push it to the caller's fork, open or update the PR.

    The branch on the fork is force-updated: a resubmission is a fresh commit on the
    target's default branch, not a child of the previous attempt.
    """
    repo = target_repo(plan["repo"])
    files = skill_submission_files(root, skill_dir)
    if sorted(plan["files"]) != files:
        raise ValueError("Submission plan does not match the files on disk; rerun submit")
    branch = plan["branch"]
    _command(["git", "check-ref-format", "--branch", branch], root)
    login = _login(root)
    owner, name = repo.split("/")
    if owner.casefold() == login.casefold() or _can_push(root, repo):
        push_repo, head = repo, branch
    else:
        _command(["gh", "repo", "fork", repo, "--clone=false"], root)  # idempotent: "already exists" is success
        push_repo, head = f"{login}/{name}", f"{login}:{branch}"
    base = _default_branch(root, repo)
    parent = _fetch_base(root, repo, base)
    with tempfile.TemporaryDirectory(prefix=".ghost-submission-", dir=root) as temporary:
        directory = Path(temporary)
        environment = dict(os.environ, GIT_INDEX_FILE=str(directory / "index"))
        _command(["git", "read-tree", parent], root, env=environment)
        for relative in files:
            blob = _command(["git", "hash-object", "-w", "--", relative], root)
            mode = "100755" if os.access(root / relative, os.X_OK) else "100644"
            _command(["git", "update-index", "--add", "--cacheinfo", mode, blob, relative], root, env=environment)
        tree = _command(["git", "write-tree"], root, env=environment)
        commit = _command(["git", "commit-tree", tree, "-p", parent], root, input=plan["title"] + "\n")
        if not re.fullmatch(r"[0-9a-f]{40,64}", commit):
            raise ValueError("Submission commit was not created")
        reference = f"refs/heads/{branch}"
        _command(["git", "update-ref", reference, commit], root)
        _command(["git", "push", f"https://github.com/{push_repo}.git", f"+{reference}:{reference}"], root)
        existing = _command(
            [
                "gh",
                "pr",
                "list",
                "--repo",
                repo,
                "--head",
                head,
                "--state",
                "open",
                "--json",
                "url",
                "--jq",
                ".[0].url",
            ],
            root,
        )
        if existing.startswith("https://"):
            return existing
        body = directory / "pr-body.md"
        body.write_text(plan["body"], encoding="utf-8")
        return _command(
            [
                "gh",
                "pr",
                "create",
                "--repo",
                repo,
                "--base",
                base,
                "--head",
                head,
                "--title",
                plan["title"],
                "--body-file",
                str(body),
            ],
            root,
        )
