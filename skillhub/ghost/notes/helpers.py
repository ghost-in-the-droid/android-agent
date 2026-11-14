"""Fossify Notes skill helpers. python_action: (device, params, context) -> dict;
validators: (device, context) -> bool. Only on-screen nodes are read.

Fossify Notes saves a note's text when the activity pauses, not on every key,
so writers leave the app with BACK before anything reads the note back."""
from __future__ import annotations

import re
import shlex
import time

_ID = "org.fossify.notes:id/"
_W = 1080


def visible_nodes(device) -> list[dict]:
    """On-screen nodes only: the note pager keeps neighbouring pages in the tree
    at off-screen x positions (left < 0 or left >= screen width)."""
    out: list[dict] = []
    tree = device.dump_portal_json() if hasattr(device, "dump_portal_json") else None
    if tree:
        stack = list(tree) if isinstance(tree, list) else [tree]
        while stack:
            n = stack.pop()
            b = n.get("boundsInScreen") or {}
            box = (b.get("left", 0), b.get("top", 0), b.get("right", 0), b.get("bottom", 0))
            if box[2] > box[0] and box[3] > box[1] and 0 <= box[0] < _W:
                out.append({"text": n.get("text") or "", "desc": n.get("contentDescription") or "",
                            "id": n.get("resourceId") or "", "bounds": box})
            stack.extend(reversed(n.get("children") or []))
        out.sort(key=lambda n: (n["bounds"][1], n["bounds"][0]))
        return out
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and 0 <= nums[0] < _W:
            out.append({"text": a.get("text", ""), "desc": a.get("content-desc", ""),
                        "id": a.get("resource-id", ""), "bounds": tuple(nums)})
    return out


