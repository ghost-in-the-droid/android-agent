"""CLI entry point: android-agent skill install/list/update/remove/validate/search"""

import argparse
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import requests
import yaml

logger = logging.getLogger(__name__)

REGISTRY_URL = "https://api.github.com/repos/ghost-in-the-droid/skills/contents/index.json"
COMMUNITY_URL = "https://api.github.com/repos/ghost-in-the-droid/skills/contents/community.json"
REGISTRY_RAW_BASE = "https://raw.githubusercontent.com/ghost-in-the-droid/skills/main/registry"
_GITHUB_HEADERS = {"Accept": "application/vnd.github.raw"}
SKILLS_DIR = Path(__file__).resolve().parent / "skills"

# Required fields in skill.yaml
REQUIRED_FIELDS = ["name", "display_name", "description", "version", "app_package", "author"]

# Patterns considered dangerous in action/workflow code
DANGEROUS_PATTERNS = ["os.system(", "eval(", "exec(", "subprocess.call(", "__import__"]


def _fetch_registry() -> list[dict]:
    """Fetch official registry index.json."""
    try:
        resp = requests.get(REGISTRY_URL, headers=_GITHUB_HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return data.get("skills", data) if isinstance(data, dict) else data
    except Exception as e:
        logger.warning("could not fetch registry: %s", e)
        return []


def _fetch_community() -> list[dict]:
    """Fetch community registry community.json."""
    try:
        resp = requests.get(COMMUNITY_URL, headers=_GITHUB_HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return data.get("skills", data) if isinstance(data, dict) else data
    except Exception as e:
        logger.warning("could not fetch community registry: %s", e)
        return []


def _is_github_url(target: str) -> bool:
    """Check if a string looks like a GitHub URL."""
    return bool(re.match(r"(https?://)?github\.com/", target)) or target.startswith("github.com/")


def _is_local_path(target: str) -> bool:
    """Check if target is a local path."""
    return target.startswith("./") or target.startswith("/") or target.startswith("../") or os.path.isdir(target)


def _normalize_github_url(url: str) -> str:
    """Ensure GitHub URL has https:// prefix."""
    if not url.startswith("http"):
        url = "https://" + url
    # Strip trailing slashes and .git suffix for consistency
    url = url.rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]
    return url


def _download_skill_from_registry(name: str) -> Path | None:
    """Download a skill from the official registry by name.

    Downloads individual files from the registry raw GitHub URL.
    Returns the temp directory path on success, None on failure.
    """
    # Fetch the registry to find the skill metadata
    registry = _fetch_registry()
    entry = next((s for s in registry if s.get("name") == name), None)
    if entry is None:
        logger.info("Skill '%s' not found in official registry.", name)
        return None

    # Download the skill folder from raw GitHub
    tmp = Path(tempfile.mkdtemp(prefix=f"android-agent-skill-{name}-"))
    base_url = f"{REGISTRY_RAW_BASE}/{name}"

    # Files and dirs we expect in a skill
    files_to_try = [
        "skill.yaml",
        "elements.yaml",
        "__init__.py",
        "actions/__init__.py",
        "workflows/__init__.py",
    ]
    # Add action/workflow files from registry metadata
    for action in entry.get("actions", []):
        aname = action if isinstance(action, str) else action.get("name", "")
        if aname:
            files_to_try.append(f"actions/{aname}.py")
    for wf in entry.get("workflows", []):
        wname = wf if isinstance(wf, str) else wf.get("name", "")
        if wname:
            files_to_try.append(f"workflows/{wname}.py")
            files_to_try.append(f"workflows/{wname}.json")

    downloaded = 0
    for rel_path in files_to_try:
        url = f"{base_url}/{rel_path}"
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                dest = tmp / rel_path
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(resp.content)
                downloaded += 1
        except Exception:
            pass

    if downloaded == 0 or not (tmp / "skill.yaml").exists():
        logger.error("Failed to download skill '%s' from registry.", name)
        shutil.rmtree(tmp, ignore_errors=True)
        return None

    return tmp


def _clone_github_skill(url: str) -> Path | None:
    """Clone a skill from a GitHub URL. Returns temp dir on success."""
    url = _normalize_github_url(url)
    tmp = Path(tempfile.mkdtemp(prefix="android-agent-skill-"))
    clone_target = tmp / "repo"
    try:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", url, str(clone_target)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            logger.error("git clone failed: %s", result.stderr.strip())
            shutil.rmtree(tmp, ignore_errors=True)
            return None
    except FileNotFoundError:
        logger.error("git is not installed. Install git or use a registry skill name.")
        shutil.rmtree(tmp, ignore_errors=True)
        return None
    except subprocess.TimeoutExpired:
        logger.error("git clone timed out.")
        shutil.rmtree(tmp, ignore_errors=True)
        return None

    # Check if skill.yaml is at the root of the cloned repo
    if (clone_target / "skill.yaml").exists():
        return clone_target

    # Maybe it's inside a registry/ subfolder — look for first skill.yaml
    for candidate in clone_target.rglob("skill.yaml"):
        return candidate.parent

    logger.error("No skill.yaml found in %s", url)
    shutil.rmtree(tmp, ignore_errors=True)
    return None


def _validate_skill_dir(skill_dir: Path, verbose: bool = True) -> bool:
    """Validate a skill directory. Returns True if valid."""
    ok = True

    # Check skill.yaml exists and has required fields
    skill_yaml = skill_dir / "skill.yaml"
    if not skill_yaml.exists():
        if verbose:
            logger.error("  FAIL: skill.yaml not found in %s", skill_dir)
        return False

    try:
        meta = yaml.safe_load(skill_yaml.read_text())
        if not isinstance(meta, dict):
            if verbose:
                logger.error("  FAIL: skill.yaml is not a valid YAML mapping")
            return False
    except Exception as e:
        if verbose:
            logger.error("  FAIL: skill.yaml parse error: %s", e)
        return False

    for field in REQUIRED_FIELDS:
        if field not in meta:
            if verbose:
                logger.warning("  WARN: missing recommended field '%s' in skill.yaml", field)

    name = meta.get("name", "")
    if name and not name.replace("-", "").replace("_", "").isalnum():
        if verbose:
            logger.error("  FAIL: skill name '%s' must be alphanumeric (hyphens/underscores allowed)", name)
        ok = False

    # Check elements.yaml if present
    elem_path = skill_dir / "elements.yaml"
    if elem_path.exists():
        try:
            data = yaml.safe_load(elem_path.read_text())
            if data is not None and not isinstance(data, dict):
                if verbose:
                    logger.error("  FAIL: elements.yaml is not a valid YAML mapping")
                ok = False
        except Exception as e:
            if verbose:
                logger.error("  FAIL: elements.yaml parse error: %s", e)
            ok = False

    # Check for dangerous imports in actions/ and workflows/
    for folder in ["actions", "workflows"]:
        folder_path = skill_dir / folder
        if not folder_path.exists():
            continue
        for py_file in folder_path.glob("*.py"):
            if py_file.name == "__init__.py":
                continue
            content = py_file.read_text()
            for pattern in DANGEROUS_PATTERNS:
                if pattern in content:
                    if verbose:
                        logger.error("  FAIL: dangerous call '%s' in %s", pattern, py_file.name)
                    ok = False
            # Also check the file compiles
            try:
                compile(content, str(py_file), "exec")
            except SyntaxError as e:
                if verbose:
                    logger.error("  FAIL: syntax error in %s: %s", py_file.name, e)
                ok = False

    return ok


def _install_to_skills_dir(source_dir: Path, name: str | None = None) -> bool:
    """Copy a skill from source_dir into the skills directory. Returns True on success."""
    skill_yaml = source_dir / "skill.yaml"
    if not skill_yaml.exists():
        logger.error("no skill.yaml in source directory.")
        return False

    meta = yaml.safe_load(skill_yaml.read_text()) or {}
    skill_name = name or meta.get("name", source_dir.name)
    # Sanitize
    skill_name = re.sub(r"[^a-zA-Z0-9_-]", "_", skill_name).strip("_")

    dest = SKILLS_DIR / skill_name
    if dest.exists():
        logger.info("Updating existing skill '%s'...", skill_name)
        shutil.rmtree(dest)

    shutil.copytree(source_dir, dest, dirs_exist_ok=True)

    # Remove .git folder if cloned
    git_dir = dest / ".git"
    if git_dir.exists():
        shutil.rmtree(git_dir)

    # Ensure __init__.py exists
    init_file = dest / "__init__.py"
    if not init_file.exists():
        init_file.write_text(f'"""Skill: {skill_name}"""\n')

    # Count actions and workflows
    action_count = sum(1 for f in (dest / "actions").glob("*.py") if f.name != "__init__.py") if (dest / "actions").exists() else 0
    workflow_count = sum(1 for f in (dest / "workflows").glob("*.py") if f.name != "__init__.py") if (dest / "workflows").exists() else 0
    # Also count recorded workflows
    if (dest / "workflows").exists():
        workflow_count += sum(1 for _ in (dest / "workflows").glob("*.json"))

    logger.info("Installed skill '%s' (%d actions, %d workflows)", skill_name, action_count, workflow_count)
    logger.info("  -> %s", dest)
    return True


# ── CLI Commands ──────────────────────────────────────────────────────────


def cmd_install(args):
    """Install a skill from registry, GitHub URL, or local path."""
    target = args.target

    if _is_local_path(target):
        # Local path install
        source = Path(target).resolve()
        if not source.is_dir():
            logger.error("'%s' is not a directory.", target)
            return 1
        if not _validate_skill_dir(source, verbose=True):
            if not args.force:
                logger.error("Validation failed. Use --force to install anyway.")
                return 1
            logger.warning("Forcing install despite validation warnings...")
        return 0 if _install_to_skills_dir(source) else 1

    elif _is_github_url(target):
        # GitHub URL install
        logger.info("Cloning from %s...", target)
        source = _clone_github_skill(target)
        if source is None:
            return 1
        if not _validate_skill_dir(source, verbose=True):
            if not args.force:
                logger.error("Validation failed. Use --force to install anyway.")
                shutil.rmtree(source.parent if source.parent.name != "repo" else source, ignore_errors=True)
                return 1
        result = _install_to_skills_dir(source)
        # Clean up temp
        tmp_root = source
        while tmp_root.parent != tmp_root and "android-agent-skill" not in tmp_root.name:
            tmp_root = tmp_root.parent
        shutil.rmtree(tmp_root, ignore_errors=True)
        return 0 if result else 1

    else:
        # Assume it's a registry skill name
        logger.info("Looking up '%s' in official registry...", target)
        source = _download_skill_from_registry(target)
        if source is None:
            # Try community registry
            logger.info("Trying community registry...")
            community = _fetch_community()
            entry = next((s for s in community if s.get("name") == target), None)
            if entry and entry.get("repo_url"):
                logger.info("Found in community: %s", entry["repo_url"])
                source = _clone_github_skill(entry["repo_url"])
            if source is None:
                logger.error("Skill '%s' not found in any registry.", target)
                return 1

        if not _validate_skill_dir(source, verbose=True):
            if not args.force:
                logger.error("Validation failed. Use --force to install anyway.")
                shutil.rmtree(source, ignore_errors=True)
                return 1
        result = _install_to_skills_dir(source, name=target)
        shutil.rmtree(source, ignore_errors=True)
        return 0 if result else 1


def cmd_list(args):
    """List installed skills."""
    if not SKILLS_DIR.is_dir():
        logger.info("No skills directory found.")
        return 0

    skills = []
    for d in sorted(SKILLS_DIR.iterdir()):
        if d.is_dir() and (d / "skill.yaml").exists() and not d.name.startswith("_"):
            try:
                meta = yaml.safe_load((d / "skill.yaml").read_text()) or {}
                skills.append({
                    "dir": d.name,
                    "name": meta.get("name", d.name),
                    "version": meta.get("version", "0.0.0"),
                    "app_package": meta.get("app_package", ""),
                    "description": meta.get("description", ""),
                })
            except Exception as e:
                skills.append({"dir": d.name, "name": d.name, "error": str(e)})

    if not skills:
        logger.info("No skills installed.")
        return 0

    # Print as formatted table
    print(f"{'Name':<20} {'Version':<10} {'Package':<30} {'Description'}")
    print("-" * 90)
    for s in skills:
        if "error" in s:
            print(f"{s['dir']:<20} {'ERROR':<10} {'':<30} {s['error']}")
        else:
            desc = (s["description"][:40] + "...") if len(s["description"]) > 40 else s["description"]
            print(f"{s['name']:<20} {s['version']:<10} {s['app_package']:<30} {desc}")

    print(f"\n{len(skills)} skill(s) installed in {SKILLS_DIR}")
    return 0


def cmd_update(args):
    """Re-fetch the latest version of a skill."""
    name = args.name
    dest = SKILLS_DIR / name
    if not dest.exists():
        logger.error("Skill '%s' is not installed.", name)
        return 1

    meta_path = dest / "skill.yaml"
    if not meta_path.exists():
        logger.error("Skill '%s' has no skill.yaml, cannot determine source.", name)
        return 1

    meta = yaml.safe_load(meta_path.read_text()) or {}
    repo_url = meta.get("repo_url", "")

    if repo_url and _is_github_url(repo_url):
        logger.info("Updating '%s' from %s...", name, repo_url)
        source = _clone_github_skill(repo_url)
        if source:
            result = _install_to_skills_dir(source, name=name)
            shutil.rmtree(source.parent if source.parent != source else source, ignore_errors=True)
            return 0 if result else 1

    # Fallback: try official registry
    logger.info("Updating '%s' from official registry...", name)
    source = _download_skill_from_registry(name)
    if source:
        result = _install_to_skills_dir(source, name=name)
        shutil.rmtree(source, ignore_errors=True)
        return 0 if result else 1

    logger.error("Could not find update source for '%s'. Specify a repo_url in skill.yaml.", name)
    return 1


def cmd_remove(args):
    """Remove an installed skill."""
    name = args.name
    dest = SKILLS_DIR / name

    if not dest.exists():
        logger.error("Skill '%s' is not installed.", name)
        return 1

    # Protect built-in skills
    if name in ("_base", "tiktok", "play_store"):
        if not args.force:
            logger.error("'%s' is a built-in skill. Use --force to remove anyway.", name)
            return 1

    shutil.rmtree(dest)
    logger.info("Removed skill '%s'.", name)
    return 0


def cmd_validate(args):
    """Validate a skill directory."""
    target = Path(args.path).resolve()
    if not target.is_dir():
        logger.error("'%s' is not a directory.", args.path)
        return 1

    logger.info("Validating %s...", target)
    if _validate_skill_dir(target, verbose=True):
        logger.info("Validation passed.")
        return 0
    else:
        logger.error("Validation FAILED.")
        return 1


def cmd_search(args):
    """Search the registry by name/description."""
    query = args.query.lower()
    logger.info("Searching registries for '%s'...\n", args.query)

    results = []

    # Search official
    for entry in _fetch_registry():
        name = entry.get("name", "")
        desc = entry.get("description", "")
        if query in name.lower() or query in desc.lower():
            entry["_source"] = "official"
            results.append(entry)

    # Search community
    for entry in _fetch_community():
        name = entry.get("name", "")
        desc = entry.get("description", "")
        if query in name.lower() or query in desc.lower():
            entry["_source"] = "community"
            results.append(entry)

    if not results:
        logger.info("No skills found.")
        return 0

    installed_names = set()
    if SKILLS_DIR.is_dir():
        installed_names = {d.name for d in SKILLS_DIR.iterdir() if d.is_dir() and (d / "skill.yaml").exists()}

    print(f"{'Name':<20} {'Version':<10} {'Source':<12} {'Installed':<10} {'Description'}")
    print("-" * 90)
    for s in results:
        name = s.get("name", "unknown")
        version = s.get("version", "?")
        source = s.get("_source", "?")
        installed = "yes" if name in installed_names else ""
        desc = s.get("description", "")
        desc = (desc[:35] + "...") if len(desc) > 35 else desc
        print(f"{name:<20} {version:<10} {source:<12} {installed:<10} {desc}")

    print(f"\n{len(results)} result(s)")
    return 0


# ── Main ──────────────────────────────────────────────────────────────────


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser(
        prog="android-agent",
        description="Android Agent CLI -- manage skills, automation, and devices",
    )
    sub = parser.add_subparsers(dest="command", help="Available commands")

    # ── skill subcommand ──
    skill_parser = sub.add_parser("skill", help="Manage skills (install, list, update, remove, validate, search)")
    skill_sub = skill_parser.add_subparsers(dest="skill_command", help="Skill sub-commands")

    # install
    install_p = skill_sub.add_parser("install", help="Install a skill from registry, GitHub URL, or local path")
    install_p.add_argument("target", help="Skill name, GitHub URL, or local path")
    install_p.add_argument("--force", "-f", action="store_true", help="Install even if validation fails")

    # list
    skill_sub.add_parser("list", help="List installed skills")

    # update
    update_p = skill_sub.add_parser("update", help="Re-fetch the latest version of a skill")
    update_p.add_argument("name", help="Skill name to update")

    # remove
    remove_p = skill_sub.add_parser("remove", help="Remove an installed skill")
    remove_p.add_argument("name", help="Skill name to remove")
    remove_p.add_argument("--force", "-f", action="store_true", help="Remove even built-in skills")

    # validate
    validate_p = skill_sub.add_parser("validate", help="Validate a skill directory")
    validate_p.add_argument("path", help="Path to skill directory")

    # search
    search_p = skill_sub.add_parser("search", help="Search registry by name/description")
    search_p.add_argument("query", help="Search query")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "skill":
        if args.skill_command is None:
            skill_parser.print_help()
            return 0

        dispatch = {
            "install": cmd_install,
            "list": cmd_list,
            "update": cmd_update,
            "remove": cmd_remove,
            "validate": cmd_validate,
            "search": cmd_search,
        }
        handler = dispatch.get(args.skill_command)
        if handler:
            return handler(args)
        else:
            skill_parser.print_help()
            return 1

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
