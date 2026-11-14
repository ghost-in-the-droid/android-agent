"""quick-calculation helpers (Quick Calculation, io.github.subhamtyagi.quickcalculation): a timed multiple choice maths game.

Screens: a setup form (operator spinner, timer spinner, two number ranges, Starts Now!), the game (timer, correct/attempts
score, a question, four answer buttons that answer at once, Submit which ends the game) and a results screen. The app keeps
hidden view groups in the accessibility tree, so the results screen is recognised by the DONE! label, not by its nodes.
"""
from __future__ import annotations

import html
import re
import time

_PKG = "io.github.subhamtyagi.quickcalculation"
_OPERATORS = ("Addition", "Subtraction", "Multiplication", "Division", "Addition Series", "Simplification", "Simplification Advance", "Miscellaneous")
_TIMERS = (30, 45, 60, 90, 120, 300, 600)


def _nodes(device) -> list[dict]:
    out = []
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"id": a.get("resource-id", "").split("/")[-1], "text": html.unescape(a.get("text", "")).strip(),
                        "cls": a.get("class", "").split(".")[-1], "bounds": tuple(nums)})
    return out


def _by(nodes, ident):
    return next((n for n in nodes if n["id"] == ident), None)


def _centre(n):
    b = n["bounds"]
    return (b[0] + b[2]) // 2, (b[1] + b[3]) // 2


def _int(text):
    m = re.search(r"\d+", text or "")
    return int(m.group()) if m else None


def read_state(device, nodes=None) -> dict:
    nodes = nodes if nodes is not None else _nodes(device)
    done = _by(nodes, "resultText")
    if done and "DONE" in done["text"].upper():
        return {"screen": "results", "correct": _int((_by(nodes, "tv_total_correct_result") or {"text": ""})["text"]),
                "attempts": _int((_by(nodes, "tv_total_attempt_result") or {"text": ""})["text"])}
    if _by(nodes, "question") and _by(nodes, "btn_submit"):
        sc = re.search(r"(\d+)\s*/\s*(\d+)", (_by(nodes, "score") or {"text": ""})["text"])
        return {"screen": "game", "question": _by(nodes, "question")["text"], "options": [(_by(nodes, f"button{i}") or {"text": ""})["text"] for i in range(4)],
                "seconds_left": _int((_by(nodes, "timer") or {"text": ""})["text"]), "correct": int(sc.group(1)) if sc else None, "attempts": int(sc.group(2)) if sc else None}
    if _by(nodes, "btn_start"):
        return {"screen": "setup", "operator": (next((n["text"] for n in nodes if n["id"] == "text1"), "")), "ranges": [n["text"] for n in nodes if n["id"].startswith("et_range")]}
    return {"screen": "other"}


def _wait(device, want, tries=12):
    for _ in range(tries):
        st = read_state(device)
        if st["screen"] in (want if isinstance(want, tuple) else (want,)):
            return st
        time.sleep(0.7)
    raise RuntimeError(f"the {want} screen is not on screen")


def _spinner_pick(device, spinner_id: str, label: str):
    sp = _by(_nodes(device), spinner_id)
    device.tap(*_centre(sp), delay=1.0)
    item = next((n for n in _nodes(device) if n["cls"] == "CheckedTextView" and n["text"] == label), None)
    if not item:
        raise RuntimeError(f"{label} is not in the list")
    device.tap(*_centre(item), delay=0.8)


def _answer_one(device, value: str) -> dict:
    before = _wait(device, "game")
    nodes = _nodes(device)
    v = str(value).strip()
    if v.startswith("#") and v[1:].isdigit() and 1 <= int(v[1:]) <= 4:  # "#2" picks the second button
        idx = int(v[1:]) - 1
        value = before["options"][idx]
    else:
        idx = next((i for i, t in enumerate(before["options"]) if t.replace(" ", "") == v.replace(" ", "")), None)
    if idx is None:
        raise RuntimeError(f"{value} is not one of the options {before['options']}")
    device.tap(*_centre(_by(nodes, f"button{idx}")), delay=1.0)  # tapping an option answers at once
    after = _wait(device, ("game", "results"))
    if (after["attempts"] or 0) <= (before["attempts"] or 0):
        time.sleep(0.8)
        after = _wait(device, ("game", "results"))
    feedback = (_by(_nodes(device), "resultText") or {"text": ""})["text"]
    right = (after["correct"] or 0) > (before["correct"] or 0)
    return {"question": before["question"], "chosen": str(value), "correct": right, "feedback": feedback, "next": after}


