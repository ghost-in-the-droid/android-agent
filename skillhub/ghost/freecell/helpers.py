"""freecell helpers (Open Patience, io.github.d_rk.openpatience).

Cards are real accessibility nodes whose content-desc starts with the card name ("seven of hearts"), so the whole
board can be read: top row = 4 free cells (left) and 4 foundations (right), below it 8 columns. Tapping a card makes the
app move it to the best legal place (a free cell, a foundation or another column); that is the only move primitive.
The deal is random: never assert specific cards.

python_action signature: (device, params, context) -> {"data": {...}} (the engine merges "data" into context.result; a bare dict is dropped)
validator signature:     (device, context) -> bool
"""
from __future__ import annotations

import re
import time

_RANKS = ("ace two three four five six seven eight nine ten jack queen king").split()


def _nodes(device) -> list[dict]:
    out = []
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"text": a.get("text", ""), "desc": a.get("content-desc", "").replace("&#10;", "\n"),
                        "bounds": tuple(nums), "clickable": a.get("clickable") == "true"})
    return out


_CARD = re.compile(r"^(ace|two|three|four|five|six|seven|eight|nine|ten|jack|queen|king) of (clubs|diamonds|hearts|spades)")


def read_board(device) -> dict:
    nodes = _nodes(device)
    cards = [(n, _CARD.match(n["desc"]).group(0)) for n in nodes if _CARD.match(n["desc"])]
    cells, found, cols = [], [], {}
    for n, name in cards:
        x0, y0 = n["bounds"][0], n["bounds"][1]
        if y0 < 290:  # top row: free cells on the left half, foundations on the right
            (cells if x0 < 360 else found).append((x0, name))
        else:
            cols.setdefault(round((x0 - 18) / 87) + 1, []).append((y0, name))
    columns = [[nm for _y, nm in sorted(cols.get(c, []))] for c in range(1, 9)]
    moves = next((int(m.group(1)) for n in nodes for m in [re.match(r"(\d+) moves?", n["desc"] or n["text"])] if m), None)
    clock = next((n["text"] or n["desc"] for n in nodes if re.fullmatch(r"\d\d:\d\d", n["text"] or n["desc"])), "")
    in_game = bool(cards)
    return {"in_game": in_game, "free_cells": [nm for _x, nm in sorted(cells)], "foundations": [nm for _x, nm in sorted(found)],
            "columns": columns, "moves": moves, "time": clock,
            "cards_on_board": sum(len(c) for c in columns) + len(cells)}


def _tap_card(device, name: str) -> dict:
    nodes = _nodes(device)
    hit = [n for n in nodes if n["desc"].startswith(name)]
    if not hit:
        raise RuntimeError(f"card {name!r} not on the board")
    n = max(hit, key=lambda n: n["bounds"][1])  # the visible one is the lowest (top of its pile)
    b = n["bounds"]
    device.tap((b[0] + b[2]) // 2, (b[1] + b[3]) // 2, delay=1.0)
    return n


# ── python_action targets ───────────────────────────────────────────────────

def start_variant(device, params, context):
    """On the FreeCell screen tap Play of the card whose title starts with the variant (Classic / 2 cells / 6 cells)."""
    want = str(params.get("variant", "Classic")).strip().lower()
    nodes = _nodes(device)
    titles = [n for n in nodes if n["desc"].lower().startswith(want)]
    plays = sorted((n for n in nodes if n["desc"] == "Play"), key=lambda n: n["bounds"][1])
    if not titles or not plays:
        raise RuntimeError(f"variant {want!r} not on screen")
    t = titles[0]["bounds"][1]
    play = min(plays, key=lambda p: abs(p["bounds"][1] - (t + 150)))
    b = play["bounds"]
    device.tap((b[0] + b[2]) // 2, (b[1] + b[3]) // 2, delay=3.0)
    return {"data": {"variant": want}}


def tap_card(device, params, context):
    before = read_board(device)
    _tap_card(device, str(params["card"]).strip().lower())
    time.sleep(0.8)
    return {"data": {"card": str(params["card"]).strip().lower(), "before": before, "board": read_board(device)}}


def tap_column(device, params, context):
    col = int(params["column"])
    before = read_board(device)
    cards = before["columns"][col - 1] if 1 <= col <= 8 else []
    if not cards:
        raise RuntimeError(f"column {col} is empty or out of range 1-8")
    _tap_card(device, cards[-1])
    time.sleep(0.8)
    return {"data": {"card": cards[-1], "column": col, "before": before, "board": read_board(device)}}


def tap_undo_redo(device, params, context):
    which = "Redo" if str(params.get("redo", "")).lower() in ("true", "yes", "1") else "Undo"
    before = read_board(device)
    btn = next((n for n in _nodes(device) if n["desc"] == which), None)
    if not btn:
        raise RuntimeError(f"{which} button not on screen")
    b = btn["bounds"]
    device.tap((b[0] + b[2]) // 2, (b[1] + b[3]) // 2, delay=0.8)
    return {"data": {"before": before, "board": read_board(device), "button": which}}


def get_board(device, params, context):
    return {"data": {"board": read_board(device)}}


# ── validators ──────────────────────────────────────────────────────────────

def dealt(device, context) -> bool:
    b = read_board(device)
    return b["in_game"] and b["cards_on_board"] == 52 and b["moves"] == 0


def moved(device, context) -> bool:
    r = context.result
    now = read_board(device)
    return now["in_game"] and now["moves"] is not None and r["before"]["moves"] is not None and now["moves"] >= r["before"]["moves"]


def undone(device, context) -> bool:
    r = context.result
    now = read_board(device)
    return now["in_game"] and now["moves"] == r["board"]["moves"]


def board_read(device, context) -> bool:
    got = context.result.get("board", {})
    now = read_board(device)
    return got.get("in_game") and got.get("columns") == now["columns"] and got.get("free_cells") == now["free_cells"]
