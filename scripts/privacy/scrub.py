#!/usr/bin/env python3
"""Privacy scrubber for the Ghost showcase recording pipeline.

Two jobs:

1. SUBSTITUTE — rewrite text (asciinema .cast files, generated snippets) so
   real paths, hostnames, device serials, and secrets become neutral
   placeholders before anything is rendered.

2. SCAN — check text (OCR output of rendered video frames, committed files)
   against the forbidden-pattern lists and report every hit. A hit means the
   artifact must not ship.

Pattern lists:
    scripts/privacy/FORBIDDEN.txt        committed, generic patterns only
    scripts/privacy/FORBIDDEN.local.txt  gitignored, personal identifiers

CLI:
    python3 scripts/privacy/scrub.py --check FILE [FILE...]   scan files, exit 1 on any hit
    python3 scripts/privacy/scrub.py --scrub IN OUT           substitution pass IN -> OUT
    python3 scripts/privacy/scrub.py --scrub-cast IN OUT      scrub an asciinema v2 .cast
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PRIVACY_DIR = Path(__file__).resolve().parent

# ── Substitutions ─────────────────────────────────────────────────────────────
# Order matters: earlier rules win (e.g. specific hostnames before generic paths).

SUBSTITUTIONS: list[tuple[re.Pattern, str]] = [
    # Personal-machine hostnames → neutral demo hosts
    (re.compile(r"[A-Za-z]+s-MacBook[A-Za-z-]*(\.local)?"), "ghost-dev-mac"),
    (re.compile(r"[a-z0-9-]+\.coredevice\.local"), "<device-hostname>"),
    (re.compile(r"\bckl-linux\b"), "ghost-dev-linux"),
    (re.compile(r"\bckl-mac\b"), "ghost-dev-mac"),
    # Home directories → ~
    (re.compile(r"/Users/[A-Za-z0-9_.-]+"), "~"),
    (re.compile(r"/home/[A-Za-z0-9_.-]+"), "~"),
    (re.compile(r"/Volumes/[A-Za-z0-9_.-]+"), "/Volumes/<VOLUME>"),
    # iOS UDIDs (8-4-4-4-12 hex)
    (
        re.compile(r"\b[A-F0-9]{8}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{12}\b"),
        "<IPHONE_UDID>",
    ),
    # iOS UDIDs (modern A12+ format: 8 hex - 16 hex, e.g. 00008030-0011223344556677),
    # optionally with an ios: prefix from ghost device specs
    (
        re.compile(r"\b(?:ios:)?[0-9A-Fa-f]{8}-[0-9A-Fa-f]{16}\b"),
        "<IPHONE_UDID>",
    ),
    # API keys / tokens
    (re.compile(r"sk-ant-[A-Za-z0-9_-]+"), "<REDACTED_KEY>"),
    (re.compile(r"sk-[A-Za-z0-9_-]{16,}"), "<REDACTED_KEY>"),
    (re.compile(r"AIza[0-9A-Za-z_-]{16,}"), "<REDACTED_KEY>"),
    (re.compile(r"ghp_[A-Za-z0-9]{16,}"), "<REDACTED_KEY>"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{16,}"), "<REDACTED_KEY>"),
    (re.compile(r"gsk_[A-Za-z0-9]{16,}"), "<REDACTED_KEY>"),
    (re.compile(r"xox[bap]-[A-Za-z0-9-]+"), "<REDACTED_KEY>"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "<REDACTED_KEY>"),
    # Sensitive env assignments shown in output (env dumps, exports)
    (
        re.compile(
            r"\b([A-Z0-9_]*(?:API_KEY|TOKEN|SECRET|PASSWORD|CREDENTIALS)[A-Z0-9_]*)=\S+"
        ),
        r"\1=<REDACTED>",
    ),
    # Passwords in prose
    (re.compile(r"(?i)\b(password\s*[:=]\s*)\S+"), r"\1<REDACTED>"),
    (re.compile(r"\bPwnd\w*"), "<REDACTED>"),
]


def scrub_text(text: str, extra: list[tuple[str, str]] | None = None) -> str:
    """Apply all substitution rules (plus per-run extras like real device
    serials -> <ANDROID_DEVICE>) to a block of text."""
    for literal, repl in extra or []:
        text = text.replace(literal, repl)
    for pat, repl in SUBSTITUTIONS:
        text = pat.sub(repl, text)
    return text


def scrub_cast(
    src: Path,
    dst: Path,
    extra: list[tuple[str, str]] | None = None,
    cols: int | None = None,
    rows: int | None = None,
) -> None:
    """Scrub an asciinema v2 cast (JSON-lines: header, then [t, type, data]
    events). Rewrites every output event and the header (env/title can leak
    SHELL paths and hostnames). Optionally force header width/height so the
    render size is deterministic regardless of the recording terminal."""
    out_lines = []
    with src.open() as f:
        header = json.loads(f.readline())
        header.pop("env", None)
        if "title" in header:
            header["title"] = scrub_text(header["title"], extra)
        if cols:
            header["width"] = cols
        if rows:
            header["height"] = rows
        out_lines.append(json.dumps(header))
        for line in f:
            line = line.strip()
            if not line:
                continue
            ev = json.loads(line)
            if isinstance(ev, list) and len(ev) == 3 and isinstance(ev[2], str):
                ev[2] = scrub_text(ev[2], extra)
            out_lines.append(json.dumps(ev))
    dst.write_text("\n".join(out_lines) + "\n")


def scrubbed_env(base: dict) -> dict:
    """A minimal, safe environment for demo subprocesses: keeps what commands
    need to run, drops anything that smells like a credential."""
    keep_exact = {
        "PATH", "TERM", "LANG", "LC_ALL", "SHELL", "COLUMNS", "LINES",
        "PYTHONPATH", "PYTHONUNBUFFERED", "VIRTUAL_ENV", "ANDROID_SERIAL",
    }
    secret = re.compile(r"KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|AUTH", re.I)
    env = {k: v for k, v in base.items() if k in keep_exact and not secret.search(k)}
    env["HOME"] = base.get("HOME", "/tmp")
    env["PS1"] = r"ghost@demo \W $ "
    return env


# ── Forbidden-pattern scanning ────────────────────────────────────────────────

def load_forbidden(extra_paths: list[Path] | None = None) -> list[tuple[str, re.Pattern]]:
    """Load FORBIDDEN.txt + FORBIDDEN.local.txt (if present) + any extras.
    Returns (source_line, compiled_regex) pairs. Plain lines become
    case-insensitive substring matches; 're:' lines are raw regexes."""
    paths = [PRIVACY_DIR / "FORBIDDEN.txt", PRIVACY_DIR / "FORBIDDEN.local.txt"]
    paths += extra_paths or []
    patterns: list[tuple[str, re.Pattern]] = []
    for p in paths:
        if not p.exists():
            continue
        for raw in p.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("re:"):
                patterns.append((line, re.compile(line[3:], re.I)))
            else:
                patterns.append((line, re.compile(re.escape(line), re.I)))
    return patterns


def scan_text(text: str, patterns=None) -> list[tuple[str, str]]:
    """Return [(pattern_line, matched_text), ...] for every forbidden hit."""
    patterns = patterns if patterns is not None else load_forbidden()
    hits = []
    for src, pat in patterns:
        m = pat.search(text)
        if m:
            hits.append((src, m.group(0)))
    return hits


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", nargs="+", metavar="FILE", help="scan files for forbidden patterns")
    mode.add_argument("--scrub", nargs=2, metavar=("IN", "OUT"), help="substitution pass on a text file")
    mode.add_argument("--scrub-cast", nargs=2, metavar=("IN", "OUT"), help="scrub an asciinema .cast file")
    args = ap.parse_args()

    if args.check:
        patterns = load_forbidden()
        bad = False
        for f in args.check:
            text = Path(f).read_text(errors="replace")
            for src, matched in scan_text(text, patterns):
                # Never echo the matched secret itself in full
                shown = matched if len(matched) <= 6 else matched[:3] + "…"
                print(f"FORBIDDEN {f}: pattern {src!r} matched ({shown})")
                bad = True
        if bad:
            return 1
        print(f"clean: {len(args.check)} file(s)")
        return 0

    if args.scrub:
        src, dst = map(Path, args.scrub)
        dst.write_text(scrub_text(src.read_text(errors="replace")))
        print(f"scrubbed {src} -> {dst}")
        return 0

    src, dst = map(Path, args.scrub_cast)
    scrub_cast(src, dst)
    print(f"scrubbed cast {src} -> {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
