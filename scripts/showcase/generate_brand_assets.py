#!/usr/bin/env python3
"""Generate Ghost Showcase brand assets — intro/outro cards, device frames.

Source of truth for site/public/showcase/_brand/. Regenerate after palette
or feature-list changes:

    python3 scripts/showcase/generate_brand_assets.py

Consumed by the showcase pipeline (record_demo.py): intro/outro cards are
1920x1080 stills prepended/appended to each demo; device frames are
transparent overlays composited above the screen recording (screen
coordinates in frames.json).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml
from PIL import Image, ImageDraw, ImageFilter, ImageFont

REPO = Path(__file__).resolve().parents[2]
BRAND = REPO / "site" / "public" / "showcase" / "_brand"
FONTS = BRAND / "fonts"
MASCOT = REPO / "site" / "public" / "mascot"

W, H = 1920, 1080

# Palette — keep in sync with site/src/styles/custom.css
ACCENT = "#00e5a0"
ACCENT_HIGH = "#6efcd0"
ACCENT_LOW = "#052e1e"
GRAY_1 = "#e8ede9"
GRAY_3 = "#8a9a8d"
GRAY_5 = "#2a3a2d"
GRAY_7 = "#0d130e"
BG_DEEP = "#070b08"

# Demo slugs + titles come from marketing's copy.yaml (single source of truth).
COPY_YAML = REPO / "site" / "public" / "showcase" / "copy.yaml"


def load_demos() -> dict[str, str]:
    data = yaml.safe_load(COPY_YAML.read_text())
    return {d["id"]: d["title"] for d in data["demos"]}


def font(path: Path, size: int, weight: int) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(path), size)
    f.set_variation_by_axes([weight])
    return f


def outfit(size: int, weight: int = 400) -> ImageFont.FreeTypeFont:
    return font(FONTS / "Outfit[wght].ttf", size, weight)


def mono(size: int, weight: int = 400) -> ImageFont.FreeTypeFont:
    return font(FONTS / "JetBrainsMono[wght].ttf", size, weight)


def hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))


def brand_background() -> Image.Image:
    """Dark green vertical gradient with a soft accent glow, matching the site."""
    top, bottom = hex_rgb(GRAY_7), hex_rgb(BG_DEEP)
    grad = Image.linear_gradient("L").resize((W, H))
    bg = Image.composite(Image.new("RGB", (W, H), bottom), Image.new("RGB", (W, H), top), grad)

    glow = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(glow)
    d.ellipse([W * 0.55, H * 0.75, W * 1.35, H * 1.6], fill=26)
    glow = glow.filter(ImageFilter.GaussianBlur(160))
    bg = Image.composite(Image.new("RGB", (W, H), hex_rgb(ACCENT)), bg, glow)

    d = ImageDraw.Draw(bg)
    d.line([(0, H - 4), (W, H - 4)], fill=hex_rgb(ACCENT_LOW), width=4)
    return bg


def draw_lockup(img: Image.Image) -> None:
    """Mascot + wordmark, top-left."""
    d = ImageDraw.Draw(img)
    mascot = Image.open(MASCOT / "09-base-ghost.png").convert("RGBA")
    mascot.thumbnail((64, 64), Image.LANCZOS)
    img.paste(mascot, (72, 60), mascot)
    d.text((152, 74), "Ghost in the Droid", font=outfit(34, 600), fill=hex_rgb(GRAY_1))


def draw_version_stamp(img: Image.Image, version: str) -> None:
    d = ImageDraw.Draw(img)
    label = f"v{version}"
    f = mono(28, 500)
    tw = d.textlength(label, font=f)
    x, y = W - 72 - tw, H - 72
    d.ellipse([x - 26, y + 10, x - 12, y + 24], fill=hex_rgb(ACCENT))
    d.text((x, y), label, font=f, fill=hex_rgb(GRAY_3))


def intro_card(slug: str, name: str, version: str) -> Image.Image:
    img = brand_background()
    draw_lockup(img)
    draw_version_stamp(img, version)
    d = ImageDraw.Draw(img)

    kicker = "F E A T U R E"
    fk = mono(30, 500)
    d.text(((W - d.textlength(kicker, font=fk)) / 2, 402), kicker, font=fk, fill=hex_rgb(ACCENT))

    size = 118
    ft = outfit(size, 800)
    while d.textlength(name, font=ft) > 1680 and size > 56:
        size -= 6
        ft = outfit(size, 800)
    tw = d.textlength(name, font=ft)
    d.text(((W - tw) / 2, 462 + (118 - size) * 0.55), name, font=ft, fill=hex_rgb(GRAY_1))

    bar_w = 180
    d.rounded_rectangle(
        [(W - bar_w) / 2, 640, (W + bar_w) / 2, 648], radius=4, fill=hex_rgb(ACCENT)
    )
    return img


def outro_card(version: str, cta: str) -> Image.Image:
    img = brand_background()
    draw_version_stamp(img, version)
    d = ImageDraw.Draw(img)

    mascot = Image.open(MASCOT / "43-wave.png").convert("RGBA")
    mascot.thumbnail((150, 150), Image.LANCZOS)
    img.paste(mascot, ((W - mascot.width) // 2, 280), mascot)

    ft = outfit(96, 800)
    site_txt = "ghostinthedroid.com"
    tw = d.textlength(site_txt, font=ft)
    d.text(((W - tw) / 2, 460), site_txt, font=ft, fill=hex_rgb(GRAY_1))

    fc = mono(38, 500)
    chip_text = f"$ {cta}"
    ctw = d.textlength(chip_text, font=fc)
    pad_x, pad_y = 44, 26
    cx0 = (W - ctw) / 2 - pad_x
    cy0 = 632
    d.rounded_rectangle(
        [cx0, cy0, cx0 + ctw + 2 * pad_x, cy0 + 38 + 2 * pad_y],
        radius=16,
        fill=hex_rgb("#101710"),
        outline=hex_rgb(GRAY_5),
        width=2,
    )
    d.text((cx0 + pad_x, cy0 + pad_y), "$ ", font=fc, fill=hex_rgb(ACCENT))
    d.text(
        (cx0 + pad_x + d.textlength("$ ", font=fc), cy0 + pad_y),
        cta,
        font=fc,
        fill=hex_rgb(ACCENT_HIGH),
    )
    return img


def _punch_transparent(img: Image.Image, box: list[float], radius: int) -> None:
    """Make a rounded-rect region fully transparent (the screen window)."""
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(box, radius=radius, fill=255)
    px = img.load()
    mpx = mask.load()
    x0, y0, x1, y1 = (int(v) for v in box)
    for y in range(max(0, y0), min(img.height, y1 + 1)):
        for x in range(max(0, x0), min(img.width, x1 + 1)):
            if mpx[x, y]:
                px[x, y] = (0, 0, 0, 0)


def device_frame(
    screen_w_px: int,
    screen_h_px: int,
    bezel: int,
    body_radius: int,
    screen_radius: int,
    edge_color: str,
    body_color: str,
    camera: str,
) -> tuple[Image.Image, dict]:
    """Draw a minimalist device frame centered on a transparent 1920x1080 canvas."""
    target_h = 940
    scr_w = round(target_h * screen_w_px / screen_h_px)
    scr_h = target_h
    body_w, body_h = scr_w + 2 * bezel, scr_h + 2 * bezel
    bx0, by0 = (W - body_w) // 2, (H - body_h) // 2
    sx0, sy0 = bx0 + bezel, by0 + bezel

    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    d.rounded_rectangle(
        [bx0 - 3, by0 - 3, bx0 + body_w + 3, by0 + body_h + 3],
        radius=body_radius + 3,
        fill=hex_rgb(edge_color) + (255,),
    )
    d.rounded_rectangle(
        [bx0, by0, bx0 + body_w, by0 + body_h],
        radius=body_radius,
        fill=hex_rgb(body_color) + (255,),
    )

    # side buttons (right edge)
    btn = hex_rgb(edge_color) + (255,)
    d.rounded_rectangle([bx0 + body_w, by0 + 180, bx0 + body_w + 6, by0 + 260], radius=3, fill=btn)
    d.rounded_rectangle([bx0 + body_w, by0 + 290, bx0 + body_w + 6, by0 + 420], radius=3, fill=btn)

    _punch_transparent(img, [sx0, sy0, sx0 + scr_w, sy0 + scr_h], screen_radius)

    # camera cutouts sit above the video, so draw them opaque after the punch
    d = ImageDraw.Draw(img)
    cam = (5, 6, 7, 255)
    if camera == "punch-hole":
        cx, cy, r = sx0 + scr_w / 2, sy0 + 42, 13
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=cam)
    elif camera == "dynamic-island":
        iw, ih = 128, 36
        ix, iy = sx0 + (scr_w - iw) / 2, sy0 + 22
        d.rounded_rectangle([ix, iy, ix + iw, iy + ih], radius=ih / 2, fill=cam)

    spec = {
        "canvas": [W, H],
        "screen_rect": [sx0, sy0, scr_w, scr_h],
        "screen_radius": screen_radius,
        "source_resolution": [screen_w_px, screen_h_px],
    }
    return img, spec


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--version", default="1.3.0")
    ap.add_argument("--cta", default="pip install ghost-in-the-droid")
    args = ap.parse_args()

    BRAND.mkdir(parents=True, exist_ok=True)

    demos = load_demos()
    for old in BRAND.glob("intro-*.png"):
        old.unlink()
    for slug, name in demos.items():
        intro_card(slug, name, args.version).save(BRAND / f"intro-{slug}.png")
    outro_card(args.version, args.cta).save(BRAND / "outro.png")
    print(f"cards: {len(demos)} intros + outro (slugs from {COPY_YAML.name})")

    frames = {}
    img, spec = device_frame(
        1080, 2400, bezel=16, body_radius=72, screen_radius=56,
        edge_color="#3a3f46", body_color="#14161a", camera="punch-hole",
    )
    img.save(BRAND / "frame-pixel8.png")
    frames["pixel8"] = spec

    img, spec = device_frame(
        1179, 2556, bezel=14, body_radius=112, screen_radius=100,
        edge_color="#4a4a4f", body_color="#1c1c1e", camera="dynamic-island",
    )
    img.save(BRAND / "frame-iphone15pro.png")
    frames["iphone15pro"] = spec

    (BRAND / "frames.json").write_text(json.dumps(frames, indent=2) + "\n")
    print("frames: pixel8 + iphone15pro (+ frames.json)")


if __name__ == "__main__":
    main()
