#!/usr/bin/env python3
"""Card text for skill demos: header, intro eyebrow/title/byline, subheader, outro.

Every card string has a skill-derived default and can be overridden per clip in
spec.yaml under `cards:` (keys below). This script also writes the per-demo card
PNGs into site/public/showcase/_brand/:

    bg-<demo>.png      C-prime background with the header repainted
    intro-<demo>.png   eyebrow + title (+ optional byline)
    outro-<demo>.png   skill ref + install command + hub path

Usage:
    python3 scripts/showcase/skill_cards.py --demo calculator-calculate
    python3 scripts/showcase/skill_cards.py --demo calculator-calculate \
        --eyebrow "SKILL SHOWCASE" --subheader "ghost/calculator: calculate"

Spec keys (all optional; defaults derived from the skill):
    cards:
      header:        "GHOST IN THE DROID"
      eyebrow:       "SKILL SHOWCASE"
      title:         <copy.yaml title>
      byline:        <author>/<skill>        (omitted unless set)
      subheader:     "<author>/<skill>: <action>"   (replaces the first caption)
      outro_title:   "<author>/<skill>"
      outro_cmd:     "ghost skill install <author>/<skill>"
      outro_url:     "https://ghostinthedroid.com/skills/<author>/<skill>/"

<author>/<skill>/<action> come from the spec's terminal command
(`ghost skill run <author>/<skill> <action> ...`) unless `cards.skill` is set.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parents[2]
BRAND_DIR = REPO_ROOT / "site" / "public" / "showcase" / "_brand"
sys.path.insert(0, str(Path(__file__).resolve().parent))

import generate_brand_assets as gba  # noqa: E402

VERSION = "1.6.0"
DEFAULT_HEADER = "GHOST IN THE DROID"
DEFAULT_EYEBROW = "SKILL SHOWCASE"
# header block in cprime-bg.png (top-left wordmark), and a clean band to copy from
HEADER_BOX = (30, 30, 1150, 80)
HEADER_SOURCE_Y = 110
HEADER_POS = (42, 40)
HEADER_SIZE = 30
HEADER_TRACK = 0.22  # letter-spacing in em

CMD_RE = re.compile(r"ghost skill run (\S+) (\S+)")


def resolve(spec: dict) -> dict:
    """Return the effective card strings for a spec (spec `cards:` > derived defaults)."""
    cards = dict(spec.get("cards") or {})
    ref, action = None, cards.get("action")
    for step in spec.get("timeline") or []:
        cmd = (step.get("args") or {}).get("cmd", "")
        m = CMD_RE.search(cmd) if step.get("action") == "terminal_type" else None
        if m:
            ref, action = m.group(1), m.group(2)
            break
    if cards.get("skill"):
        ref = cards["skill"]
    ref = ref or spec.get("demo", "skill")
    parts = ref.split("/")
    skill_ref = "/".join(parts[-2:]) if len(parts) >= 2 else f"ghost/{ref}"
    out = {
        "header": cards.get("header", DEFAULT_HEADER),
        "eyebrow": cards.get("eyebrow", DEFAULT_EYEBROW),
        "title": cards.get("title", spec.get("title", spec.get("demo", "skill"))),
        "byline": cards.get("byline"),
        "subheader": cards.get("subheader", f"{skill_ref}: {action}" if action else skill_ref),
        "outro_title": cards.get("outro_title", skill_ref),
        "outro_cmd": cards.get("outro_cmd", f"ghost skill install {skill_ref}"),
        "outro_url": cards.get("outro_url", f"https://ghostinthedroid.com/skills/{skill_ref}/"),
    }
    return out


def _spaced(draw: ImageDraw.ImageDraw, xy, text: str, font, fill) -> None:
    x, y = xy
    track = HEADER_TRACK * HEADER_SIZE
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        x += draw.textlength(ch, font=font) + track


def make_bg(demo: str, header: str) -> Path:
    """C-prime background with the header repainted from `header`."""
    base = BRAND_DIR / "cprime-bg.png"
    if not base.exists():
        gba.generate_native_terminal_assets(BRAND_DIR)
    img = Image.open(base).convert("RGB")
    x0, y0, x1, y1 = HEADER_BOX
    band = img.crop((x0, HEADER_SOURCE_Y, x1, HEADER_SOURCE_Y + (y1 - y0)))
    img.paste(band, (x0, y0))
    d = ImageDraw.Draw(img)
    _spaced(d, HEADER_POS, header.upper(), gba.outfit(HEADER_SIZE, 600), gba.hex_rgb(gba.ACCENT))
    out = BRAND_DIR / f"bg-{demo}.png"
    img.save(out)
    return out


def make_intro(demo: str, cards: dict) -> Path:
    img = gba.intro_card(demo, cards["title"], VERSION, kicker=cards["eyebrow"], byline=cards["byline"])
    out = BRAND_DIR / f"intro-{demo}.png"
    # Keep the intro wordmark configurable too.
    d = ImageDraw.Draw(img)
    d.rectangle((145, 60, 1050, 125), fill=gba.hex_rgb(gba.GRAY_7))
    d.text((152, 74), cards["header"], font=gba.outfit(34, 600), fill=gba.hex_rgb(gba.GRAY_1))
    img.save(out)
    return out


def make_outro(demo: str, cards: dict) -> Path:
    img = gba.brand_background()
    gba.draw_version_stamp(img, VERSION)
    d = ImageDraw.Draw(img)
    mascot = Image.open(gba.MASCOT / "43-wave.png").convert("RGBA")
    mascot.thumbnail((150, 150), Image.LANCZOS)
    img.paste(mascot, ((gba.W - mascot.width) // 2, 230), mascot)
    ft = gba.outfit(96, 800)
    d.text(((gba.W - d.textlength(cards["outro_title"], font=ft)) / 2, 420),
           cards["outro_title"], font=ft, fill=gba.hex_rgb(gba.GRAY_1))
    fc = gba.mono(38, 500)
    cmd = cards["outro_cmd"]
    ctw = d.textlength("$ " + cmd, font=fc)
    px, py = 44, 26
    x0 = (gba.W - ctw) / 2 - px
    y0 = 580
    d.rounded_rectangle([x0, y0, x0 + ctw + 2 * px, y0 + 38 + 2 * py], radius=16,
                        fill=gba.hex_rgb("#101710"), outline=gba.hex_rgb(gba.GRAY_5), width=2)
    d.text((x0 + px, y0 + py), "$ ", font=fc, fill=gba.hex_rgb(gba.ACCENT))
    d.text((x0 + px + d.textlength("$ ", font=fc), y0 + py), cmd, font=fc,
           fill=gba.hex_rgb(gba.ACCENT_HIGH))
    fu = gba.mono(36, 400)
    path = re.sub(r"^https?://", "", cards["outro_url"])
    d.text(((gba.W - d.textlength(path, font=fu)) / 2, 740), path, font=fu,
           fill=gba.hex_rgb(gba.GRAY_3))
    out = BRAND_DIR / f"outro-{demo}.png"
    img.save(out)
    return out


def build(demo: str, spec: dict) -> list[Path]:
    cards = resolve(spec)
    return [make_bg(demo, cards["header"]), make_intro(demo, cards), make_outro(demo, cards)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--demo", required=True)
    for flag in ("header", "eyebrow", "title", "byline", "subheader", "outro-title", "outro-cmd", "outro-url"):
        ap.add_argument(f"--{flag}")
    ap.add_argument("--skill", help="author/skill, overrides the one found in the spec")
    args = ap.parse_args()

    import yaml
    spec_path = REPO_ROOT / "site" / "public" / "showcase" / args.demo / "spec.yaml"
    spec = yaml.safe_load(spec_path.read_text()) if spec_path.exists() else {"demo": args.demo}
    spec["demo"] = args.demo
    cards = dict(spec.get("cards") or {})
    for flag in ("header", "eyebrow", "title", "byline", "subheader", "skill"):
        v = getattr(args, flag)
        if v is not None:
            cards[flag] = v
    for flag, key in (("outro_title", "outro_title"), ("outro_cmd", "outro_cmd"), ("outro_url", "outro_url")):
        v = getattr(args, flag)
        if v is not None:
            cards[key] = v
    spec["cards"] = cards
    for p in build(args.demo, spec):
        print(p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
