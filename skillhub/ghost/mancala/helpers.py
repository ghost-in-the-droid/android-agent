"""mancala helpers (Mancala by Willie169, com.willie.mancala): a text-console Kalah game for two players on one phone.

The whole game is a console: `outputText` holds the transcript and `inputText` takes a line. Both are readable, so
the board, stores and whose turn it is are parsed from the transcript. Never types `exit` (it quits the app).
"""
from __future__ import annotations

import re
import time

_PKG = "com.willie.mancala"
_ID = _PKG + ":id/"


def _nodes(device) -> list[dict]:
    import html
    out = []
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"text": html.unescape(a.get("text", "")), "id": a.get("resource-id", ""),
                        "bounds": tuple(nums)})
    return out


def _centre(n):
    b = n["bounds"]
    return (b[0] + b[2]) // 2, (b[1] + b[3]) // 2


def _console(device):
    nodes = _nodes(device)
    out = next((n for n in nodes if n["id"] == _ID + "outputText"), None)
    inp = next((n for n in nodes if n["id"] == _ID + "inputText"), None)
    return (out["text"] if out else None), inp


def _send(device, line: str):
    _out, inp = _console(device)
    if not inp:
        raise RuntimeError("Mancala console not on screen (refusing to type anywhere else)")
    device.tap(*_centre(inp), delay=0.3)
    device.adb("shell", "input", "text", line)
    device.adb("shell", "input", "keyevent", "66")
    time.sleep(1.0)


def parse_state(text: str | None) -> dict:
    if not text:
        return {"in_game": False}
    started = text.rfind("Game setup:")
    body = text[started:] if started >= 0 else ""
    boards = re.findall(r"Player 2\n((?: *\d+)+) *\n *(\d+) +(\d+) *\n((?: *\d+)+) *\nPlayer 1", body)
    if not boards:
        return {"in_game": False, "awaiting_setup": True}
    top, left, right, bottom = boards[-1]
    p2 = [int(v) for v in top.split()]
    p1 = [int(v) for v in bottom.split()]
    after = body[body.rfind("Player 1\n"):]
    turn = re.findall(r"Player ([12]), choose a pit \(1-(\d+)\)", body)
    ended = re.search(r"[^\n]*(?:wins|[Tt]ie|Game over)[^\n]*", after)
    game_over = bool(ended) and "choose a pit" not in after[ended.end():]
    return {"in_game": True, "player2_pits": p2, "player1_pits": p1, "player2_store": int(left),
            "player1_store": int(right), "to_move": int(turn[-1][0]) if turn else None,
            "pits_each": len(p1), "game_over": game_over, "result": ended.group(0).strip() if game_over else ""}


def read_state(device) -> dict:
    return parse_state(_console(device)[0])


# ── python_action targets ───────────────────────────────────────────────────

def restart_app(device, params, context):
    device.adb("shell", "am", "force-stop", _PKG)
    time.sleep(0.5)
    return {}


def new_game(device, params, context):
    pits = int(params.get("pits", 6))
    seeds = int(params.get("seeds", 4))
    out, _ = _console(device)
    if out is None:
        raise RuntimeError("Mancala console not on screen")
    _send(device, str(pits))
    _send(device, str(seeds))
    return {"pits": pits, "seeds": seeds, "state": read_state(device)}


def move(device, params, context):
    pit = int(params["pit"])
    before = read_state(device)
    if not before.get("in_game"):
        raise RuntimeError("no game running: run new_game first")
    if before["game_over"]:
        raise RuntimeError(f"game is over: {before['result']}")
    if not 1 <= pit <= before["pits_each"]:
        raise RuntimeError(f"pit must be 1-{before['pits_each']}")
    _send(device, str(pit))
    after = read_state(device)
    if after == before:
        raise RuntimeError(f"pit {pit} was rejected (empty pit or not your move)")
    return {"pit": pit, "player": before["to_move"], "before": before, "state": after,
            "extra_turn": after["to_move"] == before["to_move"] and not after["game_over"]}


def play_moves(device, params, context):
    seq = [int(p) for p in re.split(r"[ ,;]+", str(params["pits"]).strip()) if p]
    first = read_state(device)
    played, state = [], first
    for pit in seq:
        if state.get("game_over"):
            break
        _send(device, str(pit))
        nxt = read_state(device)
        if nxt == state:
            raise RuntimeError(f"pit {pit} was rejected after {len(played)} moves (empty pit or not your move)")
        played.append({"pit": pit, "player": state["to_move"]})
        state = nxt
    return {"played": played, "before": first, "state": state}


def get_state(device, params, context):
    return {"state": read_state(device)}


# ── validators ──────────────────────────────────────────────────────────────

def game_ready(device, context) -> bool:
    s = read_state(device)
    r = context.result
    return s.get("in_game") and s["pits_each"] == r["pits"] and sum(s["player1_pits"]) == r["pits"] * r["seeds"]


def moved(device, context) -> bool:
    r = context.result
    s = read_state(device)
    return s.get("in_game") and s == r["state"] and (r["state"]["to_move"] != r["player"] or r["extra_turn"]
                                                      or r["state"]["game_over"])


def played(device, context) -> bool:
    r = context.result
    return len(r["played"]) >= 1 and read_state(device) == r["state"]


def state_read(device, context) -> bool:
    return read_state(device) == context.result["state"]
