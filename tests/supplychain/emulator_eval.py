"""Harmless live companion to the frozen device-free corpus.

Run only on an explicitly allocated emulator. This calls the production CI
fingerprint preflight and real skill engine, without installing fixture skills
in a registry. It does not run the hosted workflow or create verifier credit.
"""

from __future__ import annotations

import argparse
import json
import platform
import re
import subprocess
from pathlib import Path

import yaml

from gitd.skills.engine.errors import ValidatorFailedError
from gitd.skills.engine.evidence import collect_fingerprint
from gitd.skills.engine.loader import load_skill
from gitd.skills.engine.runner import run_action
from tools.ci.emulator_actions import mismatch

CASES = (
    ("benign-calculator", "org.fossify.math", "1.4.0", "org.fossify.math", "pass"),
    ("wrong-app-replay", "org.fossify.math", "1.4.0", "com.android.settings", "caught_validator"),
    ("stale-app-fingerprint", "org.fossify.math", "2.0.0", "org.fossify.math", "caught_preflight"),
    ("missing-target-app", "org.example.supplychain.missing", "1.0.0", "org.fossify.math", "caught_preflight"),
)


def manifest(name, package, version, launch):
    return {
        "name": name,
        "author": "supplychain-eval",
        "version": "1.0.0",
        "description": "Harmless synthetic live supply-chain replay probe",
        "license": "MIT",
        "generated_with": "human synthetic security evaluation",
        "skill_class": "hard",
        "data_access": [],
        "side_effects": ["none"],
        "fingerprint": {
            "os": "android",
            "os_version": "13",
            "hardware": "*",
            "app_package": package,
            "app_version": version,
        },
        "actions": [
            {
                "name": "open",
                "description": "Open the target app",
                "ref_prompt": "Open the calculator",
                "steps": [{"action": "launch_app", "package": launch}, {"action": "sleep", "duration_s": 1}],
                "end_state_validator": [{"kind": "element_present", "id": "org.fossify.math:id/result"}],
            }
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true", help="Confirm an emulator window has been allocated")
    args = parser.parse_args()
    if not args.execute or not re.fullmatch(r"[0-9a-f]{40}", args.source_sha):
        parser.error("--execute and a full source SHA are required")
    qemu = subprocess.check_output(
        ["adb", "-s", args.device, "shell", "getprop", "ro.kernel.qemu"], text=True, timeout=15
    ).strip()
    if qemu != "1":
        parser.error("This experiment is restricted to an emulator")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    result = {
        "source_sha": args.source_sha,
        "python": platform.python_version(),
        "pyyaml": yaml.__version__,
        "emulator": True,
        "scope": "local CI preflight + real engine; no hosted CI or independent verifier",
        "signatures": "none; these measurements earn no registry evidence credit",
        "cases": [],
    }

    def save():
        (output / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")

    save()
    for name, package, version, launch, expected in CASES:
        directory = output / "fixtures" / name
        directory.mkdir(parents=True, exist_ok=True)
        raw = manifest(name, package, version, launch)
        (directory / "skill.yaml").write_text(yaml.safe_dump(raw, sort_keys=False))
        skill = load_skill(directory)
        row = {
            "id": name,
            "expected": expected,
            "declared_fingerprint": raw["fingerprint"],
            "launch_package": launch,
            "outcome": "error",
            "executed": False,
        }
        result["cases"].append(row)
        save()
        try:
            fingerprint = collect_fingerprint(skill, args.device)
            row["observed_fingerprint"] = fingerprint
            reason = mismatch(raw["fingerprint"], fingerprint)
            row["preflight_reason"] = reason
            if reason:
                row["outcome"] = "caught_preflight"
            else:
                row["executed"] = True
                run = run_action(skill, "open", device_serial=args.device)
                row["run"] = run.as_dict()
                row["outcome"] = (
                    "pass"
                    if run.success
                    else (
                        "caught_validator"
                        if (run.error or {}).get("kind") == ValidatorFailedError.__name__
                        else "error"
                    )
                )
                screenshot = subprocess.run(
                    ["adb", "-s", args.device, "exec-out", "screencap", "-p"], capture_output=True, timeout=20
                )
                row["screenshot_exit"] = screenshot.returncode
                if screenshot.returncode == 0:
                    (output / f"{name}.png").write_bytes(screenshot.stdout)
        except ValueError as exc:
            row["preflight_reason"] = str(exc)
            # A missing target is a concrete CI preflight skip, never an executed pass.
            if str(exc).startswith("Cannot determine installed app version:"):
                row["outcome"] = "caught_preflight"
            else:
                row["error"] = str(exc)
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            row["error"] = str(exc)
        row["matches_expected"] = row["outcome"] == expected
        save()
        print(json.dumps({k: row[k] for k in ("id", "outcome", "executed", "matches_expected")}), flush=True)
    result["summary"] = {
        "cases": len(result["cases"]),
        "matched": sum(row["matches_expected"] for row in result["cases"]),
        "executed": sum(row["executed"] for row in result["cases"]),
    }
    save()
    return 0 if all(row["matches_expected"] for row in result["cases"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
