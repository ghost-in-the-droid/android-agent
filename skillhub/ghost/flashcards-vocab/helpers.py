"""flashcards-vocab helpers (FlashCards, com.quchen.flashcard): built-in vocabulary quizzes (emoji to word, word to word).

Flow: folders (Chinese, English, German, ...) -> decks with checkboxes -> Start Selection -> setup (question side, item
count slider) -> Start -> multiple choice questions -> Results (score and every answer). The quiz keeps two question
views stacked; the LAST group in the dump is the one on screen.
"""
from __future__ import annotations

import html
import re
import time

_PKG = "com.quchen.flashcard"
_SLIDER_X0, _SLIDER_X1, _SLIDER_Y = 58, 590, 553


def _nodes(device) -> list[dict]:
    out = []
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"text": html.unescape(a.get("text", "")), "id": a.get("resource-id", "").split("/")[-1],
                        "checked": a.get("checked") == "true", "bounds": tuple(nums)})
    return out


def _centre(n):
    b = n["bounds"]
    return (b[0] + b[2]) // 2, (b[1] + b[3]) // 2


def _by(nodes, ident):
    return next((n for n in nodes if n["id"] == ident), None)


def _group(nodes):
    """Last question group on screen: (question node, [answer nodes])."""
    group = None
    for n in nodes:
        if n["id"] == "tv_question":
            group = (n, [])
        elif n["id"] == "answerTextView" and group is not None:
            group[1].append(n)
    return group


def _rows(nodes):
    labels = sorted((n for n in nodes if n["id"] == "label"), key=lambda n: n["bounds"][1])
    boxes = sorted((n for n in nodes if n["id"] == "selectList"), key=lambda n: n["bounds"][1])
    return labels, boxes


def read_state(device, nodes=None) -> dict:
    nodes = nodes if nodes is not None else _nodes(device)
    prog = _by(nodes, "tv_progress")
    if prog:
        g = _group(nodes)
        m = re.match(r"Question (\d+) / (\d+)", prog["text"])
        side = [n for n in nodes if n["id"] == "tv_questionSide"]
        lst = [n for n in nodes if n["id"] == "tv_listName"]
        return {"screen": "quiz", "number": int(m.group(1)) if m else 0, "total": int(m.group(2)) if m else 0,
                "question_side": side[-1]["text"] if side else "", "deck": lst[-1]["text"] if lst else "",
                "question": g[0]["text"] if g else "", "options": [a["text"] for a in g[1]] if g else []}
    title = _by(nodes, "folderListTitle")
    if title and title["text"] == "Results":
        score = (_by(nodes, "tv_resultScore") or {}).get("text", "")
        m = re.match(r"(\d+) / (\d+)", score)
        return {"screen": "results", "score_text": score, "correct": int(m.group(1)) if m else 0, "total": int(m.group(2)) if m else 0,
                "comment": (_by(nodes, "tv_resultComment") or {}).get("text", "")}
    if title and title["text"] == "Folders":
        return {"screen": "folders", "folders": [n["text"] for n in _labels(nodes)]}
    if _by(nodes, "listsTitle"):
        labels, boxes = _rows(nodes)
        return {"screen": "decks", "folder": _by(nodes, "listsTitle")["text"], "decks": [n["text"] for n in labels]}
    if _by(nodes, "tv_showSide"):
        return {"screen": "setup", "count": (_by(nodes, "numberOfListItemsSliderLabel") or {}).get("text", "")}
    return {"screen": "other"}


def _labels(nodes):
    return sorted((n for n in nodes if n["id"] == "label"), key=lambda n: n["bounds"][1])


def _wait(device, want, tries=12):
    for _ in range(tries):
        st = read_state(device)
        if st["screen"] in (want if isinstance(want, tuple) else (want,)):
            return st
        time.sleep(0.8)
    raise RuntimeError(f"the {want} screen is not on screen")


def _launch(device):
    device.adb("shell", "am", "force-stop", _PKG)
    time.sleep(0.5)
    device.adb("shell", "monkey", "-p", _PKG, "-c", "android.intent.category.LAUNCHER", "1")
    time.sleep(2.5)


def _set_count(device, count: int):
    total = int(_by(_nodes(device), "numberOfListItemsSliderLabel")["text"])
    count = max(1, min(count, total))
    if total == 1:
        return 1
    span = _SLIDER_X1 - _SLIDER_X0

    def x_for(v):
        return int(_SLIDER_X0 + (v - 1) / (total - 1) * span)

    cur = total
    for _ in range(8):
        if cur == count:
            return cur
        device.adb("shell", "input", "swipe", str(x_for(cur)), str(_SLIDER_Y), str(x_for(count)), str(_SLIDER_Y), "500")
        time.sleep(0.8)
        cur = int(_by(_nodes(device), "numberOfListItemsSliderLabel")["text"])
    raise RuntimeError(f"could not set the item count to {count} (slider shows {cur})")


def _pick(options, choice):
    s = str(choice).strip()
    if s.isdigit() and 1 <= int(s) <= len(options):
        return int(s) - 1
    low = [o.lower() for o in options]
    if s.lower() in low:
        return low.index(s.lower())
    raise RuntimeError(f"option not found: {choice!r}; options: {options}")


