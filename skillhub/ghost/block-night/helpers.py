"""block-night helpers (Block Night by Tiago, pt.tiago.blocknight).

A falling-blocks puzzle: each floor gives a fixed number of pieces and a goal (clear N lines).
The board is drawn on a canvas; the header (pieces left, lines 0 / 2, points) is real text.
Controls: drag to move (about 55 px per cell on a 720 px wide screen), tap to rotate, swipe down to drop.

python_action signature: (device, params, context) -> {"data": {...}} (the engine merges "data" into context.result; a bare dict is dropped)
validator signature:     (device, context) -> bool
"""
from __future__ import annotations

import re
import time


def visible_nodes(device) -> list[dict]:
    out: list[dict] = []
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"text": a.get("text", ""), "desc": a.get("content-desc", ""), "bounds": tuple(nums)})
    return out


def read_progress(device) -> dict:
    """Header of the game screen: floor, pieces left, lines done / goal, points. {} when not in a game."""
    nodes = visible_nodes(device)
    texts = [n["text"] for n in nodes]
    if "left" not in texts:
        return {}
    left_node = next(n for n in nodes if n["text"] == "left")
    left = next((int(n["text"]) for n in nodes if n["text"].isdigit() and n["bounds"][3] <= left_node["bounds"][1] + 5
                 and abs(n["bounds"][0] - left_node["bounds"][0]) < 40), None)
    lines = next((t for t in texts if re.fullmatch(r"\d+ / \d+", t)), "")
    done, goal = (int(x) for x in lines.split(" / ")) if lines else (None, None)
    pts = next((int(m.group(1)) for t in texts for m in [re.search(r"(\d+) points", t)] if m), None)
    floor = next((t for t in texts if re.fullmatch(r"Floor \d+", t)), "")
    return {"floor": floor, "pieces_left": left, "lines": done, "lines_goal": goal, "points": pts}


def _dims(device) -> tuple[int, int]:
    m = re.search(r"(\d+)x(\d+)", device.adb("shell", "wm", "size"))
    return (int(m.group(1)), int(m.group(2))) if m else (720, 1600)


# ── python_action targets ───────────────────────────────────────────────────

def pause_if_running(device, params, context):
    """Record the starting progress (the floor starts falling as soon as Play is tapped)."""
    return {"data": {"start": read_progress(device)}}


def _drop_one(device, mv: str) -> dict:
    """Rotate, drag by the shift (cells) and hard-drop one piece; returns the progress after it locked."""
    w, h = _dims(device)
    cell = w * 55 // 720
    m = re.fullmatch(r"(-?\d+)(?:r(\d+))?", mv)
    if not m:
        raise RuntimeError(f"bad move {mv!r}: use a cell shift like 2, -1, 0 or 2r1 (shift 2, rotate once)")
    shift, rot = int(m.group(1)), int(m.group(2) or 0)
    for _ in range(rot):
        device.tap(w // 2, int(h * 0.55), delay=0.25)
    if shift:
        x0 = w // 2
        device.swipe(x0, int(h * 0.5), x0 + shift * cell, int(h * 0.5), ms=700 + 150 * abs(shift), delay=0.3)
    before = read_progress(device).get("pieces_left")
    prog = {}
    for _attempt in range(3):
        # a drop right after a drag is sometimes swallowed as part of the same gesture: repeat it if nothing locked
        device.swipe(w // 2, int(h * 0.4), w // 2, int(h * 0.75), ms=150, delay=0.8)
        for _ in range(5):
            prog = read_progress(device)
            if not prog or before is None or (prog.get("pieces_left") is not None and prog["pieces_left"] < before):
                break
            time.sleep(0.4)
        else:
            continue
        break
    return prog


def play_pieces(device, params, context):
    """For each entry of params.shifts: rotate (r), drag by N cells, hard drop. e.g. "2,-1,0" or "2r1,-1,0r2"."""
    start = read_progress(device)
    if not start:
        raise RuntimeError("not on a Block Night floor: run start_floor first")
    moves = [s.strip() for s in str(params["shifts"]).split(",") if s.strip()]
    log = [{"move": mv, "progress": _drop_one(device, mv)} for mv in moves]
    return {"data": {"start": start, "moves": log, "progress": read_progress(device)}}


def drop_piece(device, params, context):
    """Move the falling piece params.shift cells (negative = left), rotate params.rotate times, drop it."""
    start = read_progress(device)
    if not start:
        raise RuntimeError("not on a Block Night floor: run start_floor first")
    mv = f"{int(params.get('shift', 0))}r{int(params.get('rotate', 0))}"
    prog = _drop_one(device, mv)
    return {"data": {"start": start, "moves": [{"move": mv, "progress": prog}], "progress": read_progress(device)}}


def hold_piece(device, params, context):
    """Swap the falling piece with the held one (tap the HOLD box)."""
    w, h = _dims(device)
    start = read_progress(device)
    if not start:
        raise RuntimeError("not on a Block Night floor: run start_floor first")
    device.tap(int(w * 0.90), int(h * 0.23), delay=0.8)
    return {"data": {"start": start, "progress": read_progress(device)}}


def get_progress(device, params, context):
    return {"data": {"progress": read_progress(device)}}


# ── validators ──────────────────────────────────────────────────────────────

def floor_started(device, context) -> bool:
    p = read_progress(device)
    return bool(p) and p["pieces_left"] is not None and p["lines_goal"] is not None


def pieces_played(device, context) -> bool:
    r = context.result
    now = read_progress(device)
    if not r.get("moves"):
        return False
    # every dropped piece uses one piece (gravity may lock extra ones); the floor may also have ended
    n = len(r["moves"])
    used = r["start"]["pieces_left"] - (now["pieces_left"] if now else 0)
    return used >= n or not now


def held(device, context) -> bool:
    return bool(read_progress(device))


def progress_read(device, context) -> bool:
    got = context.result.get("progress")
    now = read_progress(device)
    return bool(got) and got.get("lines_goal") == now.get("lines_goal") and got.get("floor") == now.get("floor")
