#!/usr/bin/env python3
"""Build the three_window intro-motion mp4 from live sources.

Reproduces the original opener: the full-script code window holds, then shrinks
and settles into the small code-pane slot while the header / headline / mascot
fade in — ending exactly on the content layout so the concat seam is invisible.

Sources (all live, so it never goes stale):
  intro_full  : full script drawn at FULL_WIN   (render_codepane.py --full)
  codepane    : main() segment drawn at WIN      (record's live codepane.png)
  bg-<demo>   : header + headline + mascot        (baked brand bg)

Usage: render_intro_motion.py <demo> <intro_full.png> <codepane.png> <out.mp4>
"""
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parents[2]
BRAND = REPO / "site" / "public" / "showcase" / "_brand"

CANVAS = (1920, 1080)
FPS = 30
DUR = 7.8
N = round(FPS * DUR)               # 234 frames — must match the recorder's sync
BG = (7, 10, 8)                    # BG_HEX 070a08
FULL_WIN = (44, 40, 1876, 1038)    # big intro window
WIN = (32, 742, 1392, 1041)        # code-pane slot in the content layout

FADE_IN = 1.0                      # window fades up over the first second
SHRINK_START = 5.4                 # hold the full script until here
XFADE_AT = 0.30                    # begin full->main crossfade at 30% of the shrink


def lerp(a, b, t):
    return a + (b - a) * t


def ease_out(t):
    return 1 - (1 - t) ** 3


def fade_alpha(img, a):
    if a >= 1.0:
        return img
    out = img.copy()
    out.putalpha(img.getchannel("A").point(lambda v: int(v * a)))
    return out


def main():
    demo, full_path, pane_path, out_path = sys.argv[1:5]
    full = Image.open(full_path).convert("RGBA")
    pane = Image.open(pane_path).convert("RGBA")
    header = Image.open(BRAND / f"bg-{demo}.png").convert("RGBA")
    full_win = full.crop(FULL_WIN)      # full-script window (with chrome)
    pane_win = pane.crop(WIN)           # main() window (with chrome)

    tmp = Path(tempfile.mkdtemp())
    for i in range(N):
        t = i / FPS
        canvas = Image.new("RGBA", CANVAS, BG + (255,))

        if t <= SHRINK_START:
            prog = 0.0
        else:
            prog = ease_out(min(1.0, (t - SHRINK_START) / (DUR - SHRINK_START)))

        # header/headline/mascot fade in as the window shrinks
        if prog > 0:
            canvas.alpha_composite(fade_alpha(header, prog))

        # window geometry interpolates FULL_WIN -> WIN
        x0 = lerp(FULL_WIN[0], WIN[0], prog)
        y0 = lerp(FULL_WIN[1], WIN[1], prog)
        x1 = lerp(FULL_WIN[2], WIN[2], prog)
        y1 = lerp(FULL_WIN[3], WIN[3], prog)
        w, h = max(1, int(x1 - x0)), max(1, int(y1 - y0))

        win = full_win.resize((w, h))
        if prog > XFADE_AT:                       # crossfade full script -> main()
            xf = (prog - XFADE_AT) / (1 - XFADE_AT)
            win = Image.blend(win, pane_win.resize((w, h)), xf)
        if t < FADE_IN:                           # initial fade-up
            win = fade_alpha(win, t / FADE_IN)

        canvas.alpha_composite(win, (int(x0), int(y0)))
        canvas.convert("RGB").save(tmp / f"f{i:04d}.png")

    subprocess.run(
        ["ffmpeg", "-y", "-framerate", str(FPS), "-i", str(tmp / "f%04d.png"),
         "-t", str(DUR), "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-movflags", "+faststart", out_path],
        check=True, capture_output=True)
    print(f"[render_intro_motion] {out_path} — {N} frames, "
          f"shrink {SHRINK_START}->{DUR}s, ends on content layout")


if __name__ == "__main__":
    main()