def _answer_one(device, choice):
    nodes = _nodes(device)
    st = read_state(device, nodes)
    if st["screen"] != "quiz":
        raise RuntimeError("no question on screen")
    g = _group(nodes)
    idx = _pick(st["options"], choice)
    device.tap(*_centre(g[1][idx]), delay=1.0)
    for _ in range(10):
        now = read_state(device)
        if now["screen"] == "results" or (now["screen"] == "quiz" and now["number"] != st["number"]):
            return {"number": st["number"], "question": st["question"], "answered": st["options"][idx], "state": now}
        time.sleep(0.6)
    raise RuntimeError("the quiz did not move on after the answer")


# ── python_action targets ───────────────────────────────────────────────────

def restart_app(device, params, context):
    device.adb("shell", "am", "force-stop", _PKG)
    time.sleep(0.5)
    return {}


def open_decks(device, params, context):
    return {"state": _wait(device, "folders")}


def start_quiz(device, params, context):
    folder = str(params.get("folder", "English")).strip()
    deck = str(params.get("deck", "")).strip()
    count = int(str(params.get("count", 5)) or 5)
    _launch(device)
    st = _wait(device, "folders")
    row = next((n for n in _labels(_nodes(device)) if n["text"].lower() == folder.lower()), None)
    if not row:
        raise RuntimeError(f"folder not found: {folder}; folders: {st['folders']}")
    device.tap(*_centre(row), delay=1.6)
    st = _wait(device, "decks")
    nodes = _nodes(device)
    labels, boxes = _rows(nodes)
    pos = 0 if not deck else next((i for i, n in enumerate(labels) if n["text"].lower() == deck.lower()), -1)
    if pos < 0:
        raise RuntimeError(f"deck not found: {deck}; decks: {st['decks']}")
    device.tap(*_centre(boxes[pos]), delay=0.8)
    device.tap(*_centre(_by(_nodes(device), "startBtn")), delay=1.6)
    _wait(device, "setup")
    shown = _set_count(device, count)
    device.tap(*_centre(_by(_nodes(device), "startBtn")), delay=2.0)
    q = _wait(device, "quiz")
    return {"folder": folder, "deck": labels[pos]["text"], "count": shown, "state": q}


def get_question(device, params, context):
    st = _wait(device, "quiz")
    return {"number": st["number"], "total": st["total"], "question": st["question"], "options": st["options"],
            "deck": st["deck"], "question_side": st["question_side"], "state": st}


def answer(device, params, context):
    return _answer_one(device, params.get("option", ""))


def answer_many(device, params, context):
    opts = [o.strip() for o in str(params.get("options", "")).split(",") if o.strip()]
    if not 1 <= len(opts) <= 20:
        raise RuntimeError("options must list 1 to 20 choices (numbers 1-4 or texts) separated by commas")
    done = []
    for o in opts:
        if read_state(device)["screen"] != "quiz":
            break
        r = _answer_one(device, o)
        done.append({"number": r["number"], "question": r["question"], "answered": r["answered"]})
    return {"answered": done, "state": read_state(device)}


def get_results(device, params, context):
    st = _wait(device, "results")
    nodes = _nodes(device)
    items, cur = [], None
    for n in nodes:
        if n["id"] == "tv_questionVal":
            cur = {"question": n["text"]}
            items.append(cur)
        elif cur is not None and n["id"] == "tv_correctAnswerVal":
            cur["correct_answer"] = n["text"]
        elif cur is not None and n["id"] == "tv_selectedAnswerVal":
            cur["your_answer"] = n["text"]
    return {"score": st["score_text"], "correct": st["correct"], "total": st["total"], "comment": st["comment"],
            "wrong": items, "state": st}


def ensure_quiz(device, params, context):
    """Pre-step: keep a running quiz, otherwise start a small one."""
    if read_state(device).get("screen") != "quiz":
        start_quiz(device, {"folder": "English", "deck": "Animal Emoji", "count": 3}, context)
    return {}


def ensure_results(device, params, context):
    """Pre-step: end on the results screen (start a 2-question quiz and answer the first option twice)."""
    if read_state(device).get("screen") == "results":
        return {}
    start_quiz(device, {"folder": "English", "deck": "Animal Emoji", "count": 2}, context)
    for _ in range(2):
        _answer_one(device, 1)
    return {}


# ── validators ──────────────────────────────────────────────────────────────

def decks_open(device, context) -> bool:
    return read_state(device).get("screen") == "folders"


def quiz_started(device, context) -> bool:
    r = context.result
    s = read_state(device)
    return s.get("screen") == "quiz" and s["number"] == 1 and s["total"] == r["count"] and len(s["options"]) >= 2


def question_read(device, context) -> bool:
    r = context.result
    s = read_state(device)
    return s.get("screen") == "quiz" and s["question"] == r["question"] and s["options"] == r["options"]


def answered(device, context) -> bool:
    r = context.result
    s = read_state(device)
    return (s.get("screen") == "results") or (s.get("screen") == "quiz" and s["number"] > r["number"])


def answered_many(device, context) -> bool:
    r = context.result
    s = read_state(device)
    return len(r["answered"]) >= 1 and s.get("screen") in ("quiz", "results")


def results_read(device, context) -> bool:
    r = context.result
    return read_state(device).get("screen") == "results" and r["total"] >= 1 and r["correct"] <= r["total"]
