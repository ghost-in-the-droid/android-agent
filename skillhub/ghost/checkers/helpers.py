"""checkers helpers (Checkers, Privacy Friendly, org.secuso.privacyfriendlydame).

HONEST LIMITS: the 32 dark squares are clickable ImageViews with no description and the piece colours are not in the
accessibility tree, so the skill cannot read the position. It can start a game, play moves by square name and read the
turn / game-over text. An agent that needs the position reads it from a screenshot.
Squares use standard names: a1 is the dark bottom-left square, white starts at the bottom (ranks 1-3), the bot is black.

Uses the engine-fixed API: python_action returns a plain dict merged into context.result.
"""
from __future__ import annotations

import html
import re
import time

_ID = "org.secuso.privacyfriendlydame:id/"
_X0, _Y0, _CELL = 4, 154, 89  # board origin and square size at 720 px width


def _nodes(device) -> list[dict]:
    out = []
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"text": a.get("text", ""), "id": a.get("resource-id", ""), "bounds": tuple(nums)})
    return out


def _centre(n):
    b = n["bounds"]
    return (b[0] + b[2]) // 2, (b[1] + b[3]) // 2


def read_turn(device) -> dict:
    nodes = _nodes(device)
    text = next((n["text"] for n in nodes if re.search(r"(turn|win|won|draw|over)", n["text"], re.I) and n["bounds"][1] > 800), "")
    in_game = any(n["text"] == "Checkers" for n in nodes) and not any(n["id"] == _ID + "play_button" for n in nodes) and bool(text)
    text = html.unescape(html.unescape(text))  # the dump double-escapes the apostrophe
    low = text.lower()
    return {"in_game": in_game, "text": text, "white_to_move": low.startswith("white"), "game_over": any(w in low for w in ("win", "won", "draw", "over"))}


def _square_xy(device, sq: str) -> tuple[int, int]:
    m = re.fullmatch(r"([a-h])([1-8])", sq.strip().lower())
    if not m:
        raise RuntimeError(f"bad square {sq!r}: use a1-h8")
    f, r = ord(m.group(1)) - 97, int(m.group(2))
    wm = re.search(r"(\d+)x", device.adb("shell", "wm", "size"))
    k = (int(wm.group(1)) / 720) if wm else 1.0
    return int((_X0 + (f + 0.5) * _CELL) * k), int((_Y0 + (8 - r + 0.5) * _CELL) * k)


def _wait_turn(device, was_white: bool, timeout=12.0) -> dict:
    """After a move: wait for the turn text to flip away and (against the bot) back to white."""
    end = time.monotonic() + timeout
    flipped = False
    t = read_turn(device)
    while time.monotonic() < end:
        t = read_turn(device)
        if t["game_over"]:
            return {"accepted": True, **t}
        if not t["white_to_move"]:
            flipped = True
        elif flipped:
            return {"accepted": True, **t}
        time.sleep(0.5)
    return {"accepted": flipped, **t}


# ── python_action targets ───────────────────────────────────────────────────

def leave_game(device, params, context):
    """BACK out of a running game (the start screen shares the title, so detect the board by the turn text)."""
    if read_turn(device)["in_game"]:
        device.back()
        time.sleep(1.2)
    return {}


def _confirm_overwrite(device):
    """A second new game asks before replacing the resumable board."""
    nodes = _nodes(device)
    title = next((n["text"] for n in nodes if n["id"] == _ID + "alertTitle"), "")
    if title != "Overwrite resumable game?":
        return False
    yes = next((n for n in nodes if n["id"] == "android:id/button1" and n["text"] == "YES"), None)
    if yes is None:
        raise RuntimeError("overwrite confirmation has no YES button")
    device.tap(*_centre(yes), delay=2.0)
    return True


def start(device, params, context):
    opponent = str(params.get("opponent", "bot")).lower()
    if opponent not in ("bot", "human"):
        raise RuntimeError("opponent must be bot or human")
    nodes = _nodes(device)
    label = next((n for n in nodes if n["id"] == _ID + "section_label"), None)
    if label and label["text"].lower() != opponent:
        arrow = next((n for n in nodes if n["id"] == _ID + "arrow_right"), None)
        if arrow:
            device.tap(*_centre(arrow), delay=0.8)
    play = next((n for n in _nodes(device) if n["id"] == _ID + "play_button"), None)
    if not play:
        raise RuntimeError("NEW GAME button not on screen")
    device.tap(*_centre(play), delay=3.0)
    _confirm_overwrite(device)
    return {"data": {"opponent": opponent, "turn": read_turn(device)}}


def move(device, params, context):
    src, dst = str(params["from"]), str(params["to"])
    before = read_turn(device)
    if not before["in_game"]:
        raise RuntimeError("no running game: run new_game first")
    device.tap(*_square_xy(device, src), delay=0.7)
    device.tap(*_square_xy(device, dst), delay=0.8)
    res = _wait_turn(device, before["white_to_move"])
    return {"data": {"from": src.lower(), "to": dst.lower(), "before": before, "result": res}}


def play_moves(device, params, context):
    seq = [s for s in re.split(r"[,\s]+", str(params["moves"]).strip()) if s]
    if not seq:
        raise RuntimeError("no moves given")
    log = []
    before = read_turn(device)
    if not before["in_game"]:
        raise RuntimeError("no running game: run new_game first")
    for mv in seq:
        m = re.fullmatch(r"([a-h][1-8])\W?([a-h][1-8])", mv.lower())
        if not m:
            raise RuntimeError(f"bad move {mv!r}: use c3-b4")
        device.tap(*_square_xy(device, m.group(1)), delay=0.7)
        device.tap(*_square_xy(device, m.group(2)), delay=0.8)
        res = _wait_turn(device, True)
        log.append({"move": mv.lower(), "accepted": res["accepted"], "turn": res["text"]})
        if res["game_over"] or not res["accepted"]:
            break
    return {"data": {"before": before, "log": log, "turn": read_turn(device)}}


def get_turn(device, params, context):
    return {"data": {"turn": read_turn(device)}}


# ── validators ──────────────────────────────────────────────────────────────

def started(device, context) -> bool:
    t = read_turn(device)
    return t["in_game"] and bool(context.result["turn"]["text"])


def moved(device, context) -> bool:
    r = context.result
    now = read_turn(device)
    return (now["in_game"] or now.get("game_over", False)) and bool(r["result"]["text"]) and bool(r["result"].get("accepted"))


def moves_played(device, context) -> bool:
    r = context.result
    requested = [s for s in re.split(r"[,\s]+", str(context.params["moves"]).strip()) if s]
    now = read_turn(device)
    return bool(requested) and (now["in_game"] or now["game_over"]) and len(r["log"]) == len(requested) and all(x.get("accepted") is True for x in r["log"])


def turn_read(device, context) -> bool:
    got = context.result["turn"]
    return got["in_game"] and got["text"] == read_turn(device)["text"] or got["game_over"]
