"""kana-quiz helpers (The Kana Quiz, com.noprestige.kanaquiz): multiple-choice Japanese kana/romaji quiz.

Readable: the question character (lblQuestion), the answer buttons, the running score (lblScore: 'Score: 50.0% / 1 / 2').
The skill never knows the right answer; the calling agent reads the kana and chooses.
"""
from __future__ import annotations

import html
import re
import time

_PKG = "com.noprestige.kanaquiz"
_ID = _PKG + ":id/"


def _nodes(device) -> list[dict]:
    out = []
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"text": html.unescape(a.get("text", "")), "id": a.get("resource-id", ""),
                        "cls": a.get("class", ""), "bounds": tuple(nums)})
    return out


def _centre(n):
    b = n["bounds"]
    return (b[0] + b[2]) // 2, (b[1] + b[3]) // 2


def read_state(device) -> dict:
    nodes = _nodes(device)
    q = next((n["text"] for n in nodes if n["id"] == _ID + "lblQuestion"), "")
    prompt = next((n["text"] for n in nodes if n["id"] == _ID + "lblResponse"), "")
    sc = next((n["text"] for n in nodes if n["id"] == _ID + "lblScore"), "")
    m = re.search(r"([\d.]+)%\s+(\d+)\s*/\s*(\d+)", sc)
    correct, total = (int(m.group(2)), int(m.group(3))) if m else (0, 0)
    choices = [n["text"] for n in nodes if n["cls"].endswith("Button") and n["bounds"][1] >= 600 and n["text"]]
    return {"in_quiz": bool(q), "question": q, "prompt": prompt, "choices": choices, "correct": correct,
            "total": total, "score_pct": float(m.group(1)) if m else None}


def open_quiz(device, params, context):
    """Back out of menu screens until the quiz question is showing."""
    for _ in range(3):
        if read_state(device)["in_quiz"]:
            return {}
        device.back()
        time.sleep(0.8)
    return {}


def get_question(device, params, context):
    return {"state": read_state(device)}


def answer(device, params, context):
    want = str(params["choice"]).strip().lower()
    before = read_state(device)
    if not before["in_quiz"]:
        raise RuntimeError("no quiz on screen")
    btn = next((n for n in _nodes(device) if n["cls"].endswith("Button") and n["bounds"][1] >= 600
                and n["text"].strip().lower() == want), None)
    if not btn:
        raise RuntimeError(f"no answer button {want!r}; choices: {before['choices']}")
    device.tap(*_centre(btn), delay=1.2)
    after = read_state(device)
    return {"picked": want, "was_correct": after["correct"] == before["correct"] + 1,
            "before": before, "state": after}


def get_score(device, params, context):
    s = read_state(device)
    return {"correct": s["correct"], "total": s["total"], "score_pct": s["score_pct"], "state": s}


def quiz_open(device, context) -> bool:
    s = read_state(device)
    return s["in_quiz"] and len(s["choices"]) >= 2


def answered(device, context) -> bool:
    r = context.result
    return read_state(device)["total"] == r["before"]["total"] + 1


def score_read(device, context) -> bool:
    s = read_state(device)
    r = context.result
    return s["correct"] == r["correct"] and s["total"] == r["total"]
