"""dart-checker helpers (Dart Checker, com.DartChecker): an X01 darts scoreboard for physical darts.

Every control has a resource id, so the skill enters each dart (single, double, triple, bull, miss) and reads the
remaining scores, the darts of the current turn and the average straight from the tree.
"""
from __future__ import annotations

import html
import re
import time

_PKG = "com.DartChecker"
_MODES = ("101", "201", "301", "401", "501", "601", "701", "801", "901", "1001")
_KNOWN = {"p1name", "p2name", "p3name", "p4name", "dart1", "dart2", "dart3", "averageSymbol", "average", "dartsymbol", "dartsThrown",
          "doubleButton", "tripleButton", "bull", "missedButton", "continueButton", "undoButton"}


def _nodes(device) -> list[dict]:
    out = []
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"text": html.unescape(a.get("text", "") or a.get("content-desc", "")),
                        "id": a.get("resource-id", "").split("/")[-1], "bounds": tuple(nums)})
    return out


def _centre(n):
    b = n["bounds"]
    return (b[0] + b[2]) // 2, (b[1] + b[3]) // 2


def _by(nodes, ident):
    return next((n for n in nodes if n["id"] == ident), None)


def read_state(device) -> dict:
    nodes = _nodes(device)
    if _by(nodes, "startButton"):
        return {"screen": "setup", "mode": (_by(nodes, "gamemode") or {}).get("text", ""),
                "players": (_by(nodes, "playerCountButton") or {}).get("text", "")}
    if not _by(nodes, "dart1"):
        return {"screen": "other"}
    ints = lambda t: int(t) if re.fullmatch(r"-?\d+", t or "") else None
    cur_name = (_by(nodes, "p1name") or {}).get("text", "")
    cur_score = ints((_by(nodes, "scorePlayer1") or {}).get("text", ""))
    cur_avg = (_by(nodes, "average") or {}).get("text", "")
    # the other players are listed below as plain texts: a name, then "<score>  Ø: <average>"
    texts = [n["text"] for n in nodes if n["text"] and n["id"] not in _KNOWN and not n["id"].startswith(("scorePlayer", "b", "p1", "p2name"))
             and n["id"] not in ("gamemode", "dartsymbol", "averageSymbol")]
    others, messages = [], []
    i = 0
    while i < len(texts):
        mm = re.fullmatch(r"(-?\d+)\s+Ø:\s*(\S+)", texts[i + 1]) if i + 1 < len(texts) else None
        if mm:
            others.append({"name": texts[i], "score": int(mm.group(1)), "average": mm.group(2)})
            i += 2
        else:
            messages.append(texts[i])
            i += 1
    players = [{"name": cur_name, "score": cur_score, "average": cur_avg, "current": True}] + others
    return {"screen": "game", "current_player": cur_name, "players": players, "scores": [p["score"] for p in players],
            "turn_darts": [(_by(nodes, f"dart{i}") or {}).get("text", "") for i in (1, 2, 3)],
            "darts_thrown": ints((_by(nodes, "dartsThrown") or {}).get("text", "")),
            "messages": messages, "game_over": any(p["score"] == 0 for p in players)}


def _key(st: dict):
    """The parts of the state that are stable once a turn has switched (the dart row animates)."""
    return (st.get("screen"), tuple(st.get("scores") or ()), st.get("current_player"))


def _tap_id(device, ident, delay=0.5):
    n = _by(_nodes(device), ident)
    if not n:
        raise RuntimeError(f"{ident} not on screen")
    device.tap(*_centre(n), delay=delay)


# ── python_action targets ───────────────────────────────────────────────────

def restart_app(device, params, context):
    device.adb("shell", "am", "force-stop", _PKG)
    time.sleep(0.5)
    return {}


