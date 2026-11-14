"""daily-diary helpers (Daily Diary, com.voklen.daily_diary): write and read today's diary page.

One EditText holds today's entry and autosaves. The list button opens the previous days (empty on a fresh install).
"""
from __future__ import annotations

import html
import re
import time

from gitd.bots.common.adb import input_text_arg

_PKG = "com.voklen.daily_diary"


def _nodes(device) -> list[dict]:
    out = []
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"text": html.unescape(a.get("text", "")), "desc": html.unescape(a.get("content-desc", "")),
                        "cls": a.get("class", "").split(".")[-1], "bounds": tuple(nums)})
    return out


def _centre(n):
    b = n["bounds"]
    return (b[0] + b[2]) // 2, (b[1] + b[3]) // 2


def read_state(device, nodes=None) -> dict:
    nodes = nodes if nodes is not None else _nodes(device)
    editor = next((n for n in nodes if n["cls"] == "EditText"), None)
    if editor:
        return {"screen": "today", "entry": editor["text"]}
    if any(n["desc"] == "Previous Entries" for n in nodes):
        return {"screen": "previous"}
    return {"screen": "other"}


def _wait(device, want="today", tries=10):
    for _ in range(tries):
        st = read_state(device)
        if st["screen"] == want:
            return st
        time.sleep(0.8)
    raise RuntimeError(f"the {want} screen is not on screen")


def _clean(text: str) -> str:
    text = str(text).replace("\n", " ").strip()
    if not text or len(text) > 300:
        raise RuntimeError("text must be 1 to 300 characters")
    return text


def _editor(device):
    return next(n for n in _nodes(device) if n["cls"] == "EditText")


def _replace(device, current: str, text: str) -> dict:
    """Focus the field, select all, delete, then type the full new text."""
    device.tap(*_centre(_editor(device)), delay=0.6)
    device.adb("shell", "input", "keycombination", "KEYCODE_CTRL_LEFT", "KEYCODE_A")
    time.sleep(0.4)
    device.adb("shell", "input", "keyevent", "KEYCODE_DEL")
    time.sleep(0.4)
    device.adb("shell", "input", "text", input_text_arg(text))
    time.sleep(1.0)
    now = read_state(device)
    if now.get("entry") != text:
        raise RuntimeError(f"entry did not match what was typed (got: {now.get('entry')!r})")
    return now


# ── python_action targets ───────────────────────────────────────────────────

def restart_app(device, params, context):
    device.adb("shell", "am", "force-stop", _PKG)
    time.sleep(0.5)
    return {}


def open_diary(device, params, context):
    return {"state": _wait(device)}


def write_entry(device, params, context):
    text = _clean(params.get("text", ""))
    st = _wait(device)
    now = _replace(device, st["entry"], text)
    return {"entry": now["entry"], "state": now}


def append_entry(device, params, context):
    text = _clean(params.get("text", ""))
    st = _wait(device)
    before = st["entry"]
    full = (before + " " + text) if before else text
    if len(full) > 600:
        raise RuntimeError("the entry would exceed 600 characters")
    now = _replace(device, before, full)
    return {"before": before, "entry": now["entry"], "state": now}


def read_entry(device, params, context):
    return {"state": _wait(device)}


def list_previous(device, params, context):
    _wait(device)
    nodes = _nodes(device)
    buttons = sorted((n for n in nodes if n["cls"] == "Button" and n["bounds"][1] < 160), key=lambda n: n["bounds"][0])
    if not buttons:
        raise RuntimeError("list button not found")
    device.tap(*_centre(buttons[0]), delay=1.5)
    _wait(device, "previous")
    rows = [n["text"] or n["desc"] for n in _nodes(device)
            if (n["text"] or n["desc"]) and n["desc"] not in ("Back", "Previous Entries") and n["bounds"][1] > 160 and not (n["text"] or n["desc"]).startswith("Entries from previous days")]
    back = next(n for n in _nodes(device) if n["desc"] == "Back")
    device.tap(*_centre(back), delay=1.2)
    _wait(device)
    return {"rows": rows, "count": len(rows), "state": read_state(device)}


# ── validators ──────────────────────────────────────────────────────────────

def diary_open(device, context) -> bool:
    return read_state(device).get("screen") == "today"


def written(device, context) -> bool:
    s = read_state(device)
    return s.get("screen") == "today" and s["entry"] == context.result["entry"] and bool(s["entry"])


def appended(device, context) -> bool:
    r = context.result
    s = read_state(device)
    return s.get("screen") == "today" and s["entry"] == r["entry"] and len(r["entry"]) > len(r["before"])


def entry_read(device, context) -> bool:
    s = read_state(device)
    return s.get("screen") == "today" and s["entry"] == context.result["state"]["entry"]


def previous_listed(device, context) -> bool:
    return read_state(device).get("screen") == "today" and context.result["count"] >= 0
