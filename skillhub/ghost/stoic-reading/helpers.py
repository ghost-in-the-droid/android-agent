"""stoic-reading helpers (Stoic Reading, app.reading.stoic.stoicreading2): classic Stoic texts, offline.

Screens: the author list (buttons plus a Dark Mode checkbox), an author page (one button per work), sometimes a part list
(Meditations books, Moral Letters ...) and the reader, one big TextView holding the whole text. The reader shows no back
arrow: the skill steps back with a system BACK only after checking the app owns the foreground.
"""
from __future__ import annotations

import html
import re
import time

_PKG = "app.reading.stoic.stoicreading2"
_CHUNK = 2500


def _nodes(device) -> list[dict]:
    out = []
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"id": a.get("resource-id", "").split("/")[-1], "text": html.unescape(a.get("text", "")).strip(),
                        "cls": a.get("class", "").split(".")[-1], "bounds": tuple(nums)})
    return out


def _centre(n):
    b = n["bounds"]
    return (b[0] + b[2]) // 2, (b[1] + b[3]) // 2


def read_state(device, nodes=None) -> dict:
    nodes = nodes if nodes is not None else _nodes(device)
    title = next((n["text"] for n in nodes if not n["id"] and n["cls"] == "TextView" and n["bounds"][1] < 130), "")
    body = next((n for n in nodes if n["id"] == "textView2"), None)
    if body:
        return {"screen": "reader", "title": title, "text": body["text"], "length": len(body["text"])}
    buttons = [n for n in nodes if n["cls"] == "Button" and n["id"]]
    if any(n["id"] == "toggle_dark_theme" for n in nodes):
        return {"screen": "authors", "authors": [n["text"] for n in buttons if n["id"].endswith("_button")]}
    if buttons:
        return {"screen": "menu", "title": title, "items": [n["text"] for n in buttons]}
    return {"screen": "other"}


def _wait(device, want, tries=10):
    for _ in range(tries):
        st = read_state(device)
        if st["screen"] in (want if isinstance(want, tuple) else (want,)):
            return st
        time.sleep(0.7)
    raise RuntimeError(f"the {want} screen is not on screen")


def _own_foreground(device) -> bool:
    out = device.adb("shell", "dumpsys", "window")
    focus = next((ln for ln in str(out).splitlines() if "mCurrentFocus" in ln), "")
    return f"{_PKG}/" in focus


def _to_authors(device):
    for _ in range(4):
        if read_state(device)["screen"] == "authors":
            return
        if not _own_foreground(device):
            raise RuntimeError("the app is not in the foreground")
        device.adb("shell", "input", "keyevent", "KEYCODE_BACK")
        time.sleep(1.2)
    _wait(device, "authors")


def _press(device, label: str, kind: str):
    nodes = _nodes(device)
    want = label.strip().lower()
    btns = [n for n in nodes if n["cls"] == "Button" and n["id"] and n["id"] != "toggle_dark_theme"]
    hit = next((n for n in btns if n["text"].lower() == want), None) or next((n for n in btns if want in n["text"].lower()), None)
    if not hit:
        raise RuntimeError(f"no {kind} matching {label}; available: {', '.join(n['text'] for n in btns)}")
    device.tap(*_centre(hit), delay=1.8)
    return hit["text"]


# ── python_action targets ───────────────────────────────────────────────────

def restart_app(device, params, context):
    device.adb("shell", "am", "force-stop", _PKG)
    time.sleep(0.5)
    return {}


def open_library(device, params, context):
    return {"state": _wait(device, "authors")}


def list_works(device, params, context):
    author = str(params.get("author") or "").strip()
    if not author:
        raise RuntimeError("author must be a name such as Seneca or Epictetus")
    _to_authors(device)
    _press(device, author, "author")
    return {"author": author, "state": _wait(device, ("menu", "reader"))}


def open_work(device, params, context):
    author = str(params.get("author") or "").strip()
    work = str(params.get("work") or "").strip()
    part = str(params.get("part") or "").strip()
    if not author:
        raise RuntimeError("author must be a name such as Seneca or Epictetus")
    _to_authors(device)
    _press(device, author, "author")
    st = _wait(device, ("menu", "reader"))
    for label in (work, part):
        if label and st["screen"] == "menu":
            _press(device, label, "entry")
            st = _wait(device, ("menu", "reader"))
    out = {"author": author, "work": work, "part": part, "state": st}
    if st["screen"] == "reader":
        out["state"] = {**st, "text": st["text"][:_CHUNK]}
    return out


def seed_reader(device, params, context):
    """Pre-step: make sure some text is open."""
    if read_state(device)["screen"] != "reader":
        open_work(device, {"author": "Aurelius", "work": "Meditations", "part": "Book 1"}, context)
    return {}


def read_text(device, params, context):
    offset = int(params.get("offset") or 0)
    length = min(int(params.get("length") or _CHUNK), 4000)
    st = _wait(device, "reader")
    chunk = st["text"][offset:offset + length]
    return {"title": st["title"], "offset": offset, "length": len(chunk), "total_length": st["length"], "text": chunk,
            "more": offset + length < st["length"]}


# ── validators ──────────────────────────────────────────────────────────────

def library_open(device, context) -> bool:
    return read_state(device)["screen"] == "authors"


def works_listed(device, context) -> bool:
    s = read_state(device)
    return s["screen"] in ("menu", "reader") and bool(context.result["state"])


def work_opened(device, context) -> bool:
    return read_state(device)["screen"] in ("menu", "reader")


def text_read(device, context) -> bool:
    return read_state(device)["screen"] == "reader" and bool(context.result["text"])
