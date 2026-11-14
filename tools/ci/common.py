"""Small shared helpers for offline-testable Skill Hub automation."""

import json
import re
import subprocess
import urllib.request
from pathlib import PurePosixPath


def git(*args):
    return subprocess.check_output(["git", *args], text=True).strip()


def changed_skills(base, head="HEAD"):
    return skill_dirs(changed_paths(base, head))


def changed_paths(base, head="HEAD"):
    return (
        subprocess.check_output(["git", "diff", "--name-only", "--no-renames", "-z", base, head, "--"])
        .decode()
        .split("\0")
    )


def submission_scope(paths):
    """Require one author namespace and prohibit generated registry edits.

    The rules target skill submissions: a PR that touches platform files (.github/,
    tools/ci/, scoring, the trusted-vendors policy, verifier-keys.yml) and no skill directory is a
    maintainer platform PR and is not subject to the generated-registry prohibition;
    a registry-only PR with no platform files is still rejected; the reporters separately flag
    such PRs as CI/policy-touching so their results are never trusted as a submission.
    """
    platform_prefixes = (".github/", "tools/ci/", "skillhub/scoring/")
    platform_files = {"skillhub/trusted-vendors.yml", "skillhub/verifier-keys.yml"}
    is_platform = any(p.startswith(platform_prefixes) or p in platform_files for p in paths if p)
    if is_platform and not skill_dirs(paths):
        return []
    authors = set()
    for path in paths:
        parts = PurePosixPath(path).parts
        if not parts:
            continue
        if parts[0] == "registry" or path == "skillhub/registry.json" or parts[:2] == ("skillhub", "registry"):
            raise ValueError("PRs cannot edit generated registry files")
        if len(parts) >= 3 and parts[0] == "skillhub" and parts[1] != "scoring":
            authors.add(parts[1])  # skillhub/scoring/ is the maintainer-owned scoring table, not an author
    if len(authors) > 1:
        raise ValueError("PRs may touch only one author directory")
    return sorted(authors)


RESERVED_HUB_DIRS = {"registry", "scoring", "community", "icons", "demos"}


def skill_dirs(paths):
    dirs = set()
    for path in paths:
        parts = PurePosixPath(path).parts
        # skillhub/<author>/<slug>/...; reserved top-level dirs (registry, scoring, _guides, any _*) are not skills
        if (
            len(parts) >= 4
            and parts[0] == "skillhub"
            and parts[1] not in RESERVED_HUB_DIRS
            and not parts[1].startswith("_")
            and all(re.fullmatch(r"[A-Za-z0-9_-]+", p) for p in parts[1:3])
        ):
            dirs.add("/".join(parts[:3]))
    return sorted(dirs)


def api(repo, endpoint, token, method="GET", data=None):
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/{endpoint}",
        data=None if data is None else json.dumps(data).encode(),
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.load(response)


def pages(repo, endpoint, token):
    result = []
    for page in range(1, 101):
        rows = api(repo, f"{endpoint}{'&' if '?' in endpoint else '?'}per_page=100&page={page}", token)
        result.extend(rows)
        if len(rows) < 100:
            return result
    raise RuntimeError("GitHub pagination limit exceeded")
