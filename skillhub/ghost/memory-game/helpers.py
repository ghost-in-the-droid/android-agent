"""memory-game helpers (Memo Game, Privacy Friendly, org.secuso.privacyfriendlymemory).

The status line (pairs found, tries, timer, mode, difficulty) is real text; the card faces are images without a
description, so an agent that wants to find pairs reads the faces from a screenshot. Cards are the clickable
ImageViews of the grid (row by row, left to right). The deal is random.

Uses the engine-fixed API: python_action returns a plain dict merged into context.result.
"""
from __future__ import annotations

import re
import time

_ID = "org.secuso.privacyfriendlymemory:id/"


def _nodes(device) -> list[dict]:
    out = []
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"text": a.get("text", ""), "id": a.get("resource-id", ""), "cls": a.get("class", ""),
                        "clickable": a.get("clickable") == "true", "bounds": tuple(nums)})
    return out


def _by(nodes, suffix):
    return [n for n in nodes if n["id"] == _ID + suffix]


def _centre(n):
    b = n["bounds"]
    return (b[0] + b[2]) // 2, (b[1] + b[3]) // 2


def cards(nodes) -> list[dict]:
    """Grid cards in reading order: clickable ImageViews below the status area."""
    c = [n for n in nodes if n["cls"].endswith("ImageView") and n["clickable"] and n["bounds"][1] > 450 and not n["id"]]
    c.sort(key=lambda n: (n["bounds"][1], n["bounds"][0]))
    return c


def read_status(device) -> dict:
    nodes = _nodes(device)
    cs = cards(nodes)

    def t(sfx):
        return next((n["text"] for n in _by(nodes, sfx)), "")
    found = t("player_one_found_value")
    m = re.match(r"(\d+)/(\d+)", found)
    cols = len({n["bounds"][0] for n in cs})
    return {"in_game": bool(_by(nodes, "timerView")), "mode": t("gameModeText"), "difficulty": t("difficultyText"),
            "time": t("timerView"), "pairs_found": int(m.group(1)) if m else None, "pairs_total": int(m.group(2)) if m else None,
            "tries": int(t("player_one_tries_value")) if t("player_one_tries_value").isdigit() else None,
            "cards": len(cs), "columns": cols, "rows": len(cs) // cols if cols else 0}


# ── python_action targets ───────────────────────────────────────────────────

def _answer_quit(device, *, leave):
    """Only answer this app's observed quit-game confirmation."""
    nodes = _nodes(device)
    if not any(n["id"] == "android:id/message" and n["text"] == "Do you want to quit the game?" for n in nodes):
        return False
    button_id, label = ("android:id/button1", "YES") if leave else ("android:id/button2", "NO")
    button = next((n for n in nodes if n["id"] == button_id and n["text"] == label), None)
    if button is None:
        raise RuntimeError("quit-game confirmation is missing the expected button")
    device.tap(*_centre(button), delay=1.2)
    return True


def leave_game(device, params, context):
    """new_game may discard the current board, after the app asks explicitly."""
    if _answer_quit(device, leave=True):
        return {}
    if _by(_nodes(device), "timerView"):
        device.back()
        time.sleep(0.6)
        if not _answer_quit(device, leave=True) and not _by(_nodes(device), "playButton"):
            raise RuntimeError("cannot leave the running game: expected quit confirmation or start screen")
    return {}


def resume_game(device, params, context):
    """Read/flip actions keep the current board when a quit dialog is pending."""
    _answer_quit(device, leave=False)
    return {}


def setup_and_start(device, params, context):
    """On the start screen: pick the difficulty (1-3 stars) and tap NEW GAME."""
    level = int(params.get("difficulty", 1))
    if not 1 <= level <= 3:
        raise RuntimeError("difficulty must be 1 (easy) to 3")
    nodes = _nodes(device)
    bar = _by(nodes, "difficultyBar")
    if bar:
        b = bar[0]["bounds"]
        w = (b[2] - b[0]) / 3
        device.tap(int(b[0] + w * (level - 0.5)), (b[1] + b[3]) // 2, delay=0.6)
    start = _by(_nodes(device), "playButton")
    if not start:
        raise RuntimeError("NEW GAME button not on screen")
    device.tap(*_centre(start[0]), delay=3.0)
    return {"data": {"status": read_status(device)}}


def flip(device, params, context):
    row, col = int(params["row"]), int(params["col"])
    before = read_status(device)
    cs = cards(_nodes(device))
    cols = before["columns"]
    if not cs or not cols or not (1 <= col <= cols and 1 <= row <= before["rows"]):
        raise RuntimeError(f"card ({row},{col}) is not on the board ({before['rows']}x{cols})")
    device.tap(*_centre(cs[(row - 1) * cols + col - 1]), delay=0.9)
    return {"data": {"card": [row, col], "before": before, "status": read_status(device)}}


def flip_two(device, params, context):
    before = read_status(device)
    cs = cards(_nodes(device))
    cols = before["columns"]
    picks = []
    for k in ("first", "second"):
        r, c = (int(x) for x in re.findall(r"\d+", str(params[k]))[:2])
        if not (1 <= c <= cols and 1 <= r <= before["rows"]):
            raise RuntimeError(f"card {k} ({r},{c}) is not on the board ({before['rows']}x{cols})")
        picks.append((r, c))
    for r, c in picks:
        device.tap(*_centre(cs[(r - 1) * cols + c - 1]), delay=0.9)
    time.sleep(1.6)  # a mismatch flips back after about a second
    return {"data": {"cards": picks, "before": before, "status": read_status(device)}}


def status(device, params, context):
    return {"data": {"status": read_status(device)}}


# ── validators ──────────────────────────────────────────────────────────────

def started(device, context) -> bool:
    s = read_status(device)
    return s["in_game"] and s["pairs_found"] == 0 and s["tries"] == 0 and s["cards"] >= 12


def flipped(device, context) -> bool:
    s = read_status(device)
    return s["in_game"] and s["cards"] == context.result["before"]["cards"]


def pair_tried(device, context) -> bool:
    r = context.result
    s = read_status(device)
    return s["in_game"] and s["tries"] == (r["before"]["tries"] or 0) + 1


def status_read(device, context) -> bool:
    got = context.result["status"]
    s = read_status(device)
    return got["in_game"] and got["pairs_total"] == s["pairs_total"] and got["cards"] == s["cards"]
