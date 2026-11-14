"""tic-tac-toe helpers (Dooz, io.github.yamin8000.dooz).

The 3x3 board cells are clickable Views with no text. A free cell is clickable+enabled; an occupied cell
(or every cell once the game is over) is disabled, so occupancy is readable from the accessibility tree.
Player 1 plays X, the computer replies at once with O.

python_action signature: (device, params, context) -> {"data": {...}} (the engine merges "data" into context.result; a bare dict is dropped)
validator signature:     (device, context) -> bool
"""
from __future__ import annotations

import re
import time


def _xml(device) -> str:
    """Plain uiautomator dump: the Portal tree drops the `enabled` attribute that marks occupied cells."""
    try:
        raw = device.adb("exec-out", "uiautomator", "dump", "/dev/tty", timeout=20)
        if "<hierarchy" in raw:
            return raw
    except Exception:
        pass
    return device.dump_xml()


def _nodes(device) -> list[dict]:
    out = []
    for m in re.finditer(r"<node ([^>]*)>", _xml(device)):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"text": a.get("text", ""), "desc": a.get("content-desc", ""), "bounds": tuple(nums),
                        "clickable": a.get("clickable") == "true", "enabled": a.get("enabled") == "true"})
    return out


def _cells(nodes) -> list[dict]:
    """The nine board cells in reading order (index 1-9): clickable ~210 px squares inside y 600-1300."""
    c = [n for n in nodes if n["clickable"] and 190 <= n["bounds"][2] - n["bounds"][0] <= 230
         and 600 <= n["bounds"][1] <= 1100]
    c.sort(key=lambda n: (n["bounds"][1], n["bounds"][0]))
    return c


def read_board(device) -> dict:
    nodes = _nodes(device)
    cells = _cells(nodes)
    texts = [n["text"] for n in nodes]
    result = ""
    for i, t in enumerate(texts):
        if t.startswith("Game's result"):
            result = t.split(":", 1)[1].strip() if ":" in t else ""
            if not result and i + 1 < len(texts):
                result = texts[i + 1]
    difficulty = next((t.split(":", 1)[1].strip() for t in texts if t.startswith("Difficulty")), "")
    free = [i + 1 for i, c in enumerate(cells) if c["enabled"]]
    over = bool(result) and result != "Unknown"
    if over:
        free = []
    return {"free": free, "occupied": [i for i in range(1, 10) if i not in free] if len(cells) == 9 else [],
            "cells": len(cells), "result": result or "Unknown", "game_over": over, "difficulty": difficulty}


def _tap_cell(device, cell: int):
    cells = _cells(_nodes(device))
    if len(cells) != 9:
        raise RuntimeError("board not on screen")
    b = cells[cell - 1]["bounds"]
    device.tap((b[0] + b[2]) // 2, (b[1] + b[3]) // 2, delay=0.4)


def _stable(device) -> dict:
    """Read until two reads agree and the board is not 'busy' (every cell disabled while the computer thinks)."""
    prev = read_board(device)
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        time.sleep(0.5)
        cur = read_board(device)
        busy = cur["cells"] == 9 and not cur["free"] and not cur["game_over"]
        if cur == prev and not busy:
            return cur
        prev = cur
    return prev


# ── python_action targets ───────────────────────────────────────────────────

def tap_new_game(device, params, context):
    btn = [n for n in _nodes(device) if n["clickable"] and n["bounds"][1] > 1300 and n["bounds"][0] > 300]
    if not btn:
        raise RuntimeError("New game button not found")
    b = btn[0]["bounds"]
    device.tap((b[0] + b[2]) // 2, (b[1] + b[3]) // 2, delay=1.0)
    return {}


def play_cell(device, params, context):
    cell = int(params["cell"])
    if not 1 <= cell <= 9:
        raise RuntimeError("cell must be 1-9 (row by row from the top left)")
    before = _stable(device)
    if cell not in before["free"]:
        # the computer sometimes opens the game: report it instead of failing, the agent picks another cell
        return {"data": {"cell": cell, "taken": True, "before": before, "board": before, "computer_cell": None}}
    _tap_cell(device, cell)
    time.sleep(1.0)
    after = _stable(device)
    computer = [c for c in before["free"] if c not in after["free"] and c != cell]
    return {"data": {"cell": cell, "before": before, "board": after, "computer_cell": computer[0] if computer else None}}


def play_cells(device, params, context):
    cells = [int(c) for c in re.findall(r"[1-9]", str(params["cells"]))]
    if not cells:
        raise RuntimeError("no cells 1-9 given")
    before = _stable(device)
    log = []
    for c in cells:
        st = _stable(device)
        if st["game_over"]:
            log.append({"cell": c, "skipped": True, "result": st["result"]})
            break
        if c not in st["free"]:
            log.append({"cell": c, "skipped": True, "taken": True, "result": st["result"]})
            continue
        _tap_cell(device, c)
        time.sleep(1.0)
        after = _stable(device)
        comp = [x for x in st["free"] if x not in after["free"] and x != c]
        log.append({"cell": c, "computer_cell": comp[0] if comp else None, "result": after["result"]})
    return {"data": {"before": before, "moves": log, "board": _stable(device)}}


def undo(device, params, context):
    before = _stable(device)
    btn = next((n for n in _nodes(device) if n["desc"] == "Undo"), None)
    if not btn:
        raise RuntimeError("undo button not found")
    # the node with desc Undo is the icon; its clickable parent is the button around it
    parent = next((n for n in _nodes(device) if n["clickable"] and n["bounds"][0] <= btn["bounds"][0]
                   and n["bounds"][2] >= btn["bounds"][2] and n["bounds"][1] <= btn["bounds"][1]
                   and n["bounds"][3] >= btn["bounds"][3] and n["bounds"][1] > 1300), btn)
    device.tap((parent["bounds"][0] + parent["bounds"][2]) // 2, (parent["bounds"][1] + parent["bounds"][3]) // 2)
    time.sleep(1.0)
    return {"data": {"before": before, "board": _stable(device)}}


def get_board(device, params, context):
    return {"data": {"board": _stable(device)}}


# ── validators ──────────────────────────────────────────────────────────────

def fresh_board(device, context) -> bool:
    b = read_board(device)
    return b["cells"] == 9 and len(b["free"]) in (8, 9) and not b["game_over"]


def cell_played(device, context) -> bool:
    r = context.result
    now = read_board(device)
    if r.get("taken"):
        return r["cell"] not in now["free"]  # a taken cell is reported, nothing was tapped
    return (r["cell"] not in now["free"] and len(now["free"]) <= len(r["before"]["free"]) - 1) or now["game_over"]


def cells_played(device, context) -> bool:
    r = context.result
    done = [m for m in r.get("moves", []) if not m.get("skipped")]
    now = read_board(device)
    if not done:  # every requested cell was already taken or the game was over: reported, not played
        return bool(r.get("moves"))
    return len(now["free"]) <= len(r["before"]["free"]) - len(done)


def undone(device, context) -> bool:
    r = context.result
    now = read_board(device)
    return len(now["free"]) > len(r["before"]["free"]) or r["before"]["game_over"]


def board_read(device, context) -> bool:
    got = context.result.get("board", {})
    now = read_board(device)
    return got.get("cells") == 9 and got.get("free") == now["free"]
