"""ham-test helpers (Ham Test, com.hazelhope.dubster.hamtest): US amateur radio exam practice questions.

The question id, question text, the four options and the right/wrong feedback are all plain text nodes, so an agent
can open a question pool, read a question, answer it and move on.
"""
from __future__ import annotations

import html
import re
import time

_PKG = "com.hazelhope.dubster.hamtest"
_POOLS = {"technician": "Technician Questions", "general": "General Questions", "extra": "Extra Questions"}
_QID = re.compile(r"^[TGE]\d[A-Z]\d{2}$")


def _nodes(device) -> list[dict]:
    out = []
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"text": html.unescape(a.get("text", "") or a.get("content-desc", "")), "bounds": tuple(nums)})
    return out


def _centre(n):
    b = n["bounds"]
    return (b[0] + b[2]) // 2, (b[1] + b[3]) // 2


def _find(nodes, text):
    return next((n for n in nodes if n["text"] == text), None)


def read_state(device) -> dict:
    nodes = _nodes(device)
    texts = [n["text"] for n in nodes if n["text"]]
    qid = next((t for t in texts if _QID.match(t)), "")
    if not qid:
        if "Study" in texts and any(t in texts for t in _POOLS.values()):
            return {"screen": "menu", "pools": [k for k, v in _POOLS.items() if v in texts]}
        return {"screen": "other"}
    opts = {}
    for t in texts:
        m = re.match(r"^([A-D])\.\s*(.*)$", t, re.S)
        if m:
            opts[m.group(1)] = m.group(2).strip()
    i = texts.index(qid)
    # a short badge (New, Weak, ...) sits between the id and the question: take the longest text before the first option
    first_opt = next((k for k, t in enumerate(texts) if re.match(r"^[A-D]\.\s", t)), len(texts))
    between = [t for t in texts[i + 1:first_opt] if not t.startswith("You've seen")]
    question = max(between, key=len) if between else ""
    seen = next((t for t in texts if t.startswith("You've seen")), "")
    togo = next((t for t in texts if t.endswith("questions to go") or t.endswith("question to go")), "")
    verdict = next((t for t in texts if t in ("Correct!", "Correct", "Wrong.", "Wrong")), "")
    right = next((t for t in texts if t.startswith("The right answer was")), "")
    return {"screen": "question", "pool": {"T": "technician", "G": "general", "E": "extra"}[qid[0]], "id": qid,
            "question": question, "options": opts, "seen": seen, "to_go": togo, "answered": bool(verdict),
            "correct": verdict.startswith("Correct") if verdict else None,
            "right_answer": right.replace("The right answer was", "").strip() if right else ""}


# ── python_action targets ───────────────────────────────────────────────────

def restart_app(device, params, context):
    device.adb("shell", "am", "force-stop", _PKG)
    time.sleep(0.5)
    return {}


def open_quiz(device, params, context):
    pool = str(params.get("pool", "technician")).strip().lower()
    if pool not in _POOLS:
        raise RuntimeError(f"pool must be one of {tuple(_POOLS)}")
    for _ in range(10):
        if read_state(device).get("screen") == "menu":
            break
        time.sleep(0.8)
    n = _find(_nodes(device), _POOLS[pool])
    if not n:
        raise RuntimeError(f"{_POOLS[pool]} not on the Study screen")
    device.tap(*_centre(n), delay=2.0)
    return {"pool": pool, "state": read_state(device)}


def get_question(device, params, context):
    st = read_state(device)
    if st.get("screen") != "question":
        raise RuntimeError("no question on screen: run open_quiz first")
    return {"state": st}


def answer(device, params, context):
    letter = str(params["choice"]).strip().upper()[:1]
    before = read_state(device)
    if before.get("screen") != "question":
        raise RuntimeError("no question on screen: run open_quiz first")
    if before["answered"]:
        raise RuntimeError("this question is already answered: run next_question")
    if letter not in before["options"]:
        raise RuntimeError("choice must be A, B, C or D")
    nodes = _nodes(device)
    opt = next((n for n in nodes if n["text"].startswith(letter + ".")), None)
    device.tap(*_centre(opt), delay=0.8)
    sub = _find(_nodes(device), "Submit")
    if not sub:
        raise RuntimeError("Submit button not on screen")
    device.tap(*_centre(sub), delay=1.5)
    after = read_state(device)
    if after.get("correct") and not after.get("right_answer"):
        after["right_answer"] = letter  # the app only names the right answer after a miss
    return {"choice": letter, "before": before, "state": after}


def next_question(device, params, context):
    before = read_state(device)
    n = _find(_nodes(device), "Next Question")
    if not n:
        raise RuntimeError("Next Question not on screen: answer the question first")
    device.tap(*_centre(n), delay=1.5)
    return {"before": before, "state": read_state(device)}


# ── validators ──────────────────────────────────────────────────────────────

def quiz_open(device, context) -> bool:
    s = read_state(device)
    return s.get("screen") == "question" and s["pool"] == context.result["pool"] and not s["answered"]


def question_read(device, context) -> bool:
    s = read_state(device)
    r = context.result["state"]
    return s.get("screen") == "question" and s["id"] == r["id"] and len(s["options"]) >= 2 and bool(s["question"])


def answered(device, context) -> bool:
    s = read_state(device)
    r = context.result
    return s.get("screen") == "question" and s["id"] == r["before"]["id"] and s["answered"]


def moved_on(device, context) -> bool:
    r = context.result
    for _ in range(5):  # the next card animates in
        s = read_state(device)
        if s.get("screen") == "question" and not s["answered"] and r["before"]["answered"]:
            return True
        time.sleep(1.0)
    return False
