"""code-word helpers (Code Word, com.peaceray.codeword): a Wordle-style game (secret word, 6 guesses).

Readable: the typed letters (TextViews), the on-screen keyboard, the puzzle seed and the puzzle type/difficulty.
NOT readable: the per-letter feedback (right place / elsewhere / absent): it is only the tile colour. An agent that
needs the feedback reads it from a screenshot (blue = right place, yellow = used elsewhere, grey = not in the word).

Uses the engine-fixed API: python_action returns a plain dict merged into context.result.
"""
from __future__ import annotations

import re
import time

_ID = "com.peaceray.codeword:id/"


def _nodes(device) -> list[dict]:
    out = []
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"text": a.get("text", ""), "id": a.get("resource-id", ""), "cls": a.get("class", ""),
                        "bounds": tuple(nums)})
    return out


def _centre(n):
    b = n["bounds"]
    return (b[0] + b[2]) // 2, (b[1] + b[3]) // 2


def _by(nodes, suffix):
    return [n for n in nodes if n["id"] == _ID + suffix]


def read_board(device) -> dict:
    nodes = _nodes(device)
    keys = _by(nodes, "keyTextView")
    letters = [n for n in _by(nodes, "textView") if 250 < n["bounds"][1] < 1100 and len(n["text"]) == 1]
    rows = {}
    for n in letters:
        rows.setdefault(round((n["bounds"][1] - 286) / 123), []).append(n)
    all_rows = ["".join(x["text"] for x in sorted(v, key=lambda n: n["bounds"][0])) for _k, v in sorted(rows.items())]
    typed = [r for r in all_rows if r.strip()]
    return {"in_game": len(keys) >= 20 and not _by(nodes, "createPuzzleButton"), "word_length": len(all_rows[0]) if all_rows else 0,
            "rows_total": len(all_rows), "typed_rows": typed, "rows_used": len(typed)}


def _press(device, ch: str):
    nodes = _nodes(device)
    key = next((n for n in _by(nodes, "keyTextView") if n["text"].upper() == ch.upper()), None)
    if not key:
        raise RuntimeError(f"key {ch!r} not on the keyboard")
    # the key's FrameLayout is the clickable parent, same centre as its label
    device.tap(*_centre(key), delay=0.25)


def _check_key(device):
    nodes = _nodes(device)
    frames = [n for n in nodes if n["cls"].endswith("FrameLayout") and n["bounds"][1] >= 1380 and not n["text"]]
    chk = max(frames, key=lambda n: n["bounds"][0]) if frames else None
    if not chk:
        raise RuntimeError("submit key not found")
    device.tap(*_centre(chk), delay=1.5)


# ── python_action targets ───────────────────────────────────────────────────

def close_howto(device, params, context):
    """Dismiss the first-run 'How to play' dialog (BACK) when it is showing."""
    nodes = _nodes(device)
    if _by(nodes, "titleTextView") and any(n["text"] == "HOW TO PLAY" for n in nodes):
        device.back()
        time.sleep(1.0)
    return {}


def new_puzzle(device, params, context):
    nodes = _nodes(device)
    info = next((n for n in nodes if n["id"] == _ID + "action_puzzle_info"), None)
    if not info:
        raise RuntimeError("puzzle info button not found")
    device.tap(*_centre(info), delay=1.5)
    btn = _by(_nodes(device), "createPuzzleButton")
    if not btn:
        raise RuntimeError("NEW PUZZLE button not shown")
    device.tap(*_centre(btn[0]), delay=1.5)
    nodes = _nodes(device)
    length = next((n["text"] for n in _by(nodes, "codeLengthPrompt")), "")
    seed = next((n["text"] for n in _by(nodes, "seed")), "")
    play = _by(nodes, "createPuzzleButton")
    if not play:
        raise RuntimeError("PLAY button not shown")
    device.tap(*_centre(play[0]), delay=2.0)
    return {"seed": seed, "setting": length, "board": read_board(device)}


def guess(device, params, context):
    word = re.sub(r"[^A-Za-z]", "", str(params["word"]))
    before = read_board(device)
    if not before["in_game"]:
        raise RuntimeError("no running puzzle: run new_puzzle first")
    for ch in word:
        _press(device, ch)
    time.sleep(0.4)
    _check_key(device)
    time.sleep(1.2)
    after = read_board(device)
    return {"word": word.upper(), "before": before, "board": after, "accepted": after["rows_used"] > before["rows_used"] and after["typed_rows"][-1:] == [word.upper()]}


def get_board(device, params, context):
    return {"board": read_board(device)}


# ── validators ──────────────────────────────────────────────────────────────

def puzzle_ready(device, context) -> bool:
    b = read_board(device)
    return b["in_game"] and b["rows_used"] == 0


def guessed(device, context) -> bool:
    r = context.result
    b = read_board(device)
    return b["in_game"] and r["accepted"] and b["rows_used"] == r["before"]["rows_used"] + 1


def board_read(device, context) -> bool:
    got = context.result["board"]
    return got["in_game"] and got["typed_rows"] == read_board(device)["typed_rows"]
