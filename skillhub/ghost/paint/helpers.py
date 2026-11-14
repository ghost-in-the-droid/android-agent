"""paint helpers (Fossify Paint, org.fossify.paint): a simple offline drawing app.

The canvas is a plain view (no accessibility nodes), so drawing is done by swipes on percent coordinates and the
state is read back from a screenshot (ink coverage and named colour histogram) with Pillow.
Coordinates are percent of the safe canvas area (0,0 = top-left, 100,100 = bottom-right), so they are device independent.
"""
from __future__ import annotations

import io
import re
import subprocess
import time

_ID = "org.fossify.paint:id/"
PALETTE = {"red": (211, 47, 47), "blue": (25, 118, 210), "green": (76, 175, 80),
           "yellow": (251, 192, 45), "orange": (245, 124, 0)}
_REF = dict(PALETTE, darkgreen=(16, 109, 31), black=(0, 0, 0))
_X0, _X1, _Y0, _Y1 = 0.03, 0.97, 0.22, 0.78  # safe drawing area (fractions of the screen), clear of toolbar and slider


def _nodes(device) -> list[dict]:
    out = []
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"text": a.get("text", ""), "id": a.get("resource-id", ""), "cls": a.get("class", ""),
                        "desc": a.get("content-desc", ""), "bounds": tuple(nums)})
    return out


def _centre(n):
    b = n["bounds"]
    return (b[0] + b[2]) // 2, (b[1] + b[3]) // 2


def _size(device):
    from PIL import Image
    return Image.open(io.BytesIO(_shot(device))).size


def _shot(device) -> bytes:
    return subprocess.run(["adb", "-s", device.serial, "exec-out", "screencap", "-p"], capture_output=True,
                          timeout=30).stdout


def _px(device, xp: float, yp: float):
    from PIL import Image
    im = Image.open(io.BytesIO(_shot(device))).convert("RGB")
    w, h = im.size
    return _map(w, h, xp, yp)


def _map(w, h, xp, yp):
    xp = min(max(float(xp), 0.0), 100.0)
    yp = min(max(float(yp), 0.0), 100.0)
    return round(w * (_X0 + (_X1 - _X0) * xp / 100)), round(h * (_Y0 + (_Y1 - _Y0) * yp / 100))


def _pt(device, xp, yp):
    if not hasattr(device, "_paint_wh"):
        try:
            device._paint_wh = _size(device)
        except Exception:
            device._paint_wh = (720, 1600)
    return _map(*device._paint_wh, xp, yp)


def _by_id(nodes, suffix):
    return next((n for n in nodes if n["id"] == _ID + suffix), None)


def canvas_stats(device) -> dict:
    from PIL import Image
    im = Image.open(io.BytesIO(_shot(device))).convert("RGB")
    w, h = im.size
    px = im.load()
    y0, y1 = round(h * _Y0), round(h * _Y1)
    counts = {k: 0 for k in _REF}
    total = ink = 0
    for y in range(y0, y1, 3):
        for x in range(0, w, 3):
            r, g, b = px[x, y]
            total += 1
            if r > 235 and g > 235 and b > 235:
                continue
            ink += 1
            best = min(_REF, key=lambda k: sum((a - c) ** 2 for a, c in zip((r, g, b), _REF[k])))
            if sum((a - c) ** 2 for a, c in zip((r, g, b), _REF[best])) < 60 ** 2 * 3:
                counts[best] += 1
    return {"ink_pct": round(100 * ink / total, 2) if total else 0.0,
            "colours": {k: round(100 * v / total, 2) for k, v in counts.items() if v},
            "blank": ink == 0}


def _confirm(params, what):
    # the CLI parses confirm=yes as a YAML boolean, so True arrives as well as "yes"
    if str(params.get("confirm", "")).lower() not in ("yes", "true", "1"):
        raise RuntimeError(f"{what}: pass confirm=yes")


# ── python_action targets ───────────────────────────────────────────────────

