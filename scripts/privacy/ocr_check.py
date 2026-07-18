#!/usr/bin/env python3
"""ocr_check.py — OCR-scan images and videos against the forbidden lists.

The grep guard (privacy.yml) covers text files; this covers the binary
showcase artifacts (demo.webm, poster.png, brand cards) that text grep
cannot see. Same fail-closed contract as record_demo.py's gate: a file
that yields zero scannable frames is an ERROR, never a pass.

Usage:
    python3 scripts/privacy/ocr_check.py FILE [FILE...]
    python3 scripts/privacy/ocr_check.py --all-showcase   # every webm/png under site/public/showcase

Exit codes: 0 clean, 1 forbidden hit or unscannable input, 2 tooling missing.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from privacy.scrub import load_forbidden, scan_text  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
SHOWCASE = REPO_ROOT / "site" / "public" / "showcase"
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}
VIDEO_EXT = {".webm", ".mp4", ".gif", ".mov"}


def ocr(png: Path) -> str:
    r = subprocess.run(["tesseract", str(png), "stdout"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(f"ERROR: tesseract failed on {png}: {r.stderr.strip()[:200]}")
        sys.exit(1)
    return r.stdout or ""


def frames_of(path: Path, tmp: Path) -> list[Path]:
    """The file itself for images; up to 30 frames at 2s intervals (plus the
    first frame, so sub-2s clips still yield something) for videos."""
    if path.suffix.lower() in IMAGE_EXT:
        return [path]
    out = tmp / path.stem
    out.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(path),
         "-vf", "select='eq(n\\,0)+not(mod(t\\,2))'", "-vsync", "vfr",
         "-frames:v", "30", str(out / "f%03d.png")],
        capture_output=True, text=True)
    return sorted(out.glob("f*.png"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("files", nargs="*", type=Path)
    ap.add_argument("--all-showcase", action="store_true",
                    help="scan every image/video under site/public/showcase")
    args = ap.parse_args()

    for tool in ("tesseract", "ffmpeg"):
        if not shutil.which(tool):
            print(f"ERROR: {tool} not on PATH")
            return 2

    files = list(args.files)
    if args.all_showcase:
        files += [p for p in SHOWCASE.rglob("*")
                  if p.suffix.lower() in IMAGE_EXT | VIDEO_EXT]
    files = [f for f in files if f.suffix.lower() in IMAGE_EXT | VIDEO_EXT]
    if not files:
        print("nothing to scan (no image/video inputs)")
        return 0

    patterns = load_forbidden()
    bad = 0
    with tempfile.TemporaryDirectory(prefix="ocr_check_") as td:
        for f in files:
            frames = frames_of(f, Path(td))
            if not frames:
                print(f"ERROR: {f}: no scannable frames — refusing to pass unscanned media")
                bad += 1
                continue
            hits = []
            for fr in frames:
                for src, m in scan_text(ocr(fr), patterns):
                    shown = m if len(m) <= 6 else m[:3] + "…"
                    hits.append(f"pattern {src!r} matched ({shown}) in frame {fr.name}")
            if hits:
                for h in hits:
                    print(f"FORBIDDEN {f}: {h}")
                bad += len(hits)
            else:
                print(f"clean: {f} ({len(frames)} frame(s))")
    if bad:
        print(f"\n{bad} problem(s) — see scripts/privacy/RECORDING_CHECKLIST.md")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
