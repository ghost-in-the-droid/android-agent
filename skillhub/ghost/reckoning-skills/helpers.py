"""reckoning-skills helpers (Reckoning Skills by Privacy Friendly Apps, org.secuso.privacyfriendlyrecknoningskills).

Mental arithmetic trainer, offline. Screens: a first-run tutorial (SKIP), the menu (number range, operators, NEW GAME),
the game (x operator y = ?, an on-screen keypad, progress i/10 and a timer), a Name Input dialog after the tenth answer
and a result screen (solved N of 10 and every problem with the typed answer).
"""
from __future__ import annotations

import html
import re
import time

_PKG = "org.secuso.privacyfriendlyrecknoningskills"
_OPS = {"+": lambda a, b: a + b, "-": lambda a, b: a - b, "−": lambda a, b: a - b, "*": lambda a, b: a * b, "×": lambda a, b: a * b,
        "x": lambda a, b: a * b, "÷": lambda a, b: a // b if b else None, ":": lambda a, b: a // b if b else None, "/": lambda a, b: a // b if b else None}


def _nodes(device) -> list[dict]:
    out = []
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"id": a.get("resource-id", "").split("/")[-1], "text": html.unescape(a.get("text", "")).replace("\n", " ").strip(),
                        "desc": html.unescape(a.get("content-desc", "")), "bounds": tuple(nums)})
    return out


def _by(nodes, ident):
    return next((n for n in nodes if n["id"] == ident), None)


def _centre(n):
    b = n["bounds"]
    return (b[0] + b[2]) // 2, (b[1] + b[3]) // 2


def _solve(x: int, op: str, y: int):
    f = _OPS.get(op)
    return f(x, y) if f else None


def read_state(device, nodes=None) -> dict:
    nodes = nodes if nodes is not None else _nodes(device)
    if _by(nodes, "valuex"):
        x, y, op = _by(nodes, "valuex")["text"], _by(nodes, "valuey")["text"], _by(nodes, "operator")["text"]
        prog = re.search(r"(\d+)/(\d+)", (_by(nodes, "progress") or {"text": ""})["text"])
        given = (_by(nodes, "inputfield") or {"text": ""})["text"]
        return {"screen": "game", "problem": f"{x} {op} {y}", "x": int(x), "op": op, "y": int(y), "given": given,
                "done": int(prog.group(1)) if prog else None, "total": int(prog.group(2)) if prog else None}
    if _by(nodes, "alertTitle") and _by(nodes, "button2"):
        return {"screen": "dialog"}
    if _by(nodes, "solved"):
        rows = []
        for n in sorted(nodes, key=lambda n: n["bounds"][1]):
            m = re.fullmatch(r"(\d+) ([-+*×÷:/−x]) (\d+) = (-?\d+)", n["text"])
            if m:
                x, op, y, given = int(m.group(1)), m.group(2), int(m.group(3)), int(m.group(4))
                rows.append({"problem": f"{x} {op} {y}", "given": given, "correct": _solve(x, op, y) == given})
        solved = re.search(r"Solved (\d+) of (\d+)", _by(nodes, "solved")["text"])
        hs = re.search(r"Highscore (\d+)", (_by(nodes, "score") or {"text": ""})["text"])
        return {"screen": "result", "solved": int(solved.group(1)) if solved else None, "of": int(solved.group(2)) if solved else None,
                "highscore": int(hs.group(1)) if hs else None, "problems": rows}
    if _by(nodes, "button_start_game"):
        return {"screen": "menu"}
    if _by(nodes, "btn_skip"):
        return {"screen": "tutorial"}
    return {"screen": "other"}


def _wait(device, want, tries=14):
    for _ in range(tries):
        st = read_state(device)
        if st["screen"] in (want if isinstance(want, tuple) else (want,)):
            return st
        time.sleep(0.7)
    raise RuntimeError(f"the {want} screen is not on screen")


def _press(device, ident, delay=0.5):
    device.tap(*_centre(_by(_nodes(device), ident)), delay=delay)


