#!/usr/bin/env python3
"""Build index.json from all registry/*/skill.yaml files.

Usage:
    python scripts/build_index.py

Walks the registry/ directory, parses each skill.yaml, and generates
a sorted index.json manifest at the repo root.
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY_DIR = REPO_ROOT / "registry"
OUTPUT_FILE = REPO_ROOT / "index.json"


def count_elements(skill_dir: Path) -> int:
    """Count the number of UI elements defined in elements.yaml."""
    elements_path = skill_dir / "elements.yaml"
    if not elements_path.exists():
        return 0
    try:
        data = yaml.safe_load(elements_path.read_text())
        if not isinstance(data, dict):
            return 0
        # Count top-level keys that are element definitions
        # (exclude metadata keys like 'package')
        skip_keys = {"package", "elements"}
        if "elements" in data and isinstance(data["elements"], dict):
            return len(data["elements"])
        return sum(1 for k in data if k not in skip_keys)
    except Exception:
        return 0


def parse_skill(skill_dir: Path) -> dict | None:
    """Parse a skill.yaml and return index entry, or None on failure."""
    skill_path = skill_dir / "skill.yaml"
    if not skill_path.exists():
        print(f"  SKIP {skill_dir.name}: no skill.yaml")
        return None

    try:
        data = yaml.safe_load(skill_path.read_text())
    except yaml.YAMLError as e:
        print(f"  ERROR {skill_dir.name}: invalid YAML — {e}")
        return None

    if not isinstance(data, dict):
        print(f"  ERROR {skill_dir.name}: skill.yaml is not a mapping")
        return None

    name = data.get("name", skill_dir.name)

    # Extract actions list
    exports = data.get("exports", {})
    actions_raw = exports.get("actions", [])
    actions = []
    for a in actions_raw:
        if isinstance(a, dict):
            actions.append(a.get("name", str(a)))
        else:
            actions.append(str(a))

    # Extract workflows list
    workflows_raw = exports.get("workflows", [])
    workflows = []
    for w in workflows_raw:
        if isinstance(w, dict):
            workflows.append(w.get("name", str(w)))
        else:
            workflows.append(str(w))

    # Count elements
    elements_count = count_elements(skill_dir)

    # Tested on
    tested_on = data.get("tested_on", [])

    entry = {
        "name": name,
        "display_name": data.get("display_name", name.replace("_", " ").replace("-", " ").title()),
        "description": data.get("description", ""),
        "version": data.get("version", "0.0.0"),
        "app_package": data.get("app_package"),
        "author": data.get("author", "unknown"),
        "license": data.get("license", "MIT"),
        "actions": actions,
        "workflows": workflows,
        "elements_count": elements_count,
        "tested_on": tested_on,
        "source": "official",
        "repo_url": f"https://github.com/C-K-Loan/android-agent-skills/tree/main/registry/{skill_dir.name}",
        "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    return entry


def main():
    if not REGISTRY_DIR.exists():
        print(f"ERROR: registry directory not found at {REGISTRY_DIR}")
        sys.exit(1)

    print(f"Scanning {REGISTRY_DIR} ...")
    entries = []

    for skill_dir in sorted(REGISTRY_DIR.iterdir()):
        if not skill_dir.is_dir():
            continue
        if skill_dir.name.startswith("."):
            continue

        entry = parse_skill(skill_dir)
        if entry:
            entries.append(entry)
            action_count = len(entry["actions"])
            workflow_count = len(entry["workflows"])
            print(f"  OK {entry['name']}: {action_count} actions, {workflow_count} workflows, {entry['elements_count']} elements")

    # Sort by name
    entries.sort(key=lambda e: e["name"])

    # Write index.json
    index = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "skill_count": len(entries),
        "total_actions": sum(len(e["actions"]) for e in entries),
        "total_workflows": sum(len(e["workflows"]) for e in entries),
        "skills": entries,
    }

    OUTPUT_FILE.write_text(json.dumps(index, indent=2) + "\n")
    print(f"\nWrote {OUTPUT_FILE} — {len(entries)} skills, {index['total_actions']} actions, {index['total_workflows']} workflows")


if __name__ == "__main__":
    main()
