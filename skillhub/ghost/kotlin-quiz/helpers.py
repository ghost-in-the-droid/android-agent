"""kotlin-quiz helpers (Kotlin Quiz, com.example.kotlinquiz): a 10 question multiple choice quiz about Kotlin, offline.

Screens: a welcome form (a name field and START), the quiz (a question, three options, SUBMIT which becomes GET NEXT
QUESTION) and a result screen (name, score, FINISH). Right and wrong are only shown by colour, so the score on the result
screen is the one readable verdict.
"""
from __future__ import annotations

import html
import re
import time

from gitd.bots.common.adb import input_text_arg

_PKG = "com.example.kotlinquiz"
_OPTS = ("tv_option_one", "tv_option_two", "tv_option_three")


def _nodes(device) -> list[dict]:
    out = []
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"id": a.get("resource-id", "").split("/")[-1], "text": html.unescape(a.get("text", "")).strip(), "bounds": tuple(nums)})
    return out


def _by(nodes, ident):
    return next((n for n in nodes if n["id"] == ident), None)


def _centre(n):
    b = n["bounds"]
    return (b[0] + b[2]) // 2, (b[1] + b[3]) // 2


def read_state(device, nodes=None) -> dict:
    nodes = nodes if nodes is not None else _nodes(device)
    if _by(nodes, "tv_option_one"):
        return {"screen": "quiz", "question": _by(nodes, "tv_question")["text"], "options": [(_by(nodes, i) or {"text": ""})["text"] for i in _OPTS],
                "button": (_by(nodes, "btn_submit") or {"text": ""})["text"]}
    if _by(nodes, "tv_score"):
        score = re.search(r"\d+", _by(nodes, "tv_score")["text"])
        return {"screen": "result", "name": (_by(nodes, "tv_name") or {"text": ""})["text"], "score": int(score.group()) if score else None,
                "text": _by(nodes, "tv_score")["text"]}
    if _by(nodes, "et_name"):
        return {"screen": "welcome", "name": _by(nodes, "et_name")["text"]}
    return {"screen": "other"}


def _wait(device, want, tries=12):
    for _ in range(tries):
        st = read_state(device)
        if st["screen"] in (want if isinstance(want, tuple) else (want,)):
            return st
        time.sleep(0.7)
    raise RuntimeError(f"the {want} screen is not on screen")


def _press(device, ident, delay=1.3):
    device.tap(*_centre(_by(_nodes(device), ident)), delay=delay)


def _answer_one(device, option: int) -> dict:
    if option not in (1, 2, 3):
        raise RuntimeError("option must be 1, 2 or 3")
    before = _wait(device, "quiz")
    _press(device, _OPTS[option - 1], 0.8)
    _press(device, "btn_submit", 1.4)  # SUBMIT shows the colours, the button then reads GET NEXT QUESTION
    _press(device, "btn_submit", 1.5)
    after = _wait(device, ("quiz", "result"))
    return {"question": before["question"], "chosen": before["options"][option - 1], "option": option, "next": after}


# ── python_action targets ───────────────────────────────────────────────────

def restart_app(device, params, context):
    device.adb("shell", "am", "force-stop", _PKG)
    time.sleep(0.5)
    return {}


def start_quiz(device, params, context):
    name = str(params.get("name", "Ghost")).strip() or "Ghost"
    if len(name) > 20:
        raise RuntimeError("name must be at most 20 characters")
    _wait(device, "welcome")
    field = _by(_nodes(device), "et_name")
    device.tap(*_centre(field), delay=0.5)
    device.adb("shell", "input", "keycombination", "KEYCODE_CTRL_LEFT", "KEYCODE_A")
    device.adb("shell", "input", "keyevent", "KEYCODE_DEL")
    device.adb("shell", "input", "text", input_text_arg(name))
    time.sleep(0.5)
    device.adb("shell", "input", "keyevent", "KEYCODE_ENTER")  # hides the keyboard that covers START
    time.sleep(0.8)
    _press(device, "btn_start", 2.0)
    return {"name": name, "state": _wait(device, "quiz")}


def get_question(device, params, context):
    return {"state": _wait(device, "quiz")}


def answer(device, params, context):
    return _answer_one(device, int(params.get("option", 0)))


def answer_many(device, params, context):
    opts = [o for o in str(params.get("options", "")).replace(";", ",").split(",") if o.strip()]
    if not 1 <= len(opts) <= 10:
        raise RuntimeError("options must list 1 to 10 numbers (1, 2 or 3) separated by commas")
    results = []
    for o in opts:
        r = _answer_one(device, int(o))
        results.append({"question": r["question"], "chosen": r["chosen"], "option": r["option"]})
        if r["next"]["screen"] == "result":
            break
    final = read_state(device)
    return {"count": len(results), "results": results, "state": final}


def seed_quiz(device, params, context):
    """Pre-step: make sure a question is on screen."""
    st = read_state(device)["screen"]
    if st == "welcome":
        start_quiz(device, {}, context)
    elif st == "result":
        finish_quiz(device, params, context)
        start_quiz(device, {}, context)
    return {}


def seed_result(device, params, context):
    """Pre-step: end on the result screen (answers all questions with option 1)."""
    if read_state(device)["screen"] == "result":
        return {}
    seed_quiz(device, params, context)
    for _ in range(12):
        if read_state(device)["screen"] == "result":
            break
        _answer_one(device, 1)
    return {}


def get_result(device, params, context):
    return {"state": _wait(device, "result")}


def finish_quiz(device, params, context):
    _wait(device, "result")
    _press(device, "btn_finish", 1.6)
    return {"state": _wait(device, "welcome")}


# ── validators ──────────────────────────────────────────────────────────────

def quiz_started(device, context) -> bool:
    s = read_state(device)
    return s["screen"] == "quiz" and s["question"] == context.result["state"]["question"]


def question_read(device, context) -> bool:
    s = read_state(device)
    return s["screen"] == "quiz" and s["question"] == context.result["state"]["question"] and len(s["options"]) == 3


def answered(device, context) -> bool:
    r = context.result
    s = read_state(device)
    return s["screen"] == r["next"]["screen"] and (s["screen"] != "quiz" or s["question"] != r["question"])


def answered_many(device, context) -> bool:
    r = context.result
    return read_state(device)["screen"] in ("quiz", "result") and r["count"] == len(r["results"])


def result_read(device, context) -> bool:
    s = read_state(device)
    return s["screen"] == "result" and s["score"] == context.result["state"]["score"]


def quiz_finished(device, context) -> bool:
    return read_state(device)["screen"] == "welcome"
