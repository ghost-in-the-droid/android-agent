#!/usr/bin/env python3
"""Re-composite a demo from its kept workdir (.recordings/<demo>) WITHOUT
re-recording — for iterating on composite / asset tweaks on already-captured
footage. Reuses record_demo.composite() + the OCR gate + publish tail.

    python3 scripts/showcase/recompose.py <demo> [phone_offset] [--publish]

Default phone_offset 1.5 matches the recorder's ~1.5s screenrecord warmup.
Without --publish the result stays in the workdir (safe for iteration).
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # scripts/
import record_demo as R  # noqa: E402


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    demo = args[0] if args else "langchain"
    phone_offset = float(args[1]) if len(args) > 1 else 1.5
    publish = "--publish" in sys.argv

    workdir = R.REPO_ROOT / ".recordings" / demo
    if not (workdir / "plan.json").exists():
        R.die(f"no kept workdir at {workdir} (record with --keep-workdir first)")
    # Use the CURRENT spec.yaml (not plan.json's snapshot) so composite/spec edits
    # — content_speedup, phone_in_intro, layout tweaks — take effect on recompose.
    spec = R.load_spec(demo)
    patterns = R.load_forbidden()
    term_mp4 = workdir / "terminal.mp4"
    out_webm = workdir / "demo.webm"

    print(f"[recompose] {demo} phone_offset={phone_offset} publish={publish}")
    R.composite(spec, workdir, term_mp4, workdir / "phone.mp4",
                phone_offset_s=phone_offset, out_webm=out_webm)

    viol = R.ocr_gate(out_webm, workdir, patterns)
    if viol:
        for v in viol:
            print(f"[recompose] FORBIDDEN {v}")
        R.die(f"OCR gate FAILED ({len(viol)} hit) — not publishing")
    print("[recompose] OCR gate clean")

    size_mb = out_webm.stat().st_size / 1e6
    if not publish:
        print(f"[recompose] workdir only → {out_webm} ({size_mb:.1f} MB). "
              f"Add --publish to copy into site/public/.")
        return

    out_dir = R.SHOWCASE_DIR / demo
    out_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(out_webm, out_dir / "demo.webm")
    intro_motion = R.BRAND_DIR / f"intro-{demo}-motion.mp4"
    intro_dur = R.INTRO_S
    if spec.get("layout") == "three_window" and intro_motion.exists():
        p = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(intro_motion)],
            capture_output=True, text=True)
        intro_dur = float(p.stdout.strip() or R.INTRO_S)
    hw = spec.get("highlight_window") or {}
    poster_ss = intro_dur + float(hw.get("start_s", 2)) + 1.0
    subprocess.run(["ffmpeg", "-y", "-ss", str(poster_ss), "-i",
                    str(out_dir / "demo.webm"), "-frames:v", "1",
                    str(out_dir / "poster.png")], check=True)
    R.write_snippet(spec, out_dir / "snippet.py")
    print(f"[recompose] PUBLISHED → {out_dir / 'demo.webm'} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
