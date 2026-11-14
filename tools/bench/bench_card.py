#!/usr/bin/env python3
"""Import one ab_report task into a display-only BenchCard v2, without running a model.

Tasks are replaced by task_id; historical void_arms and labelled_results survive.
Use --preserve-arms to enrich an existing card only if its published numbers agree.
Source trace paths are copied unchanged. Validity is preserved unless an explicit
ITT adjudication is supplied; its original flags are then retained as provenance.

Pro Expense: ab4 owns ExpenseAddMultiple arms and episodes, including its ab3
before/replay rows. Never mix pre-fix after_mcp rows into that task's episodes.
Import those separately with --labelled-result after_mcp_skill_bug_ab3; this
adds episodes to the existing finding without changing its numbers or ITT note.
The invalid seed-32 token-cap row stays invalid with its original reason.
The same historical separation applies to ExpenseAddSingle (ab4-single current,
ab3 labelled). --episodes-only retains published arms when source stats disagree
with their ITT policy; incompatible arm/paired stats are omitted, never substituted.
--itt-failure ARM:SEED explicitly counts a failed episode. --itt-counted-as can
adjudicate it valid with an explanation, retaining source_valid and
source_invalid_reason separately. Provenance is inferred from git history, not
a claim that these legacy runs were cryptographically bound to that revision.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ARMS = {"before", "after_mcp", "after_replay"}
LABEL = "maintainer-run, not independent"


def convert_task(report: dict, task_id: str, skill: str, action: str, label: str) -> dict:
    matches = [t for t in report["stats"]["tasks"] if t["task_id"] == task_id]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one stats task {task_id!r}, found {len(matches)}")
    stats = copy.deepcopy(matches[0])
    rows = copy.deepcopy(report["episodes"][task_id])
    for row in rows:
        if row.get("skill") is not None and row["skill"] != skill:
            raise ValueError(f"{task_id}: row skill {row['skill']!r} differs from --skill {skill!r}")
        if row.get("arm") not in ARMS:
            raise ValueError(f"{task_id}: unsupported episode arm {row.get('arm')!r}")
    arms = {}
    for arm in set(stats["arms"]) | {r["arm"] for r in rows if r.get("valid") is not False}:
        if arm not in ARMS or arm not in stats["arms"]:
            raise ValueError(f"{task_id}: missing or unsupported stats arm {arm!r}")
        data = stats["arms"][arm]
        valid = [r for r in rows if r["arm"] == arm and r.get("valid") is not False]
        passed = sum(r.get("pass") is True for r in valid)
        if (data["passed"], data["total"]) != (passed, len(valid)):
            raise ValueError(
                f"{task_id}/{arm}: stats {data['passed']}/{data['total']} "
                f"disagree with valid rows {passed}/{len(valid)}"
            )
        arms[arm] = {
            "passed": data["passed"],
            "total": data["total"],
            "wall_ms_median": data.get("wall_ms", {}).get("median"),
            "tokens_median": data.get("tokens", {}).get("median"),
        }
    return {
        "task_id": task_id,
        "action": action,
        "label": label,
        "seeds": len({r.get("seed") for r in rows}),
        "arms": dict(sorted(arms.items())),
        "episodes": rows,
        "stats": {k: v for k, v in stats.items() if k != "task_id"},
    }


def merge_card(
    existing: dict, task: dict, *, skill: str, suite: str, source: str, preserve_arms=False, episodes_only=False
) -> dict:
    """Return a new card; never mutate the caller's data or discard findings."""
    card = copy.deepcopy(existing)
    if card.get("skill", skill) != skill or card.get("suite", suite) != suite:
        raise ValueError("existing card skill/suite differs from requested destination")
    tasks = card.setdefault("tasks", [])
    old = next((t for t in tasks if t["task_id"] == task["task_id"]), {})
    task = copy.deepcopy(task)
    if episodes_only and not old.get("arms"):
        raise ValueError("--episodes-only requires existing published arms")
    if preserve_arms or episodes_only:
        incompatible = set()
        for arm, values in task["arms"].items():
            for key, value in values.items():
                previous = old.get("arms", {}).get(arm, {})
                if key in previous and previous[key] != value:
                    if not episodes_only:
                        raise ValueError(
                            f"{task['task_id']}/{arm}.{key}: existing {previous[key]!r} "
                            f"disagrees with source {value!r}; card unchanged"
                        )
                    incompatible.add(arm)
        if episodes_only:
            task["arms"] = copy.deepcopy(old["arms"])
            incompatible.update(set(task["stats"]["arms"]) - set(old["arms"]))
            task["stats"]["arms"] = {
                arm: values for arm, values in task["stats"]["arms"].items() if arm not in incompatible
            }
            task["stats"]["paired"] = {
                key: values
                for key, values in task["stats"].get("paired", {}).items()
                if not incompatible.intersection(key.split("_vs_"))
            }
        else:
            task["arms"] = {**task["arms"], **copy.deepcopy(old.get("arms", {}))}
    for key in ("void_arms", "labelled_results"):
        if key in old:
            task[key] = copy.deepcopy(old[key])
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    run_ids = set()
    for row in task["episodes"]:
        trace = row.get("trace") or ""
        match = re.search(r"(?:agent-arm|native-ab)/([^/]+)/", trace)
        if match:
            run_ids.add(match[1])
        if row.get("run_id"):
            run_ids.add(row["run_id"])
    if not run_ids:
        run_ids.add(Path(source).stem)
    task.update(source=source, generated_at=now, run_ids=sorted(run_ids))
    if old:
        tasks[tasks.index(old)] = task
    else:
        tasks.append(task)
    models = set()
    for t in tasks:
        for a in t.get("stats", {}).get("arms", {}).values():
            model = a.get("model")
            models.update(m for m in (model if isinstance(model, list) else [model]) if m)
    card.update(
        suite=suite,
        skill=skill,
        evidence_class="maintainer",
        label=LABEL,
        model=sorted(models),
        generated_at=now,
        source=source,
        run_ids=sorted({run for t in tasks for run in t.get("run_ids", [])}),
    )
    return card


