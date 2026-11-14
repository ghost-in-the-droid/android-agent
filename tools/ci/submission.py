"""Detect and check changed skill directories without a device or credentials."""

import argparse
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import yaml

from tools.ci.common import changed_paths, changed_skills, submission_scope
from tools.ci.verify_evidence import only_verifications

SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$")


def semver(value):
    match = SEMVER.fullmatch(str(value))
    if not match:
        raise ValueError(f"Invalid SemVer: {value}")
    major, minor, patch, pre = match.groups()
    prerelease = []
    if pre is not None:
        for part in pre.split("."):
            if not part or (part.isdigit() and len(part) > 1 and part.startswith("0")):
                raise ValueError(f"Invalid SemVer: {value}")
            prerelease.append((0, int(part)) if part.isdigit() else (1, part))
    return (int(major), int(minor), int(patch), pre is None, tuple(prerelease))


def version_increased(current, previous):
    return semver(current) > semver(previous)


SIGNAL_KEYS = {
    "manifest_valid",
    "static_scan_clean",
    "readme",
    "soft_md",
    "demo",
    "demo_all_actions",
    "before_after",
    "bench",
    "failure_modes",
    "validators",
    "validators_static",
    "validators_total",
    "bench_models",
    "fingerprints_verified",
    "tests_pass",
    "last_verified",
}
_HERE = Path(__file__).resolve().parent


def quality_signals(path, metadata):
    """The registry's own document signals (tools/build_registry.doc_signals via tools/ci/skill_signals.py),
    computed in the sandbox from the trusted tools copy so the comment matches the post-merge registry.
    Falls back to the minimal file checks when the helper cannot run."""
    script = (
        "/ci/tools/ci/skill_signals.py" if os.environ.get("GHOST_CI_SANDBOX_IMAGE") else str(_HERE / "skill_signals.py")
    )
    outcome = run_check(["python3", script, str(path)])
    try:
        if outcome.get("exit_code") != 0:
            raise ValueError(outcome.get("output", ""))
        first = outcome["output"].strip().splitlines()[-1]
        signals = json.loads(first)
        if not isinstance(signals, dict) or set(signals) - SIGNAL_KEYS:
            raise ValueError("unexpected signal fields")
    except (ValueError, KeyError, IndexError):
        fingerprint = metadata.get("fingerprint", {})
        signals = {
            "readme": (path / "README.md").is_file(),
            "soft_md": (path / "SOFT.md").is_file(),
            "demo": any((path / n).is_file() for n in ("demo.webm", "demo.mp4", "demo.gif")),
            "bench": (path / "bench.yaml").is_file(),
            "fingerprints_verified": len(fingerprint) if isinstance(fingerprint, list) else int(bool(fingerprint)),
        }
    signals.setdefault("tests_pass", None)
    signals.setdefault("last_verified", None)
    return signals


def run_check(command, *, soft=False, optional=False):
    image = os.environ.get("GHOST_CI_SANDBOX_IMAGE")
    if image:
        tools = os.environ.get("GHOST_CI_TOOLS")  # trusted base-branch tools copy, mounted read-only at /ci
        command = [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,size=64m",
            "--workdir",
            "/workspace",
            "--volume",
            f"{Path.cwd()}:/workspace:ro",
            *(["--volume", f"{tools}:/ci:ro"] if tools else []),
            image,
            *command,
        ]
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "warning" if soft or optional else "fail", "output": str(exc)}
    output = (proc.stdout + proc.stderr)[-16000:]
    missing = bool(
        re.search(
            r"invalid choice|no such command|unknown (?:skill )?(?:sub)?command|unrecognized arguments", output, re.I
        )
    )
    status = "pass" if proc.returncode == 0 else "warning" if soft or (optional and missing) else "fail"
    return {"status": status, "exit_code": proc.returncode, "output": output, "missing_subcommand": missing}


