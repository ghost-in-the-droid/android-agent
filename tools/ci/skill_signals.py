#!/usr/bin/env python3
"""Print the registry's document signals for one skill dir as JSON (used by submission.py).

Runs inside the CI sandbox from the trusted base-branch copy of tools/ (mounted at /ci), so the
sticky comment shows exactly what tools/build_registry.py will compute after the merge: per-action
demos, failure modes, validators and bench files included.
"""

import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # <copy>/tools: build_registry + quality

from build_registry import doc_signals  # noqa: E402


def ci_signals(skill_dir: Path, raw: dict) -> dict:
    """doc_signals flattened for the PR comment: ``validators_static`` is the weakest action's units from the
    YAML alone (the registry awards validators only on actions with a passing current run)."""
    signals = doc_signals(skill_dir, raw)
    # Unknown scan results must not become a passing submission signal.
    signals["static_scan_clean"] = signals.get("static_scan_clean") is True
    units = signals.pop("validator_units", {}) or {}
    signals.pop("status", None)
    signals["validators_static"] = min(units.values()) if units else 0
    return signals


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("usage: skill_signals.py <skill_dir>", file=sys.stderr)
        return 2
    skill_dir = Path(argv[0])
    raw = yaml.safe_load((skill_dir / "skill.yaml").read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SystemExit("skill.yaml must be a mapping")
    print(json.dumps(ci_signals(skill_dir, raw), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
