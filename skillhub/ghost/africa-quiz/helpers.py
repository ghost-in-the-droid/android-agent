"""africa-quiz helpers (Africa Quiz, com.mufradat.africaquiz): a 10 question quiz on the capitals of African countries.

Every question, option, the score and the final answer review are plain text, so an agent can play a full round and
read the review. The app has a 15 second countdown per question; a question that times out is skipped.
"""
from __future__ import annotations

import html
import re
import time

_PKG = "com.mufradat.africaquiz"


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
    nodes = [n for n in _nodes(device) if n["text"]]
    texts = [n["text"] for n in nodes]
    if "Quiz Complete!" in texts:
        return _results(nodes)
    qn = next((re.fullmatch(r"Question (\d+)/(\d+)", t) for t in texts if re.fullmatch(r"Question (\d+)/(\d+)", t)), None)
    if qn:
        score = next((int(t.split(":")[1]) for t in texts if re.fullmatch(r"Score: \d+", t)), 0)
        body = sorted((n for n in nodes if n["bounds"][1] > 790), key=lambda n: n["bounds"][1])
        prompt = " ".join(n["text"] for n in body if n["bounds"][1] < 940)
        options = [n["text"] for n in body if n["bounds"][1] >= 950]
        return {"screen": "question", "number": int(qn.group(1)), "of": int(qn.group(2)), "score": score,
                "question": prompt, "options": options}
    if "Start Quiz" in texts:
        return {"screen": "start"}
    return {"screen": "other"}


def _results(nodes) -> dict:
    texts = [n["text"] for n in nodes]
    pct = next((t for t in texts if re.fullmatch(r"\d+%", t)), "")
    frac = next((t for t in texts if re.fullmatch(r"\d+/\d+", t)), "")
    review = {}
    cur = None
    for n in sorted(nodes, key=lambda n: n["bounds"][1]):
        t = n["text"]
        m = re.fullmatch(r"(\d+)\. (.+)", t)
        if m and n["bounds"][0] < 100:
            cur = int(m.group(1))
            review[cur] = {"country": m.group(2)}
        elif cur and t.startswith("Correct: "):
            review[cur]["correct"] = t[9:]
        elif cur and t.startswith("Your answer: "):
            review[cur]["your_answer"] = t[13:]
        elif cur and t in ("✓", "✗"):
            review[cur]["right"] = t == "✓"
    return {"screen": "results", "percent": pct, "score": frac, "review": [dict(number=k, **v) for k, v in sorted(review.items())]}


# ── python_action targets ───────────────────────────────────────────────────

def restart_app(device, params, context):
    device.adb("shell", "am", "force-stop", _PKG)
    time.sleep(0.5)
    return {}


def start_quiz(device, params, context):
    for _ in range(10):
        if read_state(device).get("screen") == "start":
            break
        time.sleep(0.8)
    n = _find(_nodes(device), "Start Quiz")
    if not n:
        raise RuntimeError("Start Quiz not on screen")
    device.tap(*_centre(n), delay=2.0)
    return {"state": read_state(device)}


def get_question(device, params, context):
    st = read_state(device)
    if st.get("screen") != "question":
        raise RuntimeError("no question on screen: run start_quiz first")
    return {"state": st}


def _pick(st, option):
    opts = st["options"]
    o = str(option).strip()
    if re.fullmatch(r"[1-4]", o):
        return int(o) - 1
    low = [x.lower() for x in opts]
    if o.lower() in low:
        return low.index(o.lower())
    raise RuntimeError(f"option must be a position 1-4 or one of {opts}")


def _tap_option(device, st, option):
    i = _pick(st, option)
    for _ in range(3):  # a tap during the card transition is ignored: retry until the question number moves
        n = next((n for n in _nodes(device) if n["text"] == st["options"][i]), None)
        if not n:
            break
        device.tap(*_centre(n), delay=1.0)
        for _ in range(4):
            now = read_state(device)
            if now.get("screen") != "question" or now["number"] != st["number"]:
                return st["options"][i]
            time.sleep(0.4)
    return st["options"][i]


def answer(device, params, context):
    before = read_state(device)
    if before.get("screen") != "question":
        raise RuntimeError("no question on screen: run start_quiz first")
    exp = params.get("expect_question")
    if exp not in (None, "") and int(exp) != before["number"]:
        raise RuntimeError(f"the quiz is already on question {before['number']} (the 15 s timer skipped one)")
    chosen = _tap_option(device, before, params["option"])
    return {"chosen": chosen, "before": before, "state": read_state(device)}


def answer_many(device, params, context):
    seq = [s for s in re.split(r"[ ,;]+", str(params["options"]).strip()) if s]
    first = read_state(device)
    chosen = []
    for o in seq:
        for _ in range(6):  # wait for the next card
            st = read_state(device)
            if st.get("screen") == "question":
                break
            time.sleep(0.5)
        if st.get("screen") != "question":
            break
        chosen.append(_tap_option(device, st, o))
    time.sleep(1.0)
    return {"chosen": chosen, "before": first, "state": read_state(device)}


def get_results(device, params, context):
    st = read_state(device)
    if st.get("screen") != "results":
        raise RuntimeError("the quiz is not finished: answer all questions first")
    seen = {r["number"]: r for r in st["review"]}
    for _ in range(8):
        if _find(_nodes(device), "Play Again"):
            break
        device.swipe(360, 1250, 360, 650, 900)  # a slow drag, a fling would skip rows
        time.sleep(0.8)
        nxt = _results([n for n in _nodes(device) if n["text"]])  # the header has scrolled off: parse the rows only
        for r in nxt["review"]:
            seen.setdefault(r["number"], r)
            seen[r["number"]].update({k: v for k, v in r.items() if k not in seen[r["number"]]})
    for _ in range(8):
        device.swipe(360, 400, 360, 1300, 250)
    st["review"] = [seen[k] for k in sorted(seen)]
    return {"state": st}


# ── validators ──────────────────────────────────────────────────────────────

def quiz_started(device, context) -> bool:
    s = read_state(device)
    return s.get("screen") == "question" and s["number"] == 1


def question_read(device, context) -> bool:
    s = read_state(device)
    r = context.result["state"]
    return s.get("screen") == "question" and s["number"] == r["number"] and len(s["options"]) == 4 and bool(s["question"])


def answered(device, context) -> bool:
    r = context.result
    for _ in range(4):
        s = read_state(device)
        if s.get("screen") == "results" or (s.get("screen") == "question" and s["number"] > r["before"]["number"]):
            return True
        time.sleep(0.8)
    return False


def finished(device, context) -> bool:
    s = read_state(device)
    return s.get("screen") == "results"


def results_read(device, context) -> bool:
    r = context.result["state"]
    return read_state(device).get("screen") == "results" and len(r["review"]) == 10 and all("correct" in x for x in r["review"])
