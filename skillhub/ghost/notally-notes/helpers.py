"""notally-notes helpers (Notally, com.omgodse.notally): a minimalist local notes app.

Notes are cards with a title, date and body preview; a note opens in an editor with title and body fields and is
saved when you leave it. Delete goes through the card selection menu (the note moves to the app's trash).
"""
from __future__ import annotations

import html
import re
import time

from gitd.bots.common.adb import input_text_arg

_PKG = "com.omgodse.notally"


def _nodes(device) -> list[dict]:
    out = []
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"text": html.unescape(a.get("text", "") or a.get("content-desc", "")),
                        "id": a.get("resource-id", "").split("/")[-1], "cls": a.get("class", "").split(".")[-1], "bounds": tuple(nums)})
    return out


def _centre(n):
    b = n["bounds"]
    return (b[0] + b[2]) // 2, (b[1] + b[3]) // 2


def _by(nodes, ident):
    return next((n for n in nodes if n["id"] == ident), None)


def _cards(nodes):
    out = []
    for c in sorted((n for n in nodes if n["cls"] == "CardView"), key=lambda n: n["bounds"][1]):
        b = c["bounds"]
        inside = [n for n in nodes if n["bounds"][0] >= b[0] and n["bounds"][2] <= b[2] and n["bounds"][1] >= b[1] and n["bounds"][3] <= b[3] and n is not c]
        pick = lambda i: next((n["text"] for n in inside if n["id"] == i), "")
        out.append({"title": pick("Title"), "body": pick("Note"), "date": pick("Date"), "node": c})
    return out


def read_state(device) -> dict:
    nodes = _nodes(device)
    if _by(nodes, "EnterTitle"):
        return {"screen": "editor", "title": _by(nodes, "EnterTitle")["text"], "body": (_by(nodes, "EnterBody") or {"text": ""})["text"]}
    if _by(nodes, "TakeNote"):
        cards = _cards(nodes)
        return {"screen": "list", "notes": [{"title": c["title"], "body": c["body"], "date": c["date"]} for c in cards]}
    return {"screen": "other"}


def _wait(device, want, tries=10):
    for _ in range(tries):
        st = read_state(device)
        if st.get("screen") == want:
            return st
        time.sleep(0.8)
    raise RuntimeError(f"expected the {want} screen")


def _ascii(text, what) -> str:
    text = str(text).strip()
    if not text or not text.isascii():
        raise RuntimeError(f"{what} must be non-empty plain ASCII (adb text input cannot type other characters)")
    return text


def _up(device):
    """The toolbar up arrow of the editor: leaving the editor saves the note."""
    device.tap(52, 97, delay=1.8)


# ── python_action targets ───────────────────────────────────────────────────

def restart_app(device, params, context):
    device.adb("shell", "am", "force-stop", _PKG)
    time.sleep(0.5)
    return {}


def open_notes(device, params, context):
    return {"state": _wait(device, "list")}


def create_note(device, params, context):
    title = _ascii(params["title"], "title")
    body = str(params.get("body", "")).strip()
    if body and not body.isascii():
        raise RuntimeError("body must be plain ASCII")
    before = _wait(device, "list")
    device.tap(*_centre(_by(_nodes(device), "TakeNote")), delay=1.5)
    st = _wait(device, "editor")
    device.tap(*_centre(_by(_nodes(device), "EnterTitle")), delay=0.6)
    device.adb("shell", "input", "text", input_text_arg(title))
    if body:
        device.tap(*_centre(_by(_nodes(device), "EnterBody")), delay=0.6)
        device.adb("shell", "input", "text", input_text_arg(body))
    time.sleep(0.8)
    _up(device)
    return {"title": title, "body": body, "before": before, "state": _wait(device, "list")}


def list_notes(device, params, context):
    return {"state": _wait(device, "list")}


def _card(device, title):
    cards = _cards(_nodes(device))
    return next((c for c in cards if c["title"].lower() == title.lower()), None), cards


def read_note(device, params, context):
    title = str(params["title"]).strip()
    _wait(device, "list")
    card, cards = _card(device, title)
    if not card:
        raise RuntimeError(f"note {title!r} not found: {[c['title'] for c in cards]}")
    device.tap(*_centre(card["node"]), delay=1.5)
    note = _wait(device, "editor")
    _up(device)
    return {"title": note["title"], "body": note["body"], "state": _wait(device, "list")}


def delete_note(device, params, context):
    if str(params.get("confirm", "")).strip().lower() not in ("yes", "true", "1"):
        raise RuntimeError("delete_note removes the note from the list (into the app's trash): pass confirm=yes")
    title = str(params["title"]).strip()
    before = _wait(device, "list")
    card, cards = _card(device, title)
    if not card:
        raise RuntimeError(f"note {title!r} not found: {[c['title'] for c in cards]}")
    x, y = _centre(card["node"])
    device.adb("shell", "input", "swipe", str(x), str(y), str(x), str(y), "800")  # a long press selects the card
    time.sleep(1.2)
    more = next((n for n in _nodes(device) if n["text"] == "More options"), None)
    if not more:
        raise RuntimeError("the selection toolbar did not open")
    device.tap(*_centre(more), delay=1.0)
    delete = next((n for n in _nodes(device) if n["text"] == "Delete"), None)
    if not delete:
        raise RuntimeError("Delete not in the menu")
    device.tap(*_centre(delete), delay=1.5)
    return {"title": title, "before": before, "state": _wait(device, "list")}


# ── validators ──────────────────────────────────────────────────────────────

def notes_open(device, context) -> bool:
    return read_state(device).get("screen") == "list"


def note_created(device, context) -> bool:
    r = context.result
    s = read_state(device)
    return s.get("screen") == "list" and any(n["title"] == r["title"] for n in s["notes"]) and len(s["notes"]) == len(r["before"]["notes"]) + 1


def notes_read(device, context) -> bool:
    s = read_state(device)
    return s.get("screen") == "list" and [n["title"] for n in s["notes"]] == [n["title"] for n in context.result["state"]["notes"]]


def note_read(device, context) -> bool:
    r = context.result
    s = read_state(device)
    return s.get("screen") == "list" and any(n["title"] == r["title"] for n in s["notes"]) and bool(r["title"])


def note_deleted(device, context) -> bool:
    r = context.result
    s = read_state(device)
    return s.get("screen") == "list" and len(s["notes"]) == len(r["before"]["notes"]) - 1 and not any(n["title"] == r["title"] for n in s["notes"])