def merge_labelled_result(existing: dict, task: dict, key: str, arm: str) -> dict:
    """Attach source rows to an existing finding, leaving current results intact."""
    card = copy.deepcopy(existing)
    old = next((t for t in card["tasks"] if t["task_id"] == task["task_id"]), None)
    if old is None or key not in old.get("labelled_results", {}):
        raise ValueError(f"{task['task_id']}: no existing labelled_results entry {key!r}")
    rows = [r for r in task["episodes"] if r["arm"] == arm]
    if not rows:
        raise ValueError(f"{task['task_id']}: no episodes for labelled arm {arm!r}")
    old["labelled_results"][key]["episodes"] = copy.deepcopy(rows)
    return card


def add_skill_provenance(task: dict, skill_sha: str, skill_version: str) -> None:
    """Stamp current, void and labelled rows; a published concrete arm SHA wins.

    Callers obtain the default version from skill.yaml at the supplied commit.
    Existing per-arm versions win when present; legacy 'pre-<sha>' placeholders
    are resolved to the caller's concrete pre-fix revision.
    """
    for section in ("arms", "void_arms", "labelled_results"):
        for arm, result in task.get(section, {}).items():
            sha = result.get("skill_sha")
            result["skill_sha"] = sha if sha and not sha.startswith("pre-") else skill_sha
            result.setdefault("skill_version", skill_version)
            rows = (
                result.get("episodes", [])
                if section != "arms"
                else [r for r in task.get("episodes", []) if r["arm"] == arm]
            )
            for row in rows:
                row["skill_sha"] = result["skill_sha"]
                row["skill_version"] = result["skill_version"]
            if section == "arms" and arm in task.get("stats", {}).get("arms", {}):
                task["stats"]["arms"][arm].update(skill_sha=result["skill_sha"], skill_version=result["skill_version"])


def mark_itt_failure(task: dict, selection: str, counted_as: str | None = None) -> None:
    """Count an explicitly adjudicated failure while retaining source validity."""
    matches = [r for r in task["episodes"] if f"{r['arm']}:{r.get('seed')}" == selection]
    if len(matches) != 1 or matches[0].get("pass") is not False:
        raise ValueError(f"ITT failure {selection!r} must select exactly one failed episode")
    matches[0].update(counted=True, counting_rule="intention-to-treat")
    if counted_as:
        row = matches[0]
        row["source_valid"] = row.get("valid", True)
        if "invalid_reason" in row:
            row["source_invalid_reason"] = row.pop("invalid_reason")
        row.update(valid=True, counted_as=counted_as)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--task", required=True)
    parser.add_argument("--skill", required=True)
    parser.add_argument("--suite", required=True)
    parser.add_argument("--action", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--preserve-arms", action="store_true", help="Refuse any change to existing arm numbers")
    parser.add_argument(
        "--episodes-only", action="store_true", help="Keep published arms; omit incompatible source stats"
    )
    parser.add_argument("--itt-failure", action="append", default=[], metavar="ARM:SEED")
    parser.add_argument("--itt-counted-as", help="Adjudicate selected ITT failures valid and record this explanation")
    parser.add_argument("--skill-sha", help="Concrete default skill revision inferred from run history")
    parser.add_argument("--skill-version", help="Version from skill.yaml at --skill-sha")
    parser.add_argument(
        "--labelled-result", help="Attach episodes to this existing finding instead of replacing the task"
    )
    parser.add_argument("--labelled-arm", choices=sorted(ARMS), default="after_mcp")
    args = parser.parse_args(argv)
    if bool(args.skill_sha) != bool(args.skill_version):
        parser.error("--skill-sha and --skill-version must be supplied together")
    if args.itt_counted_as and not args.itt_failure:
        parser.error("--itt-counted-as requires --itt-failure")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*/[a-z0-9][a-z0-9_-]*", args.skill):
        parser.error("--skill must be author/slug")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", args.suite):
        parser.error("--suite must be a filename-safe suite name")
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", args.action):
        parser.error("--action must be an action name")
    try:
        report = json.loads(args.report.read_text())
        task = convert_task(report, args.task, args.skill, args.action, args.label)
        for selection in args.itt_failure:
            mark_itt_failure(task, selection, args.itt_counted_as)
        dest = Path("skillhub") / args.skill / "bench" / f"{args.suite}.json"
        existing = json.loads(dest.read_text()) if dest.exists() else {}
        if args.labelled_result:
            if existing.get("skill") != args.skill or existing.get("suite") != args.suite:
                raise ValueError("existing card skill/suite differs from requested destination")
            card = merge_labelled_result(existing, task, args.labelled_result, args.labelled_arm)
        else:
            card = merge_card(
                existing,
                task,
                skill=args.skill,
                suite=args.suite,
                source=args.report.as_posix(),
                preserve_arms=args.preserve_arms,
                episodes_only=args.episodes_only,
            )
        if args.skill_sha:
            updated = next(t for t in card["tasks"] if t["task_id"] == args.task)
            add_skill_provenance(updated, args.skill_sha, args.skill_version)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(card, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    print(dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
