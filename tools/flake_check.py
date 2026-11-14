#!/usr/bin/env python3
"""Run the engine tests N times and fail if any per-test outcome differs.

Usage:
    python3 tools/flake_check.py [--runs 3] [--tests 'tests/test_skill_*.py']

Compares the set of (test id, outcome) pairs across runs, not just the
pass/fail counts, so a test that flips while another flips the other way is
still caught. Exit 0 when all runs agree and pass, 1 otherwise.
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
_OUTCOME = re.compile(r"^(PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS) (.+?)(?: - .*)?$")


def _run(tests: list[str]) -> tuple[int, dict[str, str]]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-rA", "-p", "no:randomly", "-p", "no:cacheprovider", *tests],
        cwd=REPO, capture_output=True, text=True,
    )
    outcomes = {}
    for line in proc.stdout.splitlines():
        m = _OUTCOME.match(line)
        if m:
            outcomes[m.group(2)] = m.group(1)
    return proc.returncode, outcomes


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--tests", default="tests/test_skill_*.py")
    args = ap.parse_args(argv)

    tests = sorted(os.path.relpath(p, REPO) for p in glob.glob(str(REPO / args.tests)))
    runs = []
    for i in range(args.runs):
        code, outcomes = _run(tests)
        print(f"run {i + 1}: exit {code}, {len(outcomes)} tests, "
              f"{sum(v == 'PASSED' for v in outcomes.values())} passed")
        runs.append((code, outcomes))

    first = runs[0][1]
    flaky = sorted({t for _, o in runs[1:] for t in set(first) | set(o) if o.get(t) != first.get(t)})
    for t in flaky:
        print(f"  flaky: {t}: " + " / ".join(o.get(t, 'missing') for _, o in runs))
    if flaky or any(code != 0 for code, _ in runs) or not first:
        print("flake check: FAIL")
        return 1
    print(f"flake check: {args.runs} identical runs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
