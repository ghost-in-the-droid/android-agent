#!/usr/bin/env python3
"""record_showcase_reel.py — auto-stitch the showcase sizzle reel.

Reads every demo's recording spec (site/public/showcase/<demo>/spec.yaml),
takes each demo's highlight_window clip out of its rendered demo.webm,
orders the clips by copy.yaml's sizzle_order, joins them with a 200ms
crossfade, and writes site/public/showcase/hero-reel.webm.

Runs the same privacy OCR gate as record_demo.py before writing the output —
the reel is built from already-gated footage, but defense-in-depth is cheap.

Usage:
    python3 scripts/record_showcase_reel.py             # stitch all available
    python3 scripts/record_showcase_reel.py --dry-run   # report what would stitch
    python3 scripts/record_showcase_reel.py --demos a b # explicit subset/order
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from privacy.scrub import load_forbidden  # noqa: E402
import record_demo  # noqa: E402  (shares INTRO_S, ocr_gate, run, log/die)

XFADE_S = 0.2
FPS = 30
OUT_W, OUT_H = 1280, 720


def collect(showcase_dir: Path, only: list[str] | None) -> list[dict]:
    """All demos that have both a spec.yaml and a rendered demo.webm,
    ordered by copy.yaml sizzle_order (or the explicit --demos order)."""
    copy = yaml.safe_load((showcase_dir / "copy.yaml").read_text())
    order = {d["id"]: d.get("sizzle_order") or 99 for d in copy.get("demos", [])}

    clips = []
    for spec_path in sorted(showcase_dir.glob("*/spec.yaml")):
        demo = spec_path.parent.name
        if only and demo not in only:
            continue
        spec = yaml.safe_load(spec_path.read_text())
        webm = spec_path.parent / "demo.webm"
        hw = spec.get("highlight_window") or {}
        if not webm.exists():
            record_demo.log(f"skip {demo}: no demo.webm yet")
            continue
        if not {"start_s", "end_s"} <= hw.keys():
            record_demo.log(f"skip {demo}: spec has no highlight_window")
            continue
        clips.append({
            "demo": demo,
            "webm": webm,
            # highlight_window is in timeline seconds; the rendered file has a
            # 1s intro card in front of the content
            "start": float(hw["start_s"]) + record_demo.INTRO_S,
            "dur": float(hw["end_s"]) - float(hw["start_s"]),
            "order": order.get(demo, 99),
        })
    if only:
        clips.sort(key=lambda c: only.index(c["demo"]))
    else:
        clips.sort(key=lambda c: c["order"])
    return clips


def stitch(clips: list[dict], out: Path, workdir: Path) -> None:
    """Trim each highlight clip, then chain xfade transitions."""
    inputs, fc = [], []
    for i, c in enumerate(clips):
        inputs += ["-ss", str(c["start"]), "-t", str(c["dur"]), "-i", str(c["webm"])]
        fc.append(f"[{i}:v]scale={OUT_W}:{OUT_H},fps={FPS},format=yuv420p,"
                  f"setpts=PTS-STARTPTS[v{i}];")

    if len(clips) == 1:
        fc.append("[v0]copy[out]")
    else:
        prev = "v0"
        offset = clips[0]["dur"] - XFADE_S
        for i in range(1, len(clips)):
            label = "out" if i == len(clips) - 1 else f"x{i}"
            fc.append(f"[{prev}][v{i}]xfade=transition=fade:duration={XFADE_S}:"
                      f"offset={offset:.3f}[{label}];")
            prev = label
            offset += clips[i]["dur"] - XFADE_S
        fc[-1] = fc[-1].rstrip(";")

    record_demo.run(
        ["ffmpeg", "-y", *inputs, "-filter_complex", "".join(fc), "-map", "[out]",
         "-c:v", "libvpx-vp9", "-crf", "40", "-b:v", "0",
         "-deadline", "good", "-cpu-used", "2", "-row-mt", "1", "-an", str(out)],
        "reel stitch", heavy=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="Stitch the showcase sizzle reel")
    ap.add_argument("--demos", nargs="+", help="explicit demo ids (and order); default: all with sizzle_order")
    ap.add_argument("--dry-run", action="store_true", help="report clips without rendering")
    ap.add_argument("--showcase-dir", type=Path, default=record_demo.SHOWCASE_DIR,
                    help=argparse.SUPPRESS)  # test hook
    ap.add_argument("--out", type=Path, help="output path (default <showcase>/hero-reel.webm)")
    args = ap.parse_args()

    clips = collect(args.showcase_dir, args.demos)
    if not clips:
        record_demo.die("no stitchable demos (need spec.yaml + demo.webm + highlight_window)")
    total = sum(c["dur"] for c in clips) - XFADE_S * (len(clips) - 1)
    for c in clips:
        record_demo.log(f"clip {c['order']:>2}. {c['demo']:24s} "
                        f"{c['dur']:.1f}s @ {c['start']:.1f}s of {c['webm'].name}")
    record_demo.log(f"reel: {len(clips)} clips, ~{total:.1f}s with {XFADE_S}s crossfades")
    if args.dry_run:
        return 0

    out = args.out or (args.showcase_dir / "hero-reel.webm")
    workdir = REPO_ROOT / ".recordings" / "_reel"
    if workdir.exists():
        shutil.rmtree(workdir)
    workdir.mkdir(parents=True)
    tmp = workdir / "hero-reel.webm"
    stitch(clips, tmp, workdir)

    if shutil.which("tesseract"):
        record_demo.log("privacy OCR gate on stitched reel")
        violations = record_demo.ocr_gate(tmp, workdir, load_forbidden())
        if violations:
            for v in violations:
                record_demo.log(f"  FORBIDDEN {v}")
            record_demo.die(f"OCR gate FAILED — reel stays quarantined in {workdir}")
    else:
        record_demo.die("tesseract missing — the reel cannot ship ungated")

    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(tmp, out)
    shutil.rmtree(workdir)
    record_demo.log(f"DONE → {out} ({out.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
