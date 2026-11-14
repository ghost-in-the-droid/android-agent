#!/usr/bin/env python3
"""Scan publishable files against FORBIDDEN.txt, skipping paths scripts/public-strip.txt keeps private."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from privacy.scrub import load_forbidden, scan_text  # noqa: E402

SCAN_ROOTS = ["."]  # the whole tree: tools/, .github/, portal/, site/, skillhub/ and the root files
SKIP_DIRS = {".git", "node_modules", "__pycache__", "dist", ".astro", "test-results", "playwright-report", ".venv"}
# The list itself and the scrubber must name what they redact.
SKIP = {"scripts/privacy/FORBIDDEN.txt", "scripts/privacy/FORBIDDEN.local.txt", "scripts/privacy/scrub.py", "docker-compose.langfuse.yml"}  # last: public local-dev defaults
TEXT_EXT = {
    ".md",
    ".txt",
    ".py",
    ".yaml",
    ".yml",
    ".json",
    ".ts",
    ".tsx",
    ".js",
    ".astro",
    ".html",
    ".css",
    ".cast",
    ".sh",
    ".toml",
    ".mjs",
    ".kt",
    ".kts",
    ".jsonl",
    ".xml",
    ".cfg",
    ".ini",
    ".svg",
    ".mdx",
    ".gitignore",
}
TEXT_NAMES = {"Makefile", "CODEOWNERS", "Dockerfile", ".gitignore"}
STRIP_LIST = "scripts/public-strip.txt"


def load_strip_paths(repo: Path) -> list[str]:
    """Entries release.sh removes before publishing; the strip list itself is removed too."""
    f = repo / STRIP_LIST
    if not f.exists():
        return []
    lines = [ln.strip() for ln in f.read_text().splitlines()]
    return [ln for ln in lines if ln and not ln.startswith("#")] + [STRIP_LIST]


def is_stripped(rel: str, strip_paths: list[str]) -> bool:
    """A "!path" entry keeps one file that a directory entry would otherwise strip."""
    if f"!{rel}" in strip_paths:
        return False
    return any(rel.startswith(p) if p.endswith("/") else rel == p for p in strip_paths if not p.startswith("!"))


def scan(repo: Path, patterns=None) -> tuple[list[tuple[str, str, str]], int]:
    """Return (hits outside stripped paths as (path, source, match), count of stripped files skipped)."""
    patterns = load_forbidden() if patterns is None else patterns
    strip_paths = load_strip_paths(repo)
    hits, skipped = [], 0
    for root in SCAN_ROOTS:
        p = repo / root
        files = [p] if p.is_file() else sorted(p.rglob("*")) if p.exists() else []
        for f in files:
            rel = f.relative_to(repo).as_posix()
            if SKIP_DIRS & set(f.relative_to(repo).parts):
                continue
            if not f.is_file() or rel in SKIP or (f.suffix not in TEXT_EXT and f.name not in TEXT_NAMES):
                continue
            if is_stripped(rel, strip_paths):
                skipped += 1
                continue
            for src, m in scan_text(f.read_text(errors="replace"), patterns):
                hits.append((rel, src, m))
    return hits, skipped


def main() -> int:
    repo = Path.cwd()
    hits, skipped = scan(repo)
    for rel, src, m in hits:
        shown = m if len(m) <= 6 else m[:3] + "…"
        print(f"::error file={rel}::forbidden pattern {src!r} matched ({shown})")
    print(f"privacy-guard: {skipped} file(s) under {STRIP_LIST} paths skipped (never published)")
    if hits:
        print(f"\n{len(hits)} forbidden hit(s) — see scripts/privacy/RECORDING_CHECKLIST.md")
        return 1
    print("privacy-guard: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
