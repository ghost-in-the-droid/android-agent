"""connect-four helpers (ConnectFour Studio, io.github.patrickric.connectfourstudio).

The board is drawn on a canvas (not in the accessibility tree); the status line, move counter and
side to move are real TextViews. The engine plays perfectly and deterministically (opening book),
so the same moves always get the same replies.

python_action signature: (device, params, context) -> {"data": {...}} (the engine merges "data" into context.result; a bare dict is dropped)
validator signature:     (device, context) -> bool
"""
from __future__ import annotations

import re
import time

_ID = "io.github.patrickric.connectfourstudio:id/"


def visible_nodes(device) -> list[dict]:
    out: list[dict] = []
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"text": a.get("text", ""), "desc": a.get("content-desc", ""), "id": a.get("resource-id", ""), "bounds": tuple(nums)})
    return out


def read_state(device) -> dict:
    nodes = visible_nodes(device)
    status = next((n["text"] for n in nodes if n["id"] == _ID + "status"), "")
    to_move = next((n["text"] for n in nodes if n["id"] == _ID + "turn_text"), "")
    move = None
    for lab in (n for n in nodes if n["text"] == "Move:"):
        cy = (lab["bounds"][1] + lab["bounds"][3]) // 2
        for n in nodes:
            if n["bounds"][0] > lab["bounds"][2] - 5 and n["bounds"][1] <= cy <= n["bounds"][3] and n["text"].isdigit():
                move = int(n["text"])
    return {"move": move, "status": status, "to_move": to_move}


def _screen(device) -> tuple[int, int]:
    m = re.search(r"(\d+)x(\d+)", device.adb("shell", "wm", "size"))
    return (int(m.group(1)), int(m.group(2))) if m else (720, 1600)


def _drop(device, col: int):
    w, h = _screen(device)
    # tap inside the board, in the column: x from the 7-column grid, y at ~31% of the screen height (a board row)
    device.tap(int((col - 0.5) / 7 * w), int(h * 0.3125), delay=0.3)


def _stable_state(device) -> dict:
    """Read twice until two reads agree (the labels lag behind the board right after a tap or New)."""
    prev = read_state(device)
    for _ in range(4):
        time.sleep(0.5)
        cur = read_state(device)
        if cur == prev:
            return cur
        prev = cur
    return prev


def _game_over(status: str) -> bool:
    return any(w in status.lower() for w in ("win", "won", "draw", "game over"))


def _wait_reply(device, before_move, timeout=10.0):
    """Poll until the engine has answered (counter +2 and 'Computer played') or the game ended."""
    deadline = time.monotonic() + timeout
    st = read_state(device)
    while time.monotonic() < deadline:
        st = read_state(device)
        if _game_over(st["status"]):
            break
        if (st["status"].startswith("Computer played") and st["move"] is not None
                and before_move is not None and st["move"] >= before_move + 2):
            break
        time.sleep(0.5)
    return _stable_state(device)


# ── python_action targets ───────────────────────────────────────────────────

def play_column(device, params, context):
    col = int(params["column"])
    if not 1 <= col <= 7:
        raise RuntimeError("column must be 1-7")
    before = _stable_state(device)
    _drop(device, col)
    after = _wait_reply(device, before["move"])
    return {"data": {"column": col, "before": before, "state": after}}


def play_moves(device, params, context):
    raw = params["columns"]
    cols = [int(c) for c in re.findall(r"[1-7]", str(raw))]
    if not cols:
        raise RuntimeError("no columns 1-7 given")
    before = _stable_state(device)
    replies = []
    for c in cols:
        prev = _stable_state(device)
        _drop(device, c)
        st = _wait_reply(device, prev["move"])
        replies.append({"column": c, "status": st["status"], "move": st["move"]})
        if not st["status"].startswith("Computer played"):
            break  # game over or no reply
    return {"data": {"columns": cols, "before": before, "replies": replies, "state": read_state(device)}}


def undo(device, params, context):
    before = _stable_state(device)
    # the toolbar arrows are buttons whose content-desc is the arrow itself (XML-escaped as &lt;)
    btn = next((n for n in visible_nodes(device) if n["desc"] in ("<", "&lt;")), None)
    if not btn:
        raise RuntimeError("undo button not found")
    device.tap((btn["bounds"][0] + btn["bounds"][2]) // 2, (btn["bounds"][1] + btn["bounds"][3]) // 2)
    time.sleep(1.0)
    return {"data": {"before": before, "state": _stable_state(device)}}


def get_state(device, params, context):
    return {"data": {"state": read_state(device)}}


# ── validators ──────────────────────────────────────────────────────────────

def fresh_game(device, context) -> bool:
    s = read_state(device)
    return s["move"] == 1 and s["status"].startswith("New game")


def column_played(device, context) -> bool:
    r = context.result
    now = read_state(device)
    # compare the move counter only: the status text carries timings that keep updating
    return (r["state"]["move"] == now["move"] and now["move"] is not None and r["before"]["move"] is not None
            and now["move"] >= r["before"]["move"] + 1 and bool(now["status"]))


def moves_played(device, context) -> bool:
    r = context.result
    now = read_state(device)
    return (bool(r.get("replies")) and r["state"]["move"] == now["move"] and now["move"] is not None
            and now["move"] >= r["before"]["move"] + len(r["replies"]))


def state_read(device, context) -> bool:
    now = read_state(device)
    return context.result.get("state", {}).get("move") == now["move"] and now["move"] is not None


def undone(device, context) -> bool:
    r = context.result
    now = read_state(device)
    return (r["state"]["move"] == now["move"] and r["before"]["move"] is not None and now["move"] is not None
            and now["move"] < r["before"]["move"])