def _to_menu(device):
    st = read_state(device)["screen"]
    if st == "tutorial":
        _press(device, "btn_skip", 1.5)
        st = _wait(device, ("menu", "tutorial"))["screen"]
        if st == "tutorial":
            raise RuntimeError("the tutorial did not close")
    elif st == "result":
        fab = max((n for n in _nodes(device) if n["bounds"][1] > 1200 and n["bounds"][0] > 500), key=lambda n: n["bounds"][1], default=None)
        up = fab or next(n for n in _nodes(device) if n["desc"] == "Navigate up")
        device.tap(*_centre(up), delay=1.6)
    _wait(device, "menu")


def _answer_one(device, value: int) -> dict:
    if value < 0 or value > 9999:
        raise RuntimeError("value must be a whole number from 0 to 9999")
    before = _wait(device, "game")
    nodes = _nodes(device)
    for d in str(value):
        device.tap(*_centre(_by(nodes, f"calcbutton_0{d}")), delay=0.25)
    device.tap(*_centre(_by(_nodes(device), "calcbutton_confirm")), delay=0.9)
    after = _wait(device, ("game", "dialog", "result"))
    if after["screen"] == "dialog":
        device.tap(*_centre(_by(_nodes(device), "button2")), delay=1.5)  # CANCEL: do not store a highscore name
        after = _wait(device, "result")
    return {"problem": before["problem"], "given": value, "correct": _solve(before["x"], before["op"], before["y"]) == value, "next": after}


# ── python_action targets ───────────────────────────────────────────────────

def restart_app(device, params, context):
    device.adb("shell", "am", "force-stop", _PKG)
    time.sleep(0.5)
    return {}


def open_menu(device, params, context):
    _wait(device, ("menu", "tutorial"))
    _to_menu(device)
    return {"state": read_state(device)}


def new_game(device, params, context):
    _to_menu(device)
    _press(device, "button_start_game", 1.8)
    return {"state": _wait(device, "game")}


def seed_game(device, params, context):
    """Pre-step: make sure a game problem is on screen."""
    if read_state(device)["screen"] != "game":
        new_game(device, params, context)
    return {}


def get_problem(device, params, context):
    return {"state": _wait(device, "game")}


def answer(device, params, context):
    return _answer_one(device, int(params.get("value", -1)))


def answer_many(device, params, context):
    vals = [v for v in str(params.get("values", "")).replace(";", ",").split(",") if v.strip()]
    if not 1 <= len(vals) <= 10:
        raise RuntimeError("values must list 1 to 10 whole numbers separated by commas")
    results = []
    for v in vals:
        r = _answer_one(device, int(v))
        results.append({"problem": r["problem"], "given": r["given"], "correct": r["correct"]})
        if r["next"]["screen"] == "result":
            break
    return {"count": len(results), "right": sum(r["correct"] for r in results), "results": results, "state": read_state(device)}


def seed_result(device, params, context):
    """Pre-step: end on the result screen (solves the rest of the game correctly)."""
    if read_state(device)["screen"] == "result":
        return {}
    seed_game(device, params, context)
    for _ in range(12):
        st = read_state(device)
        if st["screen"] == "result":
            break
        _answer_one(device, _solve(st["x"], st["op"], st["y"]) or 0)
    return {}


def get_result(device, params, context):
    return {"state": _wait(device, "result")}


# ── validators ──────────────────────────────────────────────────────────────

def menu_open(device, context) -> bool:
    return read_state(device)["screen"] == "menu"


def game_started(device, context) -> bool:
    s = read_state(device)
    return s["screen"] == "game" and s["problem"] == context.result["state"]["problem"]


def answered(device, context) -> bool:
    r = context.result
    return read_state(device)["screen"] == r["next"]["screen"]


def answered_many(device, context) -> bool:
    r = context.result
    return read_state(device)["screen"] in ("game", "result") and r["count"] == len(r["results"])


def result_read(device, context) -> bool:
    s = read_state(device)
    return s["screen"] == "result" and s["solved"] == context.result["state"]["solved"]
