"""privacy-friendly-notes helpers (Privacy Friendly Notes, org.secuso.privacyfriendlynotes): text notes and checklists.

Screens: the note list (search, cards with title, preview and a done counter for checklists, add button), the
text editor (etName, etContent), the checklist editor (etName, etNewItem + ADD, item rows with checkboxes).
Audio and sketch notes are not used. Save keeps the editor open; the Navigate up arrow returns to the list.
"""
from __future__ import annotations

import html
import re
import time

from gitd.bots.common.adb import input_text_arg

_PKG = "org.secuso.privacyfriendlynotes"


def _nodes(device) -> list[dict]:
    out = []
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"text": html.unescape(a.get("text", "")), "desc": html.unescape(a.get("content-desc", "")),
                        "id": a.get("resource-id", "").split("/")[-1], "click": a.get("clickable") == "true",
                        "checked": a.get("checked") == "true", "bounds": tuple(nums)})
    return out


def _centre(n):
    b = n["bounds"]
    return (b[0] + b[2]) // 2, (b[1] + b[3]) // 2


def _by(nodes, ident):
    return next((n for n in nodes if n["id"] == ident), None)


def _all(nodes, ident):
    return sorted((n for n in nodes if n["id"] == ident), key=lambda n: n["bounds"][1])


def _cards(nodes) -> list[dict]:
    titles = _all(nodes, "text_view_title")
    out = []
    for t in titles:
        y0 = t["bounds"][1]
        desc = next((n for n in nodes if n["id"] == "text_view_description" and abs(n["bounds"][1] - t["bounds"][3]) < 6), None)
        extra = next((n for n in nodes if n["id"] == "note_text_extra" and abs(n["bounds"][1] - y0) < 10), None)
        frame = next((n for n in nodes if n["click"] and n["id"] == "" and n["bounds"][1] <= y0 and n["bounds"][3] >= t["bounds"][3]
                      and n["bounds"][0] <= t["bounds"][0] and n["bounds"][2] - n["bounds"][0] > 500), None)
        preview = (desc["text"] if desc else "").strip()
        out.append({"title": t["text"], "preview": preview, "done": extra["text"] if extra else "", "node": frame or t})
    return out


def read_state(device, nodes=None) -> dict:
    nodes = nodes if nodes is not None else _nodes(device)
    if _by(nodes, "fab") and _by(nodes, "searchViewFilter"):
        return {"screen": "list", "notes": [{k: v for k, v in c.items() if k != "node"} for c in _cards(nodes)]}
    if _by(nodes, "etNewItem"):
        items = [{"item": n["text"], "checked": c["checked"]}
                 for n, c in zip(_all(nodes, "item_name"), _all(nodes, "item_checkbox"))]
        return {"screen": "checklist", "title": (_by(nodes, "etName") or {}).get("text", ""), "items": items}
    if _by(nodes, "etContent"):
        return {"screen": "text", "title": (_by(nodes, "etName") or {}).get("text", ""), "text": _by(nodes, "etContent")["text"].strip()}
    return {"screen": "other"}


def _wait(device, want, tries=10):
    for _ in range(tries):
        st = read_state(device)
        if st["screen"] == want:
            return st
        time.sleep(0.8)
    raise RuntimeError(f"the {want} screen is not on screen")


def _up(device):
    """Tap the Navigate up arrow (never the system Back key) until the list shows."""
    for _ in range(3):
        nodes = _nodes(device)
        if read_state(device, nodes)["screen"] == "list":
            return read_state(device, nodes)
        up = next((n for n in nodes if n["desc"] == "Navigate up"), None)
        if not up:
            raise RuntimeError("cannot find the Navigate up arrow")
        device.tap(*_centre(up), delay=1.5)
    raise RuntimeError("could not return to the note list")


def _clean(text, limit, what) -> str:
    text = str(text).replace("\n", " ").strip()
    if not text or len(text) > limit:
        raise RuntimeError(f"{what} must be 1 to {limit} characters")
    return text


def _type_into(device, ident, text):
    device.tap(*_centre(_by(_nodes(device), ident)), delay=0.5)
    device.adb("shell", "input", "text", input_text_arg(text))
    time.sleep(0.6)


def _new(device, fab_id):
    _up(device)
    device.tap(*_centre(_by(_nodes(device), "fab")), delay=1.2)
    nodes = _nodes(device)
    entry = _by(nodes, fab_id)
    if not entry:
        raise RuntimeError("the add menu did not open")
    device.tap(*_centre(entry), delay=1.8)


def _save(device):
    device.tap(*_centre(_by(_nodes(device), "action_save")), delay=1.5)


def _open(device, title):
    st = _up(device)
    card = next((c for c in _cards(_nodes(device)) if c["title"] == title), None)
    if not card:
        raise RuntimeError(f"note not found: {title}")
    device.tap(*_centre(card["node"]), delay=1.8)


# ── python_action targets ───────────────────────────────────────────────────

def restart_app(device, params, context):
    device.adb("shell", "am", "force-stop", _PKG)
    time.sleep(0.5)
    return {}


def skip_intro(device, params, context):
    """First launch shows a welcome pager: tap Skip once so the note list shows."""
    for _ in range(8):
        nodes = _nodes(device)
        if read_state(device, nodes)["screen"] in {"list", "text", "checklist"}:
            return {}
        skip = _by(nodes, "btn_skip")
        if skip:
            device.tap(*_centre(skip), delay=1.5)
        else:
            time.sleep(0.8)
    raise RuntimeError("welcome did not resolve to a known Notes screen")


