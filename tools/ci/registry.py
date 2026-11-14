"""Tag changed versions and regenerate the registry for the release workflow."""

import argparse
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import yaml

from tools.ci.common import changed_skills, git
from tools.ci.submission import semver


def missing_tags(paths):
    tags = set(git("tag", "--list").splitlines())
    result = []
    for directory in paths:
        spec = Path(directory) / "skill.yaml"
        if not spec.is_file():
            continue
        metadata = yaml.safe_load(spec.read_text())
        version = str(metadata["version"])
        semver(version)
        _, author, slug = Path(directory).parts
        tag = f"{author}/{slug}-v{version}"
        if tag not in tags:
            result.append(tag)
    return result


def commit_generated_wrappers():
    """Include generated SKILL.md files in the tree that release tags pin."""
    subprocess.check_output(["python3", "tools/build_registry.py", "skillhub/"])
    wrappers = sorted(str(p) for p in Path("skillhub").glob("*/*/SKILL.md"))
    if not wrappers:
        return
    subprocess.run(["git", "add", "--", *wrappers], check=True)
    if subprocess.run(["git", "diff", "--cached", "--quiet", "--", *wrappers]).returncode:
        subprocess.run(["git", "commit", "-m", "Generate Skill Hub wrappers [skip ci]", "--", *wrappers], check=True)


def prepare_releases(paths, output):
    """Archive committed trees before any remote writes or signing."""
    output.mkdir(parents=True, exist_ok=True)
    records = []
    commit = git("rev-parse", "HEAD")
    tags = set(missing_tags(paths))
    for directory in paths:
        spec = Path(directory) / "skill.yaml"
        if not spec.is_file():
            continue
        version = str(yaml.safe_load(spec.read_text())["version"])
        _, author, slug = Path(directory).parts
        tag = f"{author}/{slug}-v{version}"
        if tag not in tags:
            continue
        filename = f"{author}.{slug}-v{version}.tar.gz"
        archive = subprocess.check_output(["git", "archive", "--format=tar.gz", f"{commit}:{directory}"])
        (output / filename).write_bytes(archive)
        records.append(
            {
                "author": author,
                "slug": slug,
                "version": version,
                "tag": tag,
                "commit": commit,
                "git_tree": git("rev-parse", f"{commit}:{directory}"),
                "sha256": hashlib.sha256(archive).hexdigest(),
                "size": len(archive),
                "released_at": git("show", "-s", "--format=%cI", commit),
                "asset": filename,
                "attestation": filename + ".sigstore.json",
            }
        )
    (output / "manifest.json").write_text(json.dumps(records, indent=2))
    return records


def publish_signed(output, repo):
    records = json.loads((output / "manifest.json").read_text())
    for entry in records:
        archive = output / entry["asset"]
        bundle = output / entry["attestation"]
        if not bundle.is_file() or hashlib.sha256(archive.read_bytes()).hexdigest() != entry["sha256"]:
            raise ValueError("Signed release bundle missing or archive changed")
        identity = f"https://github.com/{repo}/.github/workflows/skillhub-registry.yml@refs/heads/main"
        subprocess.run(
            [
                "cosign",
                "verify-blob",
                "--bundle",
                str(bundle),
                "--certificate-identity",
                identity,
                "--certificate-oidc-issuer",
                "https://token.actions.githubusercontent.com",
                str(archive),
            ],
            check=True,
        )
        subprocess.run(["git", "tag", entry["tag"], entry["commit"]], check=True)
    if records:
        subprocess.run(["git", "push", "origin", *[f"refs/tags/{entry['tag']}" for entry in records]], check=True)
    for entry in records:
        subprocess.run(
            [
                "gh",
                "release",
                "create",
                entry["tag"],
                str(output / entry["asset"]),
                str(output / entry["attestation"]),
                "--verify-tag",
                "--title",
                entry["tag"],
                "--notes",
                "Skill Hub release with Sigstore bundle and build provenance.",
            ],
            check=True,
        )
    return records


def write_indexes(records, root=Path("skillhub/registry/index")):
    root.mkdir(parents=True, exist_ok=True)
    paths = []
    for record in records:
        path = root / f"{record['author']}.{record['slug']}.json"
        entry = {
            key: record[key]
            for key in ("version", "tag", "commit", "git_tree", "sha256", "size", "released_at", "attestation")
        }
        path.write_text(json.dumps(entry, indent=2) + "\n")
        paths.append(str(path))
    return paths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--publish-signed", action="store_true")
    parser.add_argument("--artifacts", type=Path, default=Path("skill-releases"))
    args = parser.parse_args()
    base = args.base
    if set(base) == {"0"}:
        base = git("hash-object", "-t", "tree", "/dev/null")
    paths = changed_skills(base)
    if args.prepare:
        commit_generated_wrappers()
        records = prepare_releases(paths, args.artifacts)
        with open(os.environ["GITHUB_OUTPUT"], "a") as output:
            output.write(f"count={len(records)}\n")
        return
    records = publish_signed(args.artifacts, os.environ["GITHUB_REPOSITORY"]) if args.publish_signed else []
    tags = [] if args.publish_signed else missing_tags(paths)
    for tag in tags:
        subprocess.run(["git", "tag", tag], check=True)
    if tags:
        subprocess.run(["git", "push", "origin", *[f"refs/tags/{tag}" for tag in tags]], check=True)
    # Capture before writing so a failed builder cannot truncate the registry.
    # Real wall-clock date: maintenance points decay with time, not with the last skill commit (P1-7).
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    registry = subprocess.check_output(["python3", "tools/build_registry.py", "skillhub/", "--now", now])
    discovery = json.loads(registry)
    for skill in discovery.get("skills", {}).values():
        for version in skill.get("versions", {}).values():
            if not version.get("commit"):
                raise ValueError("Every registry version must pin a commit SHA")
    Path("skillhub/registry.json").write_bytes(registry)
    codeowners = subprocess.check_output(["python3", "tools/build_codeowners.py", "skillhub/"])
    Path(".github").mkdir(exist_ok=True)
    Path(".github/CODEOWNERS").write_bytes(codeowners)  # GitHub ignores CODEOWNERS outside root, .github/ or docs/
    indexes = write_indexes(records)
    generated = sorted(
        set(
            [
                "skillhub/registry.json",
                ".github/CODEOWNERS",
                *indexes,
                *[str(p) for p in Path("skillhub/registry/index").glob("*.json")],
                *[str(p) for p in Path("skillhub").glob("*/*/SKILL.md")],
            ]
        )
    )
    subprocess.run(["git", "add", "--", *generated], check=True)
    if subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode:
        subprocess.run(["git", "commit", "-m", "Update Skill Hub registry [skip ci]", "--", *generated], check=True)
        subprocess.run(["git", "push", "origin", "HEAD:main"], check=True)


if __name__ == "__main__":
    main()
