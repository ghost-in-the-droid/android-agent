#!/usr/bin/env python3
"""Live-render the showcase code pane from source.

Draws the ``def main()`` segment of a Python file as a macOS-style terminal
window PNG, so the code pane in a demo can never drift out of sync with the
script it is supposed to mirror (the old baked asset silently shipped an
OpenRouter version of the code long after the script had moved on).

Usage:  render_codepane.py <source.py> <out.png> [--title NAME]
Geometry + palette match codepane-langchain-v3.png so the compositor is unchanged.
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont
from pygments import lex
from pygments.lexers import PythonLexer
from pygments.token import Comment, Keyword, Name, Number, String

REPO = Path(__file__).resolve().parents[2]
FONT_PATH = REPO / "site/public/showcase/_brand/fonts/JetBrainsMono[wght].ttf"

# Ghost-brand palette, sampled straight from the shipped assets.
BG      = (13, 19, 14)      # window / code background
TITLE   = (26, 33, 27)      # title bar
TEXT    = (216, 216, 216)   # default code text
GREEN   = (0, 216, 144)     # keywords, strings, def-names (brand accent)
COMMENT = (120, 144, 120)   # comments
LINENO  = (96, 108, 98)     # gutter line numbers
TITLE_FG = (150, 160, 152)  # filename in the title bar
LIGHTS  = [(255, 95, 86), (255, 189, 46), (39, 201, 63)]  # macOS traffic lights

# Full 1920x1080 canvas; window box matches codepane-langchain-v3.png exactly.
CANVAS  = (1920, 1080)
WIN     = (32, 742, 1392, 1041)   # x0, y0, x1, y1  — small code pane (main segment)
FULL_WIN = (32, 175, 1392, 1041)   # tall left-column intro window (matches render_intro_motion)
TITLE_H = 40
RADIUS  = 14
PAD_X   = 30      # left padding inside code area (before gutter)
PAD_TOP = 14      # top padding inside code area
GUTTER  = 58      # width reserved for line numbers


def color_for(tok):
    if tok in Comment:       return COMMENT
    if tok in Keyword:       return GREEN
    if tok in String:        return GREEN
    if tok in Name.Function: return GREEN
    if tok in Number:        return TEXT
    return TEXT


def extract_main(src_path):
    """Return (lines, first_lineno) for the def main() block."""
    lines = Path(src_path).read_text().splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith("def main"))
    end = start + 1
    while end < len(lines) and not (
        lines[end].startswith("def ") or lines[end].startswith("#")
    ):
        end += 1
    seg = lines[start:end]
    while seg and not seg[-1].strip():
        seg.pop()
    return seg, start + 1


def extract_full(src_path):
    """Return (lines, 1) for the whole file (trailing blanks trimmed)."""
    lines = Path(src_path).read_text().splitlines()
    while lines and not lines[-1].strip():
        lines.pop()
    return lines, 1


def load_font(size):
    f = ImageFont.truetype(str(FONT_PATH), size)
    try:
        f.set_variation_by_axes([460])   # medium weight for legibility
    except Exception:
        pass
    return f


def render(src_path, out_path, title="langchain_script.py", full=False):
    seg, first_lineno = extract_full(src_path) if full else extract_main(src_path)
    n = len(seg)
    x0, y0, x1, y1 = FULL_WIN if full else WIN
    win_w, win_h = x1 - x0, y1 - y0
    code_h = win_h - TITLE_H - 2 * PAD_TOP

    # Auto-fit font so all n lines fit the code area.
    pitch = code_h / n
    fsize = max(12, int(pitch * 0.74))
    font = load_font(fsize)
    ascent, descent = font.getmetrics()
    char_w = font.getlength("M")

    img = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Soft drop shadow, then the window body.
    shadow = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        [x0, y0 + 10, x1, y1 + 14], RADIUS, fill=(0, 0, 0, 120))
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(12)))

    d.rounded_rectangle([x0, y0, x1, y1], RADIUS, fill=BG + (255,))
    # Title bar (rounded top, square bottom via a covering rect).
    d.rounded_rectangle([x0, y0, x1, y0 + TITLE_H], RADIUS, fill=TITLE + (255,))
    d.rectangle([x0, y0 + TITLE_H - RADIUS, x1, y0 + TITLE_H], fill=TITLE + (255,))

    # Traffic lights.
    cy = y0 + TITLE_H // 2
    for i, col in enumerate(LIGHTS):
        cx = x0 + 22 + i * 26
        d.ellipse([cx - 7, cy - 7, cx + 7, cy + 7], fill=col + (255,))

    # Centered filename.
    tfont = load_font(19)
    tw = tfont.getlength(title)
    d.text(((x0 + x1) / 2 - tw / 2, cy - 11), title, font=tfont, fill=TITLE_FG + (255,))

    # Code, line by line, syntax highlighted.
    code_x = x0 + PAD_X + GUTTER
    y = y0 + TITLE_H + PAD_TOP
    for idx, line in enumerate(seg):
        ln = str(first_lineno + idx)
        lnw = font.getlength(ln)
        d.text((x0 + PAD_X + GUTTER - 14 - lnw, y), ln, font=font, fill=LINENO + (255,))
        x = code_x
        for tok, val in lex(line + "\n", PythonLexer()):
            val = val.rstrip("\n")
            if not val:
                continue
            d.text((x, y), val, font=font, fill=color_for(tok) + (255,))
            x += font.getlength(val)
        y += pitch

    img.save(out_path)
    print(f"[render_codepane] {out_path} — {n} lines (L{first_lineno}-"
          f"{first_lineno + n - 1}), font {fsize}px")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    title = next((a.split("=", 1)[1] for a in sys.argv[1:]
                  if a.startswith("--title=")), "langchain_script.py")
    full = "--full" in sys.argv
    render(args[0], args[1], title, full=full)
