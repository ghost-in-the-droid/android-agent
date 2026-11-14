"""sgt-puzzles helpers (Simon Tatham's Puzzles, name.boyle.chris.sgtpuzzles).

The puzzle itself is drawn on a canvas; the app shows only a status line (`id/status_bar`), the puzzle title and menus.
The skill is built around Net (rotate tiles until every tile is connected to the centre); open_puzzle can open any
other puzzle of the list by its name, but tap_tile assumes a square grid of params.size x params.size tiles.

python_action signature: (device, params, context) -> {"data": {...}} (the engine merges "data" into context.result; a bare dict is dropped)
validator signature:     (device, context) -> bool
"""
from __future__ import annotations

import re
import time

_ID = "name.boyle.chris.sgtpuzzles:id/"


def visible_nodes(device) -> list[dict]:
    out = []
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"text": a.get("text", ""), "desc": a.get("content-desc", ""), "id": a.get("resource-id", ""),
                        "bounds": tuple(nums)})
    return out


def _dims(device):
    m = re.search(r"(\d+)x(\d+)", device.adb("shell", "wm", "size"))
    return (int(m.group(1)), int(m.group(2))) if m else (720, 1600)


def read_state(device) -> dict:
    nodes = visible_nodes(device)
    title = next((n["text"] for n in nodes if n["bounds"][1] < 160 and n["text"] and n["text"] != "Puzzles"), "")
    status = next((n["text"] for n in nodes if n["id"] == _ID + "status_bar"), "")
    on_list = any(n["id"] == _ID + "games_starred" for n in nodes)
    m = re.search(r"Active: (\d+)/(\d+)", status)
    return {"screen": "list" if on_list else "puzzle", "puzzle": title if not on_list else "", "status": status,
            "active": int(m.group(1)) if m else None, "total": int(m.group(2)) if m else None,
            "solved": status.lower().startswith(("solved", "auto-solved")) or (bool(m) and m.group(1) == m.group(2))}


def _menu(device, which: str, item: str):
    """Open the toolbar menu `which` (game_menu or type_menu) and tap the entry with text `item`."""
    nodes = visible_nodes(device)
    btn = next((n for n in nodes if n["id"] == _ID + which), None)
    if not btn:
        raise RuntimeError(f"{which} not on screen: open a puzzle first")
    b = btn["bounds"]
    device.tap((b[0] + b[2]) // 2, (b[1] + b[3]) // 2, delay=1.0)
    row = next((n for n in visible_nodes(device) if n["text"] == item), None)
    if not row:
        device.back()
        raise RuntimeError(f"menu entry {item!r} not found")
    rb = row["bounds"]
    device.tap((rb[0] + rb[2]) // 2, (rb[1] + rb[3]) // 2, delay=1.5)


# ── python_action targets ───────────────────────────────────────────────────

def open_by_name(device, params, context):
    """From the puzzle list, open the puzzle whose entry text starts with params.name (default Net)."""
    want = str(params.get("name", "Net")).strip().lower()
    for _ in range(8):
        nodes = visible_nodes(device)
        row = next((n for n in nodes if n["id"] == _ID + "text" and n["text"].lower().startswith(want + ":")), None)
        if row:
            b = row["bounds"]
            device.tap((b[0] + b[2]) // 2, (b[1] + b[3]) // 2, delay=2.5)
            return {"data": {"opened": params.get("name", "Net")}}
        _w, h = _dims(device)
        device.swipe(360, int(h * 0.75), 360, int(h * 0.3), ms=400, delay=0.6)
    raise RuntimeError(f"puzzle {params.get('name')!r} not found in the list")


def menu_new_game(device, params, context):
    if str(params.get("type", "")).strip():
        _menu(device, "type_menu", str(params["type"]).strip())  # picking a type also generates a new board
        return {"data": {"state": read_state(device), "type": str(params["type"]).strip()}}
    _menu(device, "game_menu", "New game")
    return {"data": {"state": read_state(device)}}


def menu_solution(device, params, context):
    _menu(device, "game_menu", "Show solution")
    return {"data": {"state": read_state(device)}}


def menu_restart(device, params, context):
    _menu(device, "game_menu", "Restart")
    return {"data": {"state": read_state(device)}}


def set_type(device, params, context):
    _menu(device, "type_menu", str(params["type"]))
    return {"data": {"state": read_state(device)}}


def tap_tile(device, params, context):
    """Tap tile (row, col) 1-based in a size x size Net grid (rotates it clockwise). The board spans x 10-710, y 410-1105 at 720 px width."""
    size = int(params.get("size", 5))
    row, col, times = int(params["row"]), int(params["col"]), int(params.get("times", 1))
    if not (1 <= row <= size and 1 <= col <= size):
        raise RuntimeError(f"row/col must be 1-{size}")
    w, h = _dims(device)
    sx, sy = w / 720, h / 1600
    cw, ch = 700 * sx / size, 695 * sy / size
    x = int(10 * sx + (col - 0.5) * cw)
    y = int(410 * sy + (row - 0.5) * ch)
    before = read_state(device)
    for _ in range(times):
        device.tap(x, y, delay=0.4)
    time.sleep(0.5)
    return {"data": {"before": before, "state": read_state(device), "tile": [row, col], "times": times}}


def undo_move(device, params, context):
    before = read_state(device)
    btn = next((n for n in visible_nodes(device) if n["desc"] == "Undo"), None)
    if not btn:
        raise RuntimeError("Undo button not on screen")
    b = btn["bounds"]
    device.tap((b[0] + b[2]) // 2, (b[1] + b[3]) // 2, delay=0.8)
    return {"data": {"before": before, "state": read_state(device)}}


def get_state(device, params, context):
    return {"data": {"state": read_state(device)}}


# ── validators ──────────────────────────────────────────────────────────────

def puzzle_open(device, context) -> bool:
    s = read_state(device)
    return s["screen"] == "puzzle" and bool(s["puzzle"])


def new_started(device, context) -> bool:
    s = read_state(device)
    return s["screen"] == "puzzle" and not s["solved"]


def solved(device, context) -> bool:
    return read_state(device)["solved"]


def tile_tapped(device, context) -> bool:
    r = context.result
    s = read_state(device)
    return r.get("state", {}).get("status") == s["status"] and s["screen"] == "puzzle"


def undone(device, context) -> bool:
    s = read_state(device)
    return context.result.get("state", {}).get("status") == s["status"] and s["screen"] == "puzzle"


def state_read(device, context) -> bool:
    return context.result.get("state", {}).get("status") == read_state(device)["status"]
