#!/usr/bin/env python3
"""Hand-written mutation pass over the skill engine runner and validators.

Each mutant is (id, file, exact original snippet, replacement, note). The
snippet must occur exactly once in the file. For every mutant the script:

1. works in a throwaway copy of the tracked tree (never in the checkout),
2. applies the replacement,
3. runs the engine tests,
4. records killed (tests fail) or survived (tests pass),
5. restores the original file in the copy.

A baseline run on the unmutated copy must pass first, otherwise the result
would be meaningless and the script exits 2.

Usage:
    python3 tools/mutants.py [--tests 'tests/test_skill_*'] [--only R1,V3] [--json out.json]

Exit code: 0 always after a valid run (survivors are reported, not fatal),
2 on a broken baseline or a mutant snippet that no longer matches.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RUNNER = "gitd/skills/engine/runner.py"
VALIDATORS = "gitd/skills/engine/validators.py"

MUTANTS: list[tuple[str, str, str, str, str]] = [
    # ── runner.py ────────────────────────────────────────────────────────────
    (
        "R1",
        RUNNER,
        "            if not passed:\n",
        "            if passed:\n",
        "invert the end_state_validator pass check",
    ),
    (
        "R2",
        RUNNER,
        "        if action.end_state_validator:\n",
        "        if False:\n",
        "skip the end_state_validator entirely",
    ),
    ("R3", RUNNER, 'ctx.result["dry_run"] = True', 'ctx.result["dry_run"] = False', "dry-run result no longer flagged"),
    ("R4", RUNNER, "    if unknown:\n", "    if False:\n", "accept unknown params silently"),
    ("R5", RUNNER, "        elif p.required:\n", "        elif False:\n", "missing required param no longer an error"),
    (
        "R6",
        RUNNER,
        "if p.values and val not in p.values:",
        "if p.values and val in p.values:",
        "invert enum membership check",
    ),
    (
        "R7",
        RUNNER,
        'return v.lower() in {"true", "yes", "1", "on"}',
        'return v.lower() not in {"true", "yes", "1", "on"}',
        "invert string-to-bool coercion",
    ),
    (
        "R8",
        RUNNER,
        'if ctx.extras.get("_dry_run") and "checkpoint" not in step and "ask" not in step:',
        'if ctx.extras.get("_dry_run") and "checkpoint" in step and "ask" not in step:',
        "dry run skips checkpoints and runs device steps",
    ),
    (
        "R9",
        RUNNER,
        "if xml_before is not None and xml_after is not None and looks_like_new_popup(xml_before, xml_after):",
        "if False:",
        "drop the Layer-4 unknown-popup retry",
    ),
    (
        "R10",
        RUNNER,
        "                    return  # retry succeeded",
        "                    raise first_err  # retry succeeded",
        "Layer-4 retry success treated as failure",
    ),
    (
        "R11",
        RUNNER,
        "        if e.step_index < 0:\n",
        "        if e.step_index > 0:\n",
        "error no longer enriched with the failing step index",
    ),
    (
        "R12",
        RUNNER,
        "for i, step in enumerate(action.steps):",
        "for i, step in enumerate(action.steps[:-1]):",
        "last step of every action silently dropped",
    ),
    # ── validators.py ────────────────────────────────────────────────────────
    (
        "V1",
        VALIDATORS,
        'return not evaluate(spec["not"], ctx, device)',
        'return evaluate(spec["not"], ctx, device)',
        "`not:` composition no longer negates",
    ),
    (
        "V2",
        VALIDATORS,
        "return any(evaluate(s, ctx, device) for s in subs)",
        "return all(evaluate(s, ctx, device) for s in subs)",
        "`any_of:` behaves like all_of",
    ),
    (
        "V3",
        VALIDATORS,
        'subs = spec["all_of"]\n        return all(',
        'subs = spec["all_of"]\n        return any(',
        "`all_of:` behaves like any_of",
    ),
    (
        "V4",
        VALIDATORS,
        "    if spec is None:\n        return True\n",
        "    if spec is None:\n        return False\n",
        "empty validator spec fails instead of passing",
    ),
    (
        "V5",
        VALIDATORS,
        "    return text in xml\n",
        "    return text not in xml\n",
        "text_visible (substring mode) inverted",
    ),
    (
        "V6",
        VALIDATORS,
        "        if pat.search(xml):\n",
        "        if not pat.search(xml):\n",
        "element_present inverted",
    ),
    (
        "V7",
        VALIDATORS,
        "    return bool(fn(spec, ctx, device))\n",
        "    return not bool(fn(spec, ctx, device))\n",
        "every leaf validator result inverted",
    ),
    (
        "V8",
        VALIDATORS,
        "        return bool(fn(device, ctx))\n",
        "        return True\n",
        "custom_python always passes",
    ),
]

_SKIP_TOP: set[str] = set()  # tracked site files are small, and the demo planner reads site/public/showcase


def _tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=REPO, check=True, capture_output=True).stdout
    return [p for p in out.decode().split("\0") if p and p.split("/", 1)[0] not in _SKIP_TOP]


def _copy_tree(dest: Path) -> None:
    for rel in _tracked_files():
        src = REPO / rel
        if not src.is_file():
            continue  # deleted in the working tree
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)


def _run_tests(copy: Path, tests: list[str], timeout: int) -> tuple[bool, str]:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:randomly", "-p", "no:cacheprovider", *tests],
            cwd=copy,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, "timeout"
    tail = (proc.stdout.strip().splitlines() or [""])[-1]
    return proc.returncode == 0, tail


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--tests", default="tests/test_skill_*.py", help="glob of engine test files")
    ap.add_argument("--only", default="", help="comma-separated mutant ids")
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--json", dest="json_out", help="write results as JSON")
    args = ap.parse_args(argv)

    chosen = [m for m in MUTANTS if not args.only or m[0] in set(args.only.split(","))]
    tests = sorted(os.path.relpath(p, REPO) for p in glob.glob(str(REPO / args.tests)))
    if not tests:
        print(f"no tests match {args.tests}", file=sys.stderr)
        return 2

    # Snippet check against the real files before doing any work.
    for mid, rel, orig, _new, _note in chosen:
        count = (REPO / rel).read_text().count(orig)
        if count != 1:
            print(f"{mid}: snippet occurs {count}x in {rel} (expected 1); update tools/mutants.py", file=sys.stderr)
            return 2

    results = []
    with tempfile.TemporaryDirectory(prefix="ghost-mutants-") as tmp:
        copy = Path(tmp)
        _copy_tree(copy)
        t0 = time.monotonic()
        ok, tail = _run_tests(copy, tests, args.timeout)
        print(f"baseline: {'pass' if ok else 'FAIL'} ({tail}) {time.monotonic() - t0:.0f}s")
        if not ok:
            return 2

        for mid, rel, orig, new, note in chosen:
            path = copy / rel
            original = path.read_text()
            try:
                path.write_text(original.replace(orig, new, 1))
                passed, tail = _run_tests(copy, tests, args.timeout)
            finally:
                path.write_text(original)
            status = "survived" if passed else "killed"
            results.append({"id": mid, "file": rel, "status": status, "note": note, "tests": tail})
            print(f"{mid:4} {status:8} {rel.rsplit('/', 1)[-1]:14} {note}")

    killed = sum(r["status"] == "killed" for r in results)
    survived = [r for r in results if r["status"] == "survived"]
    print(f"\nkilled {killed}/{len(results)}, survived {len(survived)}")
    for r in survived:
        print(f"  survivor {r['id']}: {r['note']}")
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(results, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