# ── python_action targets ───────────────────────────────────────────────────

def restart_app(device, params, context):
    device.adb("shell", "am", "force-stop", _PKG)
    time.sleep(0.5)
    return {}


def open_setup(device, params, context):
    return {"state": _wait(device, "setup")}


def start_game(device, params, context):
    operator = str(params.get("operator") or "Addition").strip() or "Addition"
    timer = int(params.get("timer") or 120)
    match = next((o for o in _OPERATORS if o.lower() == operator.lower()), None)
    if not match:
        raise RuntimeError(f"operator must be one of {', '.join(_OPERATORS)}")
    if timer not in _TIMERS:
        raise RuntimeError(f"timer must be one of {', '.join(map(str, _TIMERS))} seconds")
    _wait(device, "setup")
    _spinner_pick(device, "spinner_operator", match)
    _spinner_pick(device, "spinner_timer", str(timer))
    device.tap(*_centre(_by(_nodes(device), "btn_start")), delay=1.8)
    return {"operator": match, "timer": timer, "state": _wait(device, "game")}


def seed_game(device, params, context):
    """Pre-step: make sure a running game is on screen."""
    st = read_state(device)["screen"]
    if st == "results":
        device.tap(*_centre(_by(_nodes(device), "btn_play_again")), delay=1.8)
        _wait(device, "game")
    elif st != "game":
        start_game(device, {}, context)
    return {}


def get_question(device, params, context):
    return {"state": _wait(device, "game")}


def answer(device, params, context):
    value = params.get("value") or ""
    if not str(value).strip() and params.get("option"):
        value = f"#{int(params['option'])}"
    return _answer_one(device, value)


def answer_many(device, params, context):
    vals = [v.strip() for v in str(params.get("values") or "").replace(";", ",").split(",") if v.strip()]
    vals += [f"#{o.strip()}" for o in str(params.get("options") or "").replace(";", ",").split(",") if o.strip()]
    if not 1 <= len(vals) <= 8:
        raise RuntimeError("give 1 to 8 answers: values (answer texts) or options (button positions 1-4), comma separated")
    results = []
    for v in vals:
        r = _answer_one(device, v)
        results.append({"question": r["question"], "chosen": r["chosen"], "correct": r["correct"]})
        if r["next"]["screen"] == "results":
            break
    return {"count": len(results), "right": sum(r["correct"] for r in results), "results": results, "state": read_state(device)}


def finish_game(device, params, context):
    """End the game with Submit and read the results."""
    st = _wait(device, ("game", "results"))
    if st["screen"] == "game":
        device.tap(*_centre(_by(_nodes(device), "btn_submit")), delay=1.5)
    return {"state": _wait(device, "results")}


def seed_result(device, params, context):
    """Pre-step: end on the results screen."""
    if read_state(device)["screen"] != "results":
        seed_game(device, params, context)
        answer(device, {"value": read_state(device)["options"][0]}, context)
        finish_game(device, params, context)
    return {}


def get_result(device, params, context):
    return {"state": _wait(device, "results")}


# ── validators ──────────────────────────────────────────────────────────────

def setup_open(device, context) -> bool:
    return read_state(device)["screen"] == "setup"


def game_started(device, context) -> bool:
    return read_state(device)["screen"] in ("game", "results")


def question_read(device, context) -> bool:
    return read_state(device)["screen"] in ("game", "results") and bool(context.result["state"]["question"])


def answered(device, context) -> bool:
    r = context.result
    return read_state(device)["screen"] in ("game", "results") and "correct" in r


def answered_many(device, context) -> bool:
    r = context.result
    return read_state(device)["screen"] in ("game", "results") and r["count"] == len(r["results"])


def game_finished(device, context) -> bool:
    s = read_state(device)
    return s["screen"] == "results" and s["attempts"] == context.result["state"]["attempts"]


def result_read(device, context) -> bool:
    s = read_state(device)
    return s["screen"] == "results" and s["correct"] == context.result["state"]["correct"]
