#!/usr/bin/env python3
"""Pool every declared showcase task's current before/after_mcp arms (never findings).

Marginals use published arms. Pairing uses (skill, task, seed) and valid current
rows. Adjudicated ITT failures are valid:true/pass:false with counted_as metadata.
Missing tasks, duplicate declarations/episodes and count mismatches are errors.
"""

from __future__ import annotations

import argparse
import json
from math import comb
from pathlib import Path

import yaml


def pooled_headline(manifest: Path) -> dict:
    totals = {arm: {"passed": 0, "total": 0} for arm in ("before", "after_mcp")}
    pairs = favor = against = 0
    seen = set()
    models = set()
    entries = yaml.safe_load(manifest.read_text())["skills"]
    for ref, task_id in ((entry["ref"], task) for entry in entries for task in entry["task_ids"]):
        identity = (ref, task_id)
        if identity in seen:
            raise ValueError(f"duplicate showcase task: {identity}")
        seen.add(identity)
        matches = [
            task
            for file in sorted((manifest.parent / ref / "bench").glob("*.json"))
            for task in json.loads(file.read_text()).get("tasks", [])
            if task["task_id"] == task_id
        ]
        if len(matches) != 1:
            raise ValueError(f"{identity}: expected one bench task, found {len(matches)}")
        task = matches[0]
        by_arm = {}
        for arm in totals:
            result = task["arms"][arm]
            if result.get("valid") is False:
                raise ValueError(f"{identity}/{arm}: published arm is void")
            episodes = {}
            for row in task.get("episodes", []):
                if row["arm"] != arm:
                    continue
                if row.get("valid") is False:
                    continue
                seed = row["seed"]
                if seed in episodes:
                    raise ValueError(f"{identity}/{arm}: duplicate seed {seed}")
                episodes[seed] = row.get("pass") is True
                if row.get("model"):
                    models.add(row["model"])
            if (sum(episodes.values()), len(episodes)) != (result["passed"], result["total"]):
                raise ValueError(f"{identity}/{arm}: counted episodes disagree with published arm")
            by_arm[arm] = episodes
            for key in ("passed", "total"):
                totals[arm][key] += result[key]
        for seed in by_arm["before"].keys() & by_arm["after_mcp"].keys():
            before, after = by_arm["before"][seed], by_arm["after_mcp"][seed]
            pairs += 1
            favor += after and not before
            against += before and not after
    discordant = favor + against
    p_value = min(1.0, 2 * sum(comb(discordant, k) for k in range(min(favor, against) + 1)) / 2**discordant)
    return {
        "label": "maintainer-run, not independent",
        "model": sorted(models),
        "tasks": len(seen),
        **totals,
        "paired": {"pairs": pairs, "for_skill": favor, "against_skill": against, "mcnemar_exact_p": p_value},
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, nargs="?", default=Path("skillhub/showcase.yml"))
    args = parser.parse_args(argv)
    try:
        result = pooled_headline(args.manifest)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
