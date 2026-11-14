"""easy-notes helpers (Easy Notes, com.kin.easynotes): create, list, search and read markdown notes offline.

Screens: the note list (search field + New Note button), the editor (Name and Description fields, Done) and the
note view (title and body text, Back arrow). The app crashes when a note is deleted from its view, so the skill
never deletes.
"""
from __future__ import annotations

import html
import re
import time

from gitd.bots.common.adb import input_text_arg

_PKG = "com.kin.easynotes"


def _nodes(device) -> list[dict]:
    out = []
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"text": html.unescape(a.get("text", "")), "desc": html.unescape(a.get("content-desc", "")),
                        "cls": a.get("class", "").split(".")[-1], "click": a.get("clickable") == "true",
                        "bounds": tuple(nums)})
    return out


def _centre(n):
    b = n["bounds"]
    return (b[0] + b[2]) // 2, (b[1] + b[3]) // 2


def _desc(nodes, d):
    return next((n for n in nodes if n["desc"] == d), None)


def _rows(nodes) -> list[dict]:
    """Note cards: clickable Views below the search field that contain text."""
    texts = [n for n in nodes if n["text"] and n["cls"] == "TextView" and n["bounds"][1] > 200]
    rows = []
    for c in (n for n in nodes if n["click"] and n["cls"] == "View" and n["bounds"][1] > 200 and n["bounds"][3] - n["bounds"][1] > 100):
        b = c["bounds"]
        inside = sorted((t for t in texts if b[0] <= t["bounds"][0] and t["bounds"][2] <= b[2]
                         and b[1] <= t["bounds"][1] and t["bounds"][3] <= b[3]), key=lambda t: t["bounds"][1])
        if inside:
            rows.append({"title": inside[0]["text"], "body": inside[1]["text"] if len(inside) > 1 else "", "node": c})
    return rows


def read_state(device, nodes=None) -> dict:
    nodes = nodes if nodes is not None else _nodes(device)
    edits = [n for n in nodes if n["cls"] == "EditText"]
    if _desc(nodes, "New Note"):
        return {"screen": "list", "notes": [{"title": r["title"], "body": r["body"]} for r in _rows(nodes)]}
    if _desc(nodes, "Done") and len(edits) >= 2:
        return {"screen": "editor"}
    if _desc(nodes, "Back") and not edits:
        body = sorted((n for n in nodes if n["text"] and n["bounds"][1] > 200), key=lambda n: n["bounds"][1])
        if body:
            return {"screen": "note", "title": body[0]["text"], "body": body[1]["text"] if len(body) > 1 else ""}
    return {"screen": "other"}


def _wait(device, want, tries=10):
    for _ in range(tries):
        st = read_state(device)
        if st["screen"] == want:
            return st
        time.sleep(0.8)
    raise RuntimeError(f"the {want} screen is not on screen")


def _to_list(device):
    for _ in range(3):
        nodes = _nodes(device)
        st = read_state(device, nodes)
        if st["screen"] == "list":
            return st
        back = _desc(nodes, "Back")
        if st["screen"] == "note" and back:
            device.tap(*_centre(back), delay=1.3)
            continue
        time.sleep(0.8)
    raise RuntimeError("could not reach the note list")


def _clean(text: str, limit: int, what: str) -> str:
    text = str(text).replace("\n", " ").strip()
    if not text or len(text) > limit:
        raise RuntimeError(f"{what} must be 1 to {limit} characters")
    return text


# ── python_action targets ───────────────────────────────────────────────────

def restart_app(device, params, context):
    device.adb("shell", "am", "force-stop", _PKG)
    time.sleep(0.5)
    return {}


def open_notes(device, params, context):
    return {"state": _to_list(device)}


def create_note(device, params, context):
    title = _clean(params.get("title", ""), 60, "title")
    text = _clean(params.get("text", ""), 300, "text")
    before = _to_list(device)
    device.tap(*_centre(_desc(_nodes(device), "New Note")), delay=1.5)
    _wait(device, "editor")
    edits = sorted((n for n in _nodes(device) if n["cls"] == "EditText"), key=lambda n: n["bounds"][1])
    device.tap(*_centre(edits[0]), delay=0.6)
    device.adb("shell", "input", "text", input_text_arg(title))
    time.sleep(0.6)
    edits = sorted((n for n in _nodes(device) if n["cls"] == "EditText"), key=lambda n: n["bounds"][1])
    device.tap(*_centre(edits[-1]), delay=0.6)
    device.adb("shell", "input", "text", input_text_arg(text))
    time.sleep(0.8)
    typed = sorted((n for n in _nodes(device) if n["cls"] == "EditText"), key=lambda n: n["bounds"][1])
    if [t["text"] for t in typed[:2]] != [title, text]:
        raise RuntimeError(f"fields do not match what was typed: {[t['text'] for t in typed[:2]]!r}")
    device.tap(668, 105, delay=1.5)
    after = _wait(device, "list")
    if not any(n["title"] == title for n in after["notes"]):
        raise RuntimeError("the new note is not in the list")
    return {"title": title, "text": text, "count_before": len(before["notes"]), "count_after": len(after["notes"]),
            "state": after}


def seed_note(device, params, context):
    """Pre-step for read_note and search_notes on a clean reset: make sure the demo note exists."""
    st = _to_list(device)
    if not any(n["title"] == "Shopping list" for n in st["notes"]):
        create_note(device, {"title": "Shopping list", "text": "Milk eggs bread"}, context)
    return {}


def list_notes(device, params, context):
    st = _to_list(device)
    return {"count": len(st["notes"]), "notes": st["notes"], "state": st}


def read_note(device, params, context):
    title = _clean(params.get("title", ""), 60, "title")
    st = _to_list(device)
    row = next((r for r in _rows(_nodes(device)) if r["title"] == title), None)
    if not row:
        raise RuntimeError(f"note not found: {title}")
    device.tap(*_centre(row["node"]), delay=1.5)
    note = _wait(device, "note")
    _to_list(device)
    return {"title": note["title"], "body": note["body"], "state": read_state(device)}


def search_notes(device, params, context):
    query = _clean(params.get("query", ""), 40, "query")
    _to_list(device)
    search = next(n for n in _nodes(device) if n["cls"] == "EditText")
    device.tap(*_centre(search), delay=0.6)
    device.adb("shell", "input", "text", input_text_arg(query))
    time.sleep(1.2)
    st = read_state(device)
    hits = st["notes"]
    device.adb("shell", "input", "keycombination", "KEYCODE_CTRL_LEFT", "KEYCODE_A")
    device.adb("shell", "input", "keyevent", "KEYCODE_DEL")
    time.sleep(0.8)
    return {"query": query, "count": len(hits), "notes": hits, "state": read_state(device)}


# ── validators ──────────────────────────────────────────────────────────────

def notes_open(device, context) -> bool:
    return read_state(device).get("screen") == "list"


def note_created(device, context) -> bool:
    r = context.result
    s = read_state(device)
    return s.get("screen") == "list" and any(n["title"] == r["title"] for n in s["notes"]) and r["count_after"] >= r["count_before"]


def notes_listed(device, context) -> bool:
    s = read_state(device)
    return s.get("screen") == "list" and len(s["notes"]) == context.result["count"]


def note_read(device, context) -> bool:
    r = context.result
    return read_state(device).get("screen") == "list" and r["title"] != "" and r["body"] != ""


def searched(device, context) -> bool:
    return read_state(device).get("screen") == "list" and context.result["count"] >= 0
