"""flashcards helpers (Flash Deck, m.co.rh.id.a_flash_deck): offline flashcards with spaced-repetition grading.

Every control has a resource id, so the toolkit is node-driven: add decks and cards, list decks, review due cards
(question, reveal answer, grade again/hard/good/easy). The Gemini/AI generators and import/export are never touched.
"""
from __future__ import annotations

import html
import re
import time

_PKG = "m.co.rh.id.a_flash_deck"
_ID = _PKG + ":id/"
_SAFE = re.compile(r"^[A-Za-z0-9 .,?!'-]{1,80}$")


def _nodes(device) -> list[dict]:
    out = []
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"text": html.unescape(a.get("text", "")), "id": a.get("resource-id", "").replace(_ID, ""),
                        "bounds": tuple(nums)})
    return out


def _centre(n):
    b = n["bounds"]
    return (b[0] + b[2]) // 2, (b[1] + b[3]) // 2


def _get(nodes, ident):
    return next((n for n in nodes if n["id"] == ident), None)


def _tap_id(device, ident, delay=1.0, timeout=6.0):
    end = time.time() + timeout
    while True:
        n = _get(_nodes(device), ident)
        if n:
            device.tap(*_centre(n), delay=delay)
            return
        if time.time() > end:
            raise RuntimeError(f"{ident} not on screen")
        time.sleep(0.5)


def _type(device, ident, text):
    if not _SAFE.match(text):
        raise RuntimeError("text must be 1-80 chars of letters, digits, space and . , ? ! ' -")
    _tap_id(device, ident, delay=0.4)
    device.adb("shell", "input", "text", text.replace(" ", "%s").replace("'", "\\'"))
    time.sleep(0.4)


def go_home(device, params=None, context=None):
    """Land on the Home screen: dismiss the notification prompt, EXIT a review, BACK out of forms."""
    for _ in range(6):
        nodes = _nodes(device)
        if _get(nodes, "button_add_deck") and _get(nodes, "button_add_card"):
            return {}
        if _get(nodes, "text_view_content") and _get(nodes, "button_cancel"):
            device.tap(*_centre(_get(nodes, "button_cancel")), delay=1.0)
        elif _get(nodes, "button_exit"):
            device.tap(*_centre(_get(nodes, "button_exit")), delay=1.0)
        else:
            device.back()
            time.sleep(0.8)
    raise RuntimeError("could not reach the Home screen")


def read_review(device) -> dict:
    nodes = _nodes(device)
    q = _get(nodes, "text_question")
    a = _get(nodes, "text_answer")
    prog = _get(nodes, "text_progress")
    revealed = bool(_get(nodes, "button_grade_good"))
    return {"in_review": bool(q), "question": q["text"] if q else "",
            "answer": a["text"] if (a and revealed) else "", "revealed": revealed,
            "progress": prog["text"] if prog else ""}


def _decks(device) -> list[dict]:
    nodes = _nodes(device)
    names = sorted((n for n in nodes if n["id"] == "text_deck_name"), key=lambda n: n["bounds"][1])
    cards = sorted((n for n in nodes if n["id"] == "text_total_cards"), key=lambda n: n["bounds"][1])
    return [{"deck": n["text"], "cards": int(re.sub(r"\D", "", c["text"]) or 0)} for n, c in zip(names, cards)]


# ── python_action targets ───────────────────────────────────────────────────

def add_deck(device, params, context):
    name = str(params["name"]).strip()
    go_home(device)
    _tap_id(device, "button_add_deck")
    _type(device, "edit_text_name", name)
    _tap_id(device, "button_save")
    time.sleep(0.8)
    go_home(device)
    return {"deck": name, "decks": _list_decks(device)}


def _list_decks(device) -> list[dict]:
    go_home(device)
    _tap_id(device, "button_add_card", delay=1.5)
    decks = _decks(device)
    _tap_id(device, "button_cancel", delay=0.8)
    go_home(device)
    return decks


def list_decks(device, params, context):
    return {"decks": _list_decks(device)}


def add_card(device, params, context):
    deck, q, a = str(params["deck"]).strip(), str(params["question"]).strip(), str(params["answer"]).strip()
    go_home(device)
    before = _list_decks(device)
    if deck not in [d["deck"] for d in before]:
        raise RuntimeError(f"no deck named {deck!r}; decks: {[d['deck'] for d in before]}")
    _tap_id(device, "button_add_card", delay=1.5)
    n = next((n for n in _nodes(device) if n["id"] == "text_deck_name" and n["text"] == deck), None)
    device.tap(*_centre(n), delay=0.6)
    _tap_id(device, "button_ok", delay=1.5)
    _type(device, "text_input_edit_question", q)
    _type(device, "text_input_edit_answer", a)
    _tap_id(device, "menu_save", delay=1.5)
    go_home(device)
    after = _list_decks(device)
    return {"deck": deck, "question": q, "answer": a, "before": before, "decks": after}


def start_review(device, params, context):
    go_home(device)
    nodes = _nodes(device)
    due = _get(nodes, "button_study_due_cards")
    if not due:
        return {"due": 0, "state": {"in_review": False}}
    due_n = int(re.sub(r"\D", "", due["text"]) or 0)
    device.tap(*_centre(due), delay=1.5)
    return {"due": due_n, "state": read_review(device)}


def reveal_answer(device, params, context):
    s = read_review(device)
    if not s["in_review"]:
        raise RuntimeError("no card on screen: run start_review first")
    if not s["revealed"]:
        _tap_id(device, "text_answer", delay=1.0)
    return {"state": read_review(device)}


def grade(device, params, context):
    rating = str(params["rating"]).strip().lower()
    if rating not in ("again", "hard", "good", "easy"):
        raise RuntimeError("rating must be again, hard, good or easy")
    before = read_review(device)
    if not before["in_review"]:
        raise RuntimeError("no card on screen: run start_review first")
    if not before["revealed"]:
        _tap_id(device, "text_answer", delay=1.0)
    _tap_id(device, "button_grade_" + rating, delay=1.5)
    return {"rating": rating, "before": before, "state": read_review(device)}


def get_card(device, params, context):
    return {"state": read_review(device)}


# ── validators ──────────────────────────────────────────────────────────────

def home_shown(device, context) -> bool:
    nodes = _nodes(device)
    return bool(_get(nodes, "button_add_deck"))


def deck_added(device, context) -> bool:
    return context.result["deck"] in [d["deck"] for d in context.result["decks"]]


def card_added(device, context) -> bool:
    r = context.result
    cnt = lambda ds: next((d["cards"] for d in ds if d["deck"] == r["deck"]), 0)
    return cnt(r["decks"]) == cnt(r["before"]) + 1


def decks_listed(device, context) -> bool:
    return isinstance(context.result["decks"], list)


def review_open(device, context) -> bool:
    r = context.result
    return r["due"] == 0 or read_review(device)["in_review"]


def card_revealed(device, context) -> bool:
    return read_review(device)["revealed"]


def graded(device, context) -> bool:
    r = context.result
    s = read_review(device)
    # after the last card the review ends; otherwise the card or the progress changed (AGAIN may repeat the card)
    return (not s["in_review"]) or s["question"] != r["before"]["question"] or s["progress"] != r["before"]["progress"] \
        or r["rating"] == "again"


def card_read(device, context) -> bool:
    return read_review(device) == context.result["state"]