def check_skill(path, base, actor, maintainer=False):
    path = Path(path)
    result = {"skill": path.as_posix(), "checks": {}, "signals": {}, "labels": ["skill-submission"]}
    checks = result["checks"]
    author = path.parts[1]
    changes = [name for name in changed_paths(base) if name.startswith(path.as_posix() + "/")]
    evidence_only = only_verifications(changes) and all(Path(name).is_file() for name in changes)
    checks["ownership"] = {
        "status": "pass"
        if evidence_only or (actor.lower() == author.lower() and author.lower() != "ghost") or maintainer
        else "fail"
    }
    if not path.exists():
        checks["deleted"] = {"status": "pass", "output": "Skill removed"}
        return result
    try:
        metadata = yaml.safe_load((path / "skill.yaml").read_text())
        if not isinstance(metadata, dict):
            raise ValueError("skill.yaml must be a mapping")
        result["signals"] = quality_signals(path, metadata)
        if metadata.get("skill_class") == "soft":
            result["labels"].append("soft-skill")
        if any(path.rglob("*.py")):
            result["labels"].append("has-python")
        size = sum(p.stat().st_size for p in path.rglob("*") if p.is_file())
        result["labels"].append("size/" + ("small" if size < 50_000 else "medium" if size < 500_000 else "large"))
        semver(metadata.get("version"))
        previous = subprocess.run(
            ["git", "show", f"{base}:{path.as_posix()}/skill.yaml"], capture_output=True, text=True
        )
        if previous.returncode == 0 and not evidence_only:
            old = yaml.safe_load(previous.stdout)
            if not version_increased(metadata["version"], old["version"]):
                raise ValueError("Existing skills require a SemVer version increase")
        checks["version"] = {"status": "pass"}
    except (OSError, ValueError, KeyError, yaml.YAMLError) as exc:
        checks["version"] = {"status": "fail", "output": str(exc)}
    for command in ("validate", "analyze", "lint", "test"):
        checks[command] = run_check(
            ["ghost", "skill", command, str(path)], soft=command == "lint", optional=command in ("analyze", "lint")
        )
    analysis = checks["analyze"]
    # Analyzer contract: exit 2 means high. Exit 1 or medium findings require review.
    if not analysis.get("missing_subcommand") and (
        analysis.get("exit_code") == 2 or re.search(r"\b(high|medium)\b", analysis.get("output", ""), re.I)
    ):
        result["labels"].append("needs-security-review")
    if analysis.get("exit_code") == 1 and not analysis.get("missing_subcommand"):
        analysis["status"] = "warning"
        result["labels"].append("needs-security-review")
    if result["signals"].get("static_scan_clean") is False:
        analysis["status"] = "fail"
        analysis["output"] = (
            analysis.get("output", "") + "\nShared static scan rejected the skill or could not complete."
        )
        if "needs-security-review" not in result["labels"]:
            result["labels"].append("needs-security-review")
    for name, command in [
        ("bandit", ["bandit", "-q", "-r", str(path)]),
        ("semgrep", ["semgrep", "--config", "p/python", str(path)]),
    ]:
        checks[name] = (
            run_check(command, soft=True)
            if shutil.which(name) or (os.environ.get("GHOST_CI_SANDBOX_IMAGE") and name == "bandit")
            else {"status": "warning", "output": f"{name} unavailable"}
        )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["detect", "check"])
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--path")
    parser.add_argument("--actor", default="")
    parser.add_argument("--maintainer", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args()
    if args.mode == "detect":
        submission_scope(changed_paths(args.base, args.head))
        print(json.dumps({"skill": changed_skills(args.base, args.head)}))
        return 0
    result = check_skill(args.path, args.base, args.actor, args.maintainer)
    for check in result["checks"].values():
        if "output" in check:
            check["output"] = (
                re.sub(r"[\x00-\x08\x0b-\x1f]", " ", check["output"])
                .replace("<", "less than ")
                .replace(">", "greater than ")[:16000]
            )
    Path(args.output).write_text(json.dumps(result, indent=2))
    return int(any(c["status"] == "fail" for c in result["checks"].values()))


if __name__ == "__main__":
    raise SystemExit(main())