def clear_canvas(device, params, context):
    _confirm(params, "new_drawing wipes the canvas")
    nodes = _nodes(device)
    btn = _by_id(nodes, "clear")
    if not btn:
        raise RuntimeError("clear button not found")
    device.tap(*_centre(btn), delay=1.0)
    nodes = _nodes(device)
    ok = next((n for n in nodes if n["id"].endswith("button1")), None)
    if ok:  # a confirmation dialog may appear
        device.tap(*_centre(ok), delay=1.0)
    return {"canvas": canvas_stats(device)}


def set_color(device, params, context):
    name = str(params["color"]).strip().lower()
    if name not in PALETTE:
        raise RuntimeError(f"unknown colour {name!r}; use one of {sorted(PALETTE)}")
    nodes = _nodes(device)
    pick = _by_id(nodes, "color_picker")
    if not pick:
        raise RuntimeError("colour button not found")
    device.tap(*_centre(pick), delay=1.2)
    nodes = _nodes(device)
    sw = [n for n in nodes if n["cls"].endswith("ImageView") and n["bounds"][2] - n["bounds"][0] == 56
          and n["bounds"][3] - n["bounds"][1] == 56]
    if len(sw) < 5:
        raise RuntimeError("colour dialog not shown")
    top = min(n["bounds"][1] for n in sw)
    row = sorted((n for n in sw if n["bounds"][1] == top), key=lambda n: n["bounds"][0])[:5]
    device.tap(*_centre(row[list(PALETTE).index(name)]), delay=0.6)
    ok = next((n for n in _nodes(device) if n["id"].endswith("button1")), None)
    if not ok:
        raise RuntimeError("OK button not found")
    device.tap(*_centre(ok), delay=0.8)
    return {"color": name}


def draw_path(device, params, context):
    pts = [tuple(float(v) for v in p.split(",")) for p in str(params["points"]).replace(" ", "").split(";") if p]
    if len(pts) < 2:
        raise RuntimeError("give at least two points like 10,10;50,50")
    before = canvas_stats(device)
    for (xa, ya), (xb, yb) in zip(pts, pts[1:]):
        ax, ay = _pt(device, xa, ya)
        bx, by = _pt(device, xb, yb)
        device.swipe(ax, ay, bx, by, 250, delay=0.3)
    time.sleep(0.5)
    return {"segments": len(pts) - 1, "before": before, "canvas": canvas_stats(device)}


def fill(device, params, context):
    nodes = _nodes(device)
    bucket = _by_id(nodes, "bucket_fill")
    if not bucket:
        raise RuntimeError("bucket tool not found")
    before = canvas_stats(device)
    device.tap(*_centre(bucket), delay=0.6)
    device.tap(*_pt(device, params["x"], params["y"]), delay=1.2)
    after = canvas_stats(device)
    # the bucket stays selected after a fill (the next stroke would flood): toggle it off again
    bucket = _by_id(_nodes(device), "bucket_fill")
    if bucket:
        device.tap(*_centre(bucket), delay=0.6)
    return {"before": before, "canvas": after}


def get_canvas(device, params, context):
    return {"canvas": canvas_stats(device)}


# ── validators ──────────────────────────────────────────────────────────────

def canvas_blank(device, context) -> bool:
    return context.result["canvas"]["blank"] and canvas_stats(device)["blank"]


def colour_set(device, context) -> bool:
    from PIL import Image
    pick = _by_id(_nodes(device), "color_picker")
    if not pick:
        return False
    x, y = _centre(pick)
    # the colour button is drawn as a filled square: its centre shows the active colour
    im = Image.open(io.BytesIO(_shot(device))).convert("RGB")
    want = PALETTE[context.result["color"]]
    got = im.getpixel((min(x + 30, im.size[0] - 1), y))
    return sum((a - c) ** 2 for a, c in zip(got, want)) < 40 ** 2 * 3


def ink_added(device, context) -> bool:
    r = context.result
    return r["canvas"]["ink_pct"] > r["before"]["ink_pct"]


def canvas_read(device, context) -> bool:
    return abs(context.result["canvas"]["ink_pct"] - canvas_stats(device)["ink_pct"]) < 1.0