def _tap(device, node):
    b = node["bounds"]
    device.tap((b[0] + b[2]) // 2, (b[1] + b[3]) // 2)


def _find(nodes, id_suffix=None, text=None, desc=None):
    for n in nodes:
        if id_suffix and n["id"] != _ID + id_suffix:
            continue
        if text is not None and n["text"] != text:
            continue
        if desc is not None and n["desc"] != desc:
            continue
        return n
    return None


def _type(device, text: str):
    """`input text` with spaces as %s, shell-quoted. Newlines are not supported."""
    device.adb("shell", "input", "text", shlex.quote(str(text).replace(" ", "%s")))


def _note_dialog(device) -> list[dict]:
    """Open the 'Open note' picker and return [{title, preview, node}]."""
    btn = _find(visible_nodes(device), "open_note")
    if btn is None:
        return []           # only one note exists: the picker button is hidden
    _tap(device, btn)
    time.sleep(1.5)
    nodes = visible_nodes(device)
    out = []
    for holder in (n for n in nodes if n["id"] == _ID + "open_note_item_holder"):
        hb = holder["bounds"]
        inside = [n for n in nodes if hb[0] <= n["bounds"][0] and hb[1] <= n["bounds"][1]
                  and n["bounds"][2] <= hb[2] and n["bounds"][3] <= hb[3]]
        title = next((n for n in inside if n["id"] == _ID + "open_note_item_title"), None)
        prev = next((n["text"] for n in inside if n["id"] == _ID + "open_note_item_text"), "")
        if title:
            out.append({"title": title["text"], "preview": prev, "node": title})
    return out


def _current(device) -> dict:
    nodes = visible_nodes(device)
    body = _find(nodes, "text_note_view")
    return {"text": body["text"] if body else None}


# ── python_action targets ───────────────────────────────────────────────────

def close_notes(device, params, context):
    device.adb("shell", "am", "force-stop", "org.fossify.notes")
    return {"success": True}


def create_note(device, params, context):
    btn = _find(visible_nodes(device), "new_note")
    if btn is None:
        return {"success": False, "error": "'Create a new note' button not on screen"}
    _tap(device, btn)
    time.sleep(1.5)
    label = _find(visible_nodes(device), "locked_note_title")
    if label is None:
        return {"success": False, "error": "new-note dialog did not open"}
    _type(device, params["title"])
    time.sleep(0.5)
    ok = next((n for n in visible_nodes(device) if n["id"] == "android:id/button1"), None)
    if ok is None:
        return {"success": False, "error": "OK button missing"}
    _tap(device, ok)
    time.sleep(1.5)
    nodes = visible_nodes(device)
    if any(n["text"] == params["title"] for n in nodes if n["id"] == "android:id/button1" or n["id"].endswith(":id/alertTitle")):
        return {"success": False, "error": "dialog still open (duplicate title?)"}
    body = _find(nodes, "text_note_view")
    if body is None:
        return {"success": False, "error": "note editor not on screen"}
    _tap(device, body)
    time.sleep(0.8)
    _type(device, params["text"])
    time.sleep(1)
    return {"success": True}


def append_text(device, params, context):
    if not _open_by_title(device, params["title"]):
        return {"success": False, "error": f"no note titled {params['title']!r}"}
    body = _find(visible_nodes(device), "text_note_view")
    if body is None:
        return {"success": False, "error": "note editor not on screen"}
    b = body["bounds"]
    device.tap((b[0] + b[2]) // 2, b[3] - 40)          # tap low in the field: caret goes to the end
    time.sleep(0.8)
    device.adb("shell", "input", "keyevent", "KEYCODE_MOVE_END")
    _type(device, " " + str(params["text"]))
    time.sleep(1)
    return {"success": True}


def _open_by_title(device, title: str) -> bool:
    notes = _note_dialog(device)
    if not notes:
        # Single note: it is already showing; its title is not displayed, so accept
        # only when the caller asks for the default note.
        return title == "General note"
    hit = next((n for n in notes if n["title"] == title), None)
    if hit is None:
        device.adb("shell", "input", "keyevent", "KEYCODE_BACK")
        return False
    _tap(device, hit["node"])
    time.sleep(1.5)
    return True


def list_notes(device, params, context):
    notes = _note_dialog(device)
    if notes:
        device.adb("shell", "input", "keyevent", "KEYCODE_BACK")
        result = [{"title": n["title"], "preview": n["preview"]} for n in notes]
    else:
        text = _current(device)["text"] or ""
        result = [{"title": "General note", "preview": "" if text == "Insert text here" else text}]
    return {"success": True, "data": {"notes": result, "count": len(result)}}


def read_note(device, params, context):
    if not _open_by_title(device, params["title"]):
        return {"success": False, "error": f"no note titled {params['title']!r}"}
    text = _current(device)["text"]
    if text == "Insert text here":   # hint text of an empty note
        text = ""
    return {"success": text is not None, "data": {"note": {"title": params["title"], "text": text}},
            "error": "note text not readable"}


# ── End-state validators: (device, context) -> bool ──────────────────────────

def note_saved(device, context) -> bool:
    """After the app was closed and reopened, the picker lists the title and the
    preview starts with the expected text."""
    want_title = str(context.params["title"])
    want_text = str(context.params["text"])
    notes = _note_dialog(device)
    device.adb("shell", "input", "keyevent", "KEYCODE_BACK")
    hit = next((n for n in notes if n["title"] == want_title), None)
    context.result["note"] = hit and {"title": hit["title"], "preview": hit["preview"]}
    return hit is not None and (want_text[:20] in hit["preview"])


def appended(device, context) -> bool:
    if not _open_by_title(device, context.params["title"]):
        return False
    text = _current(device)["text"] or ""
    context.result["note"] = {"title": context.params["title"], "text": text}
    return text.endswith(str(context.params["text"]))


def notes_ok(device, context) -> bool:
    return isinstance(context.result.get("notes"), list) and len(context.result["notes"]) >= 1


def note_read_ok(device, context) -> bool:
    note = context.result.get("note") or {}
    return note.get("title") == context.params["title"] and isinstance(note.get("text"), str)
