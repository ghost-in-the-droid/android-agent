"""regex-crossword helpers (Regex Crossword, de.chagemann.regexcrossword): crosswords whose clues are regular expressions.

Readable: level lists, every clue (a regex, as text with its position), every cell (an EditText), the typed
characters and the Verify result dialog. The agent reads the regexes and works out the letters; the skill types and verifies.
Rectangular grids are supported: rows and columns are derived from the cell positions.
"""
from __future__ import annotations

import html
import re
import time

_PKG = "de.chagemann.regexcrossword"
_ID = _PKG + ":id/"


def _nodes(device) -> list[dict]:
    out = []
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"text": html.unescape(a.get("text", "")), "id": a.get("resource-id", "").split("/")[-1],
                        "cls": a.get("class", ""), "bounds": tuple(nums)})
    return out


def _centre(n):
    b = n["bounds"]
    return (b[0] + b[2]) // 2, (b[1] + b[3]) // 2


def _tap_text(device, ident, text, delay=1.2):
    n = next((n for n in _nodes(device) if n["id"] == ident and n["text"] == text), None)
    if not n:
        raise RuntimeError(f"{text!r} not found")
    device.tap(*_centre(n), delay=delay)


def read_puzzle(device) -> dict:
    nodes = _nodes(device)
    cells = sorted((n for n in nodes if n["cls"].endswith("EditText")), key=lambda n: (n["bounds"][1], n["bounds"][0]))
    if not cells:
        return {"in_puzzle": False}
    ys = sorted({n["bounds"][1] for n in cells})
    xs = sorted({n["bounds"][0] for n in cells})
    grid = [["" for _ in xs] for _ in ys]
    for n in cells:
        grid[ys.index(n["bounds"][1])][xs.index(n["bounds"][0])] = n["text"]
    x0, y0 = min(n["bounds"][0] for n in cells), min(n["bounds"][1] for n in cells)
    labels = [n for n in nodes if n["cls"].endswith("TextView") and n["id"] == "" and n["bounds"][1] > 150 and n["text"]]
    top = [n["text"] for n in sorted((n for n in labels if n["bounds"][3] <= y0), key=lambda n: n["bounds"][0])]
    left = [n["text"] for n in sorted((n for n in labels if n["bounds"][2] <= x0 and n["bounds"][3] > y0),
                                      key=lambda n: n["bounds"][1])]
    title = next((n["text"] for n in nodes if n["cls"].endswith("TextView") and n["bounds"][1] < 140 and n["bounds"][0] > 100), "")
    return {"in_puzzle": True, "title": title, "rows": len(ys), "cols": len(xs), "grid": ["".join(c or "." for c in r) for r in grid],
            "column_clues": top, "row_clues": left, "verify_visible": any(n["id"] == "verifyCrosswordButton" for n in nodes)}


def _to_categories(device):
    for _ in range(5):
        nodes = _nodes(device)
        if any(n["id"] == "categoryNameTextView" for n in nodes):
            return
        device.back()
        time.sleep(0.8)
    raise RuntimeError("could not reach the category list")


# ── python_action targets ───────────────────────────────────────────────────

def list_levels(device, params, context):
    _to_categories(device)
    nodes = _nodes(device)
    cats = [n["text"] for n in nodes if n["id"] == "categoryNameTextView"]
    stats = [n["text"] for n in nodes if n["id"] == "levelStatsTextView"]
    return {"categories": [{"name": c, "solved": s} for c, s in zip(cats, stats)]}


def open_level(device, params, context):
    cat, level = str(params["category"]).strip(), str(params["level"]).strip()
    _to_categories(device)
    _tap_text(device, "categoryNameTextView", cat)
    names = [n["text"] for n in _nodes(device) if n["id"] == "levelNameTextView"]
    if level not in names:
        raise RuntimeError(f"no level {level!r} in {cat}; levels: {names}")
    _tap_text(device, "levelNameTextView", level, delay=2.0)
    return {"category": cat, "level": level, "puzzle": read_puzzle(device)}


def get_puzzle(device, params, context):
    return {"puzzle": read_puzzle(device)}


def enter(device, params, context):
    """rows: one string per row separated by '/', e.g. 'AB/CD'. '.' leaves a cell untouched."""
    rows = str(params["rows"]).strip().split("/")
    nodes = _nodes(device)
    cells = sorted((n for n in nodes if n["cls"].endswith("EditText")), key=lambda n: (n["bounds"][1], n["bounds"][0]))
    if not cells:
        raise RuntimeError("no puzzle on screen: run open_level first")
    ys = sorted({n["bounds"][1] for n in cells})
    xs = sorted({n["bounds"][0] for n in cells})
    if len(rows) != len(ys) or any(len(r) != len(xs) for r in rows):
        raise RuntimeError(f"grid is {len(ys)} rows x {len(xs)} columns")
    for n in cells:
        ch = rows[ys.index(n["bounds"][1])][xs.index(n["bounds"][0])]
        if ch == ".":
            continue
        if not re.fullmatch(r"[A-Za-z0-9 ]", ch):
            raise RuntimeError(f"unsupported character {ch!r}")
        device.tap(*_centre(n), delay=0.3)
        device.adb("shell", "input", "keyevent", "KEYCODE_MOVE_END")
        for _ in range(3):
            device.adb("shell", "input", "keyevent", "KEYCODE_DEL")
        device.adb("shell", "input", "text", "%s" if ch == " " else ch.upper())
        time.sleep(0.3)
    return {"typed": "/".join(rows), "puzzle": read_puzzle(device)}


def verify(device, params, context):
    nodes = _nodes(device)
    btn = next((n for n in nodes if n["id"] == "verifyCrosswordButton"), None)
    if not btn:
        raise RuntimeError("Verify button not on screen")
    device.tap(*_centre(btn), delay=1.0)
    title = ""
    for _ in range(5):  # the completion dialog appears a moment after the tap
        nodes = _nodes(device)
        title = next((n["text"] for n in nodes if n["id"] == "alertTitle"), "")
        if title:
            break
        time.sleep(0.8)
    msg = next((n["text"] for n in nodes if n["id"] == "message"), "")
    return {"solved": "complete" in title.lower() or "solved" in msg.lower(), "title": title, "message": msg,
            "dialog_open": bool(title)}


# ── validators ──────────────────────────────────────────────────────────────

def categories_listed(device, context) -> bool:
    return len(context.result["categories"]) >= 2


def level_open(device, context) -> bool:
    return read_puzzle(device).get("in_puzzle", False) and read_puzzle(device)["title"] == context.result["level"]


def puzzle_read(device, context) -> bool:
    return context.result["puzzle"].get("in_puzzle") and read_puzzle(device)["grid"] == context.result["puzzle"]["grid"]


def typed(device, context) -> bool:
    got = read_puzzle(device)["grid"]
    want = context.result["typed"].split("/")
    return all(all(w == "." or w.upper() == g for w, g in zip(wr, gr)) for wr, gr in zip(want, got))


def verified(device, context) -> bool:
    r = context.result
    nodes = _nodes(device)
    open_now = any(n["id"] == "alertTitle" for n in nodes)
    return open_now == r["dialog_open"] and (not r["solved"] or "completed" in r["title"].lower())
