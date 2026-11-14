"""futoshiki helpers (Futoshiki by HeX, com.hexcorp.futoshiki): a 4x4 number-logic puzzle.

Readable: every digit on the grid (givens and the player's entries) and the timer.
NOT readable: the inequality arrows between cells (drawn only) and which digits are givens: an agent that must
respect the arrows reads them from a screenshot. Supports the 4x4 grid (the layout constants below).
"""
from __future__ import annotations

import re
import time

_PKG = "com.hexcorp.futoshiki"
_X0, _Y0, _PITCH, _N = 103, 530, 171.7, 4  # centre of cell (0,0) and the cell pitch on a 720x1600 screen
_PAD_Y = 1268


def _nodes(device) -> list[dict]:
    out = []
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"text": a.get("text", ""), "bounds": tuple(nums)})
    return out


def _centre(n):
    b = n["bounds"]
    return (b[0] + b[2]) // 2, (b[1] + b[3]) // 2


def _cell_xy(r, c):
    return round(_X0 + c * _PITCH), round(_Y0 + r * _PITCH)


def read_grid(device) -> dict:
    nodes = _nodes(device)
    grid = [[0] * _N for _ in range(_N)]
    found = 0
    for n in nodes:
        x, y = _centre(n)
        if re.fullmatch(r"[1-4]", n["text"]) and 440 < y < 1130:
            c, r = round((x - _X0) / _PITCH), round((y - _Y0) / _PITCH)
            if 0 <= r < _N and 0 <= c < _N:
                grid[r][c] = int(n["text"])
                found += 1
    in_game = any(n["text"] == "RESET" for n in nodes)
    timer = next((n["text"] for n in nodes if re.fullmatch(r"\d\d:\d\d", n["text"])), "")
    filled = sum(1 for row in grid for v in row if v)
    complete = filled == _N * _N and all(sorted(row) == [1, 2, 3, 4] for row in grid) and \
        all(sorted(grid[r][c] for r in range(_N)) == [1, 2, 3, 4] for c in range(_N))
    return {"in_game": in_game, "grid": grid, "filled": filled, "timer": timer, "rows_cols_complete": complete}


def _tap_text(device, text: str, delay=1.2):
    n = next((n for n in _nodes(device) if n["text"] == text), None)
    if not n:
        raise RuntimeError(f"{text!r} not on screen")
    device.tap(*_centre(n), delay=delay)


def _confirm(params, what):
    # the CLI parses confirm=yes as a YAML boolean, so True arrives as well as "yes"
    if str(params.get("confirm", "")).lower() not in ("yes", "true", "1"):
        raise RuntimeError(f"{what}: pass confirm=yes")


# ── python_action targets ───────────────────────────────────────────────────

def restart_app(device, params, context):
    device.adb("shell", "am", "force-stop", _PKG)
    time.sleep(0.5)
    return {}


def new_game(device, params, context):
    level = str(params.get("difficulty", "easy")).strip().upper()
    if level not in ("EASY", "MEDIUM", "HARD"):
        raise RuntimeError("difficulty must be easy, medium or hard")
    _tap_text(device, "NEW GAME")
    _tap_text(device, "4 x 4", delay=0.6)
    _tap_text(device, level, delay=0.6)
    _tap_text(device, "START", delay=2.5)
    st = read_grid(device)
    for _ in range(12):  # the grid is generated after START; wait until it is shown
        if st["in_game"] and st["filled"] >= 3:
            break
        time.sleep(1.0)
        st = read_grid(device)
    return {"difficulty": level.lower(), "state": st}


def place(device, params, context):
    r, c, d = int(params["row"]), int(params["col"]), int(params["digit"])
    if not (1 <= r <= _N and 1 <= c <= _N and 1 <= d <= _N):
        raise RuntimeError("row, col and digit must be 1-4")
    before = read_grid(device)
    if not before["in_game"]:
        raise RuntimeError("no game running: run new_game first")
    device.tap(*_cell_xy(r - 1, c - 1), delay=0.5)
    pad = next((n for n in _nodes(device) if n["text"] == str(d) and _centre(n)[1] > 1200), None)
    if not pad:
        raise RuntimeError("number pad not on screen")
    device.tap(*_centre(pad), delay=0.8)
    after = read_grid(device)
    shown = after["grid"][r - 1][c - 1]
    return {"row": r, "col": c, "digit": d, "accepted": shown == d, "cell_now": shown, "before": before, "state": after}


def reset_puzzle(device, params, context):
    _confirm(params, "reset_puzzle clears your entries")
    _tap_text(device, "RESET")
    return {"state": read_grid(device)}


def get_grid(device, params, context):
    return {"state": read_grid(device)}


# ── validators ──────────────────────────────────────────────────────────────

def game_started(device, context) -> bool:
    s = read_grid(device)
    return s["in_game"] and s["filled"] >= 3


def placed(device, context) -> bool:
    r = context.result
    s = read_grid(device)
    was_given = r["before"]["grid"][r["row"] - 1][r["col"] - 1] != 0
    return s["in_game"] and s["grid"][r["row"] - 1][r["col"] - 1] == r["cell_now"] and (r["accepted"] or was_given)


def reset_done(device, context) -> bool:
    return read_grid(device)["in_game"]


def grid_read(device, context) -> bool:
    s = read_grid(device)
    return s["in_game"] and s["grid"] == context.result["state"]["grid"]
