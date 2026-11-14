"""game-2048 helpers (2048 Privacy Friendly, org.secuso.privacyfriendly2048).

The 4x4 board is a grid of Buttons: a tile has its number as text; empty cells have none. Points and record are real
text (`id/points`, `id/record`). Moves are swipes on the board. New tiles spawn randomly, so the skill never asserts
the exact board after a move, only the tile sum, the points and the changed layout.

python_action signature: (device, params, context) -> {"data": {...}} (the engine merges "data" into context.result; a bare dict is dropped)
validator signature:     (device, context) -> bool
"""
from __future__ import annotations

import re
import time

_ID = "org.secuso.privacyfriendly2048:id/"


def _nodes(device) -> list[dict]:
    out = []
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"text": a.get("text", ""), "id": a.get("resource-id", ""), "cls": a.get("class", ""),
                        "bounds": tuple(nums)})
    return out


def read_board(device) -> dict:
    nodes = _nodes(device)
    cells = [n for n in nodes if n["cls"].endswith("Button") and 130 <= n["bounds"][2] - n["bounds"][0] <= 170
             and 440 <= n["bounds"][1] <= 1000]
    xs = sorted({n["bounds"][0] for n in cells})
    ys = sorted({n["bounds"][1] for n in cells})
    grid = [[0] * len(xs) for _ in ys]
    for n in cells:
        if n["text"].isdigit():
            grid[ys.index(n["bounds"][1])][xs.index(n["bounds"][0])] = int(n["text"])
    points = next((int(n["text"]) for n in nodes if n["id"] == _ID + "points" and n["text"].isdigit()), None)
    record = next((int(n["text"]) for n in nodes if n["id"] == _ID + "record" and n["text"].isdigit()), None)
    texts = " ".join(n["text"] for n in nodes).lower()
    return {"grid": grid, "size": len(xs), "points": points, "record": record,
            "tile_sum": sum(sum(r) for r in grid), "max_tile": max((max(r) for r in grid), default=0),
            "game_over": "game over" in texts or "no more moves" in texts}


def _swipe(device, direction: str):
    d = direction.lower()[0]
    cx, cy = 360, 770
    dx = {"l": (500, 220), "r": (220, 500)}.get(d)
    if d in ("l", "r"):
        device.swipe(dx[0], cy, dx[1], cy, ms=180, delay=0.7)
    elif d in ("u", "d"):
        y0, y1 = (950, 600) if d == "u" else (600, 950)
        device.swipe(cx, y0, cx, y1, ms=180, delay=0.7)
    else:
        raise RuntimeError("direction must be left, right, up or down")


# ── python_action targets ───────────────────────────────────────────────────

def swipe(device, params, context):
    before = read_board(device)
    if not before["grid"] or before["size"] == 0:
        raise RuntimeError("no running 2048 board: run new_game first")
    _swipe(device, str(params["direction"]))
    time.sleep(0.5)
    return {"data": {"direction": str(params["direction"]).lower(), "before": before, "board": read_board(device)}}


def play_moves(device, params, context):
    seq = [s.strip() for s in re.split(r"[,\s]+", str(params["directions"])) if s.strip()]
    if not seq:
        raise RuntimeError("no directions given")
    before = read_board(device)
    log = []
    for s in seq:
        _swipe(device, s)
        b = read_board(device)
        log.append({"move": s.lower(), "points": b["points"], "tile_sum": b["tile_sum"]})
    return {"data": {"before": before, "moves": log, "board": read_board(device)}}


def get_board(device, params, context):
    return {"data": {"board": read_board(device)}}


def tap_restart(device, params, context):
    btn = next((n for n in _nodes(device) if n["id"] == _ID + "restartButton"), None)
    if not btn:
        raise RuntimeError("restart button not on screen")
    b = btn["bounds"]
    device.tap((b[0] + b[2]) // 2, (b[1] + b[3]) // 2, delay=1.5)
    return {}


# ── validators ──────────────────────────────────────────────────────────────

def fresh_board(device, context) -> bool:
    b = read_board(device)
    return b["size"] == 4 and b["points"] == 0 and b["tile_sum"] in (4, 6, 8)


def swiped(device, context) -> bool:
    r = context.result
    now = read_board(device)
    b0 = r["before"]
    # a legal move spawns a tile (sum grows) and a blocked one changes nothing
    return now["size"] == 4 and now["points"] is not None and now["points"] >= (b0["points"] or 0) and now["tile_sum"] >= b0["tile_sum"]


def moves_played(device, context) -> bool:
    r = context.result
    now = read_board(device)
    return now["size"] == 4 and len(r.get("moves", [])) >= 1 and now["tile_sum"] >= r["before"]["tile_sum"]


def board_read(device, context) -> bool:
    got = context.result.get("board", {})
    now = read_board(device)
    return got.get("size") == 4 and got.get("grid") == now["grid"]
