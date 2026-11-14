#!/usr/bin/env python3
"""Aggregate A/B episode cells (agent_arm.py / native_ab.py ``*.cell.json``) into stats and v2 episode rows.

Per task and arm: passed/total with a Wilson 95% interval, median and IQR of tokens, wall-clock, LLM calls
and UI actions. Per task, paired on seed: exact McNemar (two-sided) of each arm against ``before``,
median tokens saved per episode, and the break-even reuse count when the skill's authoring tokens are
given. Episode rows follow the BenchCard v2 shape used by the hub site (``actions[]``, ``calls[]``
read back from the transcript). Numbers come only from the cell files passed in.

Example:
    python3 tools/bench/ab_report.py bench-out/agent-arm/ab1/*.cell.json --out bench-out/ab/ab1.json
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

ACTION_TYPES = {
    "tap": "tap",
    "tap_element": "tap",
    "long_press": "tap",
    "type_text": "type",
    "paste_text": "type",
    "swipe": "swipe",
    "scroll": "swipe",
    "press_back": "key",
    "press_home": "key",
    "press_key": "key",
    "launch_app": "launch",
    "launch_intent": "launch",
    "open_url": "launch",
    "force_stop": "launch",
    "wait": "wait",
    "run_skill": "skill",
    "run_action": "skill",
    "run_workflow": "skill",
    "run_flow": "flow",
    "find_skill": "skill",
}


def wilson(passed: int, total: int, z: float = 1.959964) -> tuple[float, float]:
    if total == 0:
        return (0.0, 0.0)
    p = passed / total
    denom = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denom
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denom
    return (round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4))


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p from the discordant pairs (b: only A passed, c: only B passed)."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2**n
    return round(min(1.0, 2 * tail), 6)


def spread(values: list[float]) -> dict:
    if not values:
        return {"median": None, "q1": None, "q3": None, "n": 0}
    ordered = sorted(values)
    if len(ordered) == 1:
        return {"median": ordered[0], "q1": ordered[0], "q3": ordered[0], "n": 1}
    q1, med, q3 = statistics.quantiles(ordered, n=4, method="inclusive")
    return {"median": med, "q1": q1, "q3": q3, "n": len(ordered)}


def transcript_rows(path: Path) -> tuple[list[dict], list[dict]]:
    """``actions[]`` (one per tool call, ok from its result) and ``calls[]`` (one per API response)."""
    actions, calls, pending, usage_by_id = [], [], {}, {}
    if not path.exists():
        return actions, calls
    for line in path.read_text().splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        message = event.get("message") or {} if isinstance(event, dict) else {}
        if event.get("type") == "assistant":
            if message.get("id"):
                usage_by_id[message["id"]] = message.get("usage") or {}
            for block in message.get("content") or []:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    tool = str(block.get("name", "")).split("__")[-1]
                    row = {"i": len(actions) + 1, "type": ACTION_TYPES.get(tool, "read"), "tool": tool, "ok": None}
                    target = (
                        (block.get("input") or {}).get("text")
                        or (block.get("input") or {}).get("package")
                        or (block.get("input") or {}).get("action")
                    )
                    if target:
                        row["target"] = str(target)[:60]
                    pending[block.get("id")] = row
                    actions.append(row)
        elif event.get("type") == "user":
            for block in message.get("content") or []:
                if (
                    isinstance(block, dict)
                    and block.get("type") == "tool_result"
                    and block.get("tool_use_id") in pending
                ):
                    text = (
                        block.get("content")
                        if isinstance(block.get("content"), str)
                        else json.dumps(block.get("content"))[:400]
                    )
                    failed = (
                        bool(block.get("is_error"))
                        or '"result":"ERROR' in text.replace(" ", "")
                        or '"result":"FAILED' in text.replace(" ", "")
                        or text.startswith(("ERROR", "FAILED"))
                    )
                    pending[block["tool_use_id"]]["ok"] = not failed
    for i, usage in enumerate(usage_by_id.values(), 1):
        calls.append(
            {
                "i": i,
                "tokens_in": int(usage.get("input_tokens") or 0) + int(usage.get("cache_creation_input_tokens") or 0),
                # the stream carries only the first chunk's output count; the episode total is exact
                "tokens_out": None,
                "tokens_cache_read": int(usage.get("cache_read_input_tokens") or 0),
            }
        )
    return actions, calls


def episode_row(cell: dict) -> dict:
    breakdown = cell.get("token_breakdown") or {}
    row = {
        "arm": cell["arm"],
        "seed": cell["seed"],
        "instance_seed": cell.get("instance_seed"),
        "model": cell.get("model"),
        "pass": bool(cell.get("success")),
        "tokens": int(cell.get("tokens") or 0),
        "tokens_in": int(breakdown.get("input_tokens", 0)) + int(breakdown.get("cache_creation_input_tokens", 0)),
        "tokens_out": int(breakdown.get("output_tokens", 0)),
        "tokens_cache_read": int(breakdown.get("cache_read_input_tokens", 0)),
        "wall_ms": int(cell.get("wall_ms") or 0),
        "steps": int(cell.get("steps") or 0),
        "llm_calls": int(cell.get("llm_calls") or 0),
        "ui_actions": cell.get("ui_actions") or {},
        "skill_calls": len(cell.get("skill_calls") or []),
        "tool_errors": int(cell.get("tool_errors") or 0),
        "valid": "error" not in cell or not cell.get("error"),
        "trace": cell.get("transcript"),
    }
    if not row["valid"]:
        row["invalid_reason"] = cell.get("error")
    if cell.get("transcript"):
        row["actions"], row["calls"] = transcript_rows(REPO / cell["transcript"])
    else:
        row["actions"], row["calls"] = [], []
    return row


def aggregate(cells: list[dict], authoring_tokens: int | None = None) -> dict:
    by_task: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for cell in cells:
        if cell.get("error"):
            continue  # cut-short episodes are listed in episodes, never counted
        by_task[cell["task_id"]][cell["arm"]].append(cell)
    report = {"tasks": []}
    for task, arms in sorted(by_task.items()):
        entry = {"task_id": task, "arms": {}, "paired": {}}
        for arm, arm_cells in sorted(arms.items()):
            passed = sum(1 for c in arm_cells if c.get("success"))
            entry["arms"][arm] = {
                "passed": passed,
                "total": len(arm_cells),
                "wilson95": wilson(passed, len(arm_cells)),
                "model": sorted({str(c.get("model")) for c in arm_cells if c.get("model")}) or None,
                "tokens": spread([c.get("tokens") or 0 for c in arm_cells]),
                "wall_ms": spread([c.get("wall_ms") or 0 for c in arm_cells]),
                "llm_calls": spread([c.get("llm_calls") or 0 for c in arm_cells]),
                "ui_actions": spread([(c.get("ui_actions") or {}).get("total", 0) for c in arm_cells]),
                "tool_errors": sum(int(c.get("tool_errors") or 0) for c in arm_cells),
                "seeds": sorted(c["seed"] for c in arm_cells),
            }
        base = {c["seed"]: c for c in arms.get("before", [])}
        for arm, arm_cells in arms.items():
            if arm == "before" or not base:
                continue
            pairs = [(base[c["seed"]], c) for c in arm_cells if c["seed"] in base]
            only_before = sum(1 for b, a in pairs if b.get("success") and not a.get("success"))
            only_after = sum(1 for b, a in pairs if a.get("success") and not b.get("success"))
            saved = [int(b.get("tokens") or 0) - int(a.get("tokens") or 0) for b, a in pairs]
            med_saved = statistics.median(saved) if saved else None
            entry["paired"][f"{arm}_vs_before"] = {
                "pairs": len(pairs),
                "only_before_passed": only_before,
                "only_after_passed": only_after,
                "mcnemar_exact_p": mcnemar_exact(only_before, only_after),
                "tokens_saved_median": med_saved,
                "break_even_reuses": (
                    math.ceil(authoring_tokens / med_saved)
                    if authoring_tokens and med_saved and med_saved > 0
                    else None
                ),
            }
        report["tasks"].append(entry)
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cells", nargs="+")
    ap.add_argument("--authoring-tokens", type=int, help="Tokens spent writing the skill, for break-even")
    ap.add_argument("--out", help="Write {stats, episodes} JSON here")
    args = ap.parse_args(argv)
    cells = [json.loads(Path(p).read_text()) for p in args.cells]
    stats = aggregate(cells, args.authoring_tokens)
    episodes = defaultdict(list)
    for cell in sorted(cells, key=lambda c: (c["task_id"], c["seed"], c["arm"])):
        episodes[cell["task_id"]].append(episode_row(cell))
    doc = {"stats": stats, "episodes": dict(episodes)}
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(doc, indent=2) + "\n")
    for task in stats["tasks"]:
        print(f"== {task['task_id']}")
        for arm, a in task["arms"].items():
            print(
                f"  {arm:13s} {a['passed']}/{a['total']} CI{a['wilson95']} tokens_med={a['tokens']['median']} "
                f"llm_calls_med={a['llm_calls']['median']} ui_med={a['ui_actions']['median']} wall_med={a['wall_ms']['median']}"
            )
        for name, p in task["paired"].items():
            print(
                f"  {name}: pairs={p['pairs']} b={p['only_before_passed']} c={p['only_after_passed']} "
                f"p={p['mcnemar_exact_p']} tokens_saved_med={p['tokens_saved_median']} break_even={p['break_even_reuses']}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