def new_game(device, params, context):
    mode = str(params.get("mode", "301")).strip()
    players = str(params.get("players", "1")).strip()
    if mode not in _MODES:
        raise RuntimeError(f"mode must be one of {_MODES}")
    if players not in tuple("12345678"):
        raise RuntimeError("players must be 1 to 8")
    for _ in range(10):  # wait for the setup screen after the relaunch
        if read_state(device).get("screen") == "setup":
            break
        time.sleep(0.8)
    # Game: tapping cycles through the modes
    for _ in range(12):
        n = _by(_nodes(device), "gamemode")
        if not n:
            raise RuntimeError("gamemode not on the setup screen")
        if n["text"] == mode:
            break
        device.tap(*_centre(n), delay=0.5)
    else:
        raise RuntimeError(f"could not set the game to {mode}")
    # Players: a dropdown with 1 to 8
    pc = _by(_nodes(device), "playerCountButton")
    if not pc:
        raise RuntimeError("playerCountButton not on the setup screen")
    if pc["text"] != players:
        device.tap(*_centre(pc), delay=0.8)
        opt = next((n for n in _nodes(device) if n["text"] == players and n["id"] == "" and n["bounds"][1] > 200), None)
        if not opt:
            raise RuntimeError(f"player count {players} not offered")
        device.tap(*_centre(opt), delay=0.8)
    _tap_id(device, "startButton", delay=2.0)
    return {"mode": mode, "players": int(players), "state": read_state(device)}


def throw(device, params, context):
    tok = str(params["dart"]).strip().lower()
    before = read_state(device)
    if before.get("screen") != "game":
        raise RuntimeError("no game running: run new_game first")
    m = re.fullmatch(r"([dt]?)(\d{1,2})", tok)
    if tok == "miss":
        _tap_id(device, "missedButton", delay=0.8)
    elif tok in ("bull", "dbull"):
        if tok == "dbull":
            _tap_id(device, "doubleButton", delay=0.3)
        _tap_id(device, "bull", delay=0.8)
    elif m and 1 <= int(m.group(2)) <= 20:
        if m.group(1) == "d":
            _tap_id(device, "doubleButton", delay=0.3)
        elif m.group(1) == "t":
            _tap_id(device, "tripleButton", delay=0.3)
        _tap_id(device, "b" + m.group(2), delay=0.8)
    else:
        raise RuntimeError("dart must be 1-20, d1-d20, t1-t20, bull, dbull or miss")
    time.sleep(1.0)
    return {"dart": tok, "before": before, "state": read_state(device)}


def throw_darts(device, params, context):
    seq = [s for s in re.split(r"[ ,;]+", str(params["darts"]).strip().lower()) if s]
    first = read_state(device)
    done = []
    for tok in seq:
        r = throw(device, {"dart": tok}, context)
        done.append(tok)
    time.sleep(1.0)
    return {"thrown": done, "before": first, "state": read_state(device)}


def end_turn(device, params, context):
    before = read_state(device)
    _tap_id(device, "continueButton", delay=1.0)
    time.sleep(1.0)
    return {"before": before, "state": read_state(device)}


def undo(device, params, context):
    before = read_state(device)
    _tap_id(device, "undoButton", delay=1.0)
    yes = next((n for n in _nodes(device) if n["id"] == "button1"), None)  # "Do you really want to undo the last input?"
    if yes:
        device.tap(*_centre(yes), delay=1.0)
    return {"before": before, "state": read_state(device)}


def get_state(device, params, context):
    return {"state": read_state(device)}


# ── validators ──────────────────────────────────────────────────────────────

def game_started(device, context) -> bool:
    s = read_state(device)
    r = context.result
    return s.get("screen") == "game" and len(s["scores"]) == r["players"] and all(x == int(r["mode"]) for x in s["scores"])


def threw(device, context) -> bool:
    r = context.result
    now = read_state(device)
    return now.get("screen") == "game" and _key(now) == _key(r["state"]) and _key(now) != _key(r["before"])


def darts_thrown(device, context) -> bool:
    r = context.result
    now = read_state(device)
    return _key(now) == _key(r["state"]) and _key(now) != _key(r["before"])


def turn_ended(device, context) -> bool:
    r = context.result
    now = read_state(device)
    return _key(now) == _key(r["state"]) and (now["current_player"] != r["before"]["current_player"]
                                              or (now["darts_thrown"] or 0) > (r["before"]["darts_thrown"] or 0))


def undone(device, context) -> bool:
    r = context.result
    return _key(read_state(device)) == _key(r["state"])


def state_read(device, context) -> bool:
    return _key(read_state(device)) == _key(context.result["state"])