def open_notes(device, params, context):
    skip_intro(device, params, context)
    return {"state": _up(device)}


def create_note(device, params, context):
    title = _clean(params.get("title", ""), 60, "title")
    text = _clean(params.get("text", ""), 300, "text")
    before = _up(device)
    _new(device, "fab_text")
    _wait(device, "text")
    _type_into(device, "etName", title)
    _type_into(device, "etContent", text)
    typed = read_state(device)
    if typed.get("title") != title or typed.get("text") != text:
        raise RuntimeError(f"fields do not match what was typed: {typed!r}")
    _save(device)
    after = _up(device)
    if not any(n["title"] == title for n in after["notes"]):
        raise RuntimeError("the new note is not in the list")
    return {"title": title, "text": text, "count_before": len(before["notes"]), "count_after": len(after["notes"]), "state": after}


def create_checklist(device, params, context):
    title = _clean(params.get("title", ""), 60, "title")
    items = [i.strip() for i in str(params.get("items", "")).replace("|", ",").split(",") if i.strip()]
    if not 1 <= len(items) <= 12 or any(len(i) > 60 for i in items):
        raise RuntimeError("items must be 1 to 12 entries separated by commas, each up to 60 characters")
    before = _up(device)
    _new(device, "fab_checklist")
    _wait(device, "checklist")
    _type_into(device, "etName", title)
    for it in items:
        _type_into(device, "etNewItem", it)
        device.tap(*_centre(_by(_nodes(device), "btn_add")), delay=0.9)
    typed = read_state(device)
    if [i["item"] for i in typed.get("items", [])] != items:
        raise RuntimeError(f"items do not match what was typed: {typed!r}")
    _save(device)
    after = _up(device)
    if not any(n["title"] == title for n in after["notes"]):
        raise RuntimeError("the new checklist is not in the list")
    return {"title": title, "items": items, "count_before": len(before["notes"]), "count_after": len(after["notes"]), "state": after}


def list_notes(device, params, context):
    st = _up(device)
    return {"count": len(st["notes"]), "notes": st["notes"], "state": st}


def read_note(device, params, context):
    title = _clean(params.get("title", ""), 60, "title")
    _open(device, title)
    st = read_state(device)
    if st["screen"] not in ("text", "checklist"):
        raise RuntimeError("the note did not open")
    _up(device)
    return {"kind": st["screen"], **{k: v for k, v in st.items() if k != "screen"}, "state": read_state(device)}


def check_item(device, params, context):
    title = _clean(params.get("title", ""), 60, "title")
    item = _clean(params.get("item", ""), 60, "item")
    _open(device, title)
    st = _wait(device, "checklist")
    nodes = _nodes(device)
    names = _all(nodes, "item_name")
    boxes = _all(nodes, "item_checkbox")
    pair = next(((n, c) for n, c in zip(names, boxes) if n["text"] == item), None)
    if not pair:
        raise RuntimeError(f"item not found: {item}")
    was = pair[1]["checked"]
    device.tap(*_centre(pair[1]), delay=1.0)
    now = read_state(device)
    row = next((i for i in now["items"] if i["item"] == item), None)
    if not row or row["checked"] == was:
        raise RuntimeError("the checkbox did not change")
    _save(device)
    after = _up(device)
    return {"title": title, "item": item, "checked": row["checked"], "state": after}


def search_notes(device, params, context):
    query = _clean(params.get("query", ""), 40, "query")
    _up(device)
    device.tap(*_centre(_by(_nodes(device), "search_src_text")), delay=0.6)
    device.adb("shell", "input", "text", input_text_arg(query))
    time.sleep(1.2)
    hits = read_state(device)
    device.adb("shell", "input", "keycombination", "KEYCODE_CTRL_LEFT", "KEYCODE_A")
    device.adb("shell", "input", "keyevent", "KEYCODE_DEL")
    time.sleep(0.8)
    if hits.get("screen") != "list":
        raise RuntimeError("search results not readable")
    return {"query": query, "count": len(hits["notes"]), "notes": hits["notes"], "state": read_state(device)}


def seed_notes(device, params, context):
    """Pre-step for read/check/search on a clean reset: make sure the demo note and checklist exist."""
    skip_intro(device, params, context)
    st = _up(device)
    have = {n["title"] for n in st["notes"]}
    if "Garden plan" not in have:
        create_note(device, {"title": "Garden plan", "text": "Plant tomatoes in May"}, context)
    if "Groceries" not in have:
        create_checklist(device, {"title": "Groceries", "items": "Milk,Eggs"}, context)
    return {}


# ── validators ──────────────────────────────────────────────────────────────

def notes_open(device, context) -> bool:
    return read_state(device).get("screen") == "list"


def note_created(device, context) -> bool:
    r = context.result
    s = read_state(device)
    return s.get("screen") == "list" and any(n["title"] == r["title"] for n in s["notes"]) and r["count_after"] > r["count_before"]


def notes_listed(device, context) -> bool:
    s = read_state(device)
    return s.get("screen") == "list" and len(s["notes"]) == context.result["count"]


def note_read(device, context) -> bool:
    r = context.result
    return read_state(device).get("screen") == "list" and (r.get("text") or r.get("items"))


def item_checked(device, context) -> bool:
    r = context.result
    s = read_state(device)
    mark = "[x] " if r["checked"] else "[  ] "
    return s.get("screen") == "list" and any(n["title"] == r["title"] and (mark + r["item"]) in n["preview"] for n in s["notes"])


def searched(device, context) -> bool:
    return read_state(device).get("screen") == "list" and context.result["count"] >= 0
