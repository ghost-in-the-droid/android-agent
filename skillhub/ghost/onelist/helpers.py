"""onelist helpers (1List, com.lolo.io.onelist): a minimalist offline list app (todo and shopping lists).

Lists are tabs at the top, the input field sits above the items, and an item is deleted by swiping it left. The
done/strikethrough state is not exposed in the accessibility tree, so the skill does not toggle or read it.
"""
from __future__ import annotations

import html
import re
import time

from gitd.bots.common.adb import input_text_arg

_PKG = "com.lolo.io.onelist"


def _nodes(device) -> list[dict]:
    out = []
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"text": html.unescape(a.get("text", "") or a.get("content-desc", "")),
                        "cls": a.get("class", "").split(".")[-1], "bounds": tuple(nums)})
    return out


def _centre(n):
    b = n["bounds"]
    return (b[0] + b[2]) // 2, (b[1] + b[3]) // 2


def _ascii(text, what) -> str:
    text = str(text).strip()
    if not text or not text.isascii():
        raise RuntimeError(f"{what} must be a non-empty plain ASCII text (adb text input cannot type other characters)")
    return text


def read_state(device) -> dict:
    nodes = _nodes(device)
    if not any(n["cls"] == "EditText" for n in nodes):
        return {"screen": "other"}
    tabs = sorted((n for n in nodes if n["cls"] == "TextView" and 140 <= n["bounds"][1] < 240 and n["text"] != "1List"),
                  key=lambda n: n["bounds"][0])
    items = sorted((n for n in nodes if n["cls"] == "TextView" and n["bounds"][1] >= 380 and n["bounds"][0] < 120
                    and n["text"] not in ("Add", "Undo")), key=lambda n: n["bounds"][1])
    return {"screen": "lists", "lists": [re.sub(r"^\S*\s", "", t["text"]) if re.match(r"^[^\w\s]", t["text"]) else t["text"] for t in tabs],
            "items": [i["text"] for i in items]}


def _wait(device, tries=10):
    for _ in range(tries):
        st = read_state(device)
        if st.get("screen") == "lists":
            return st
        time.sleep(0.8)
    raise RuntimeError("the list screen is not on screen")


def _tab(device, name):
    nodes = _nodes(device)
    for n in nodes:
        if n["cls"] == "TextView" and 140 <= n["bounds"][1] < 240 and name.lower() in n["text"].lower():
            return n
    return None


# ── python_action targets ───────────────────────────────────────────────────

def restart_app(device, params, context):
    device.adb("shell", "am", "force-stop", _PKG)
    time.sleep(0.5)
    return {}


def open_lists(device, params, context):
    return {"state": _wait(device)}


def create_list(device, params, context):
    name = _ascii(params["name"], "name")
    before = _wait(device)
    device.tap(661, 99, delay=1.5)
    nodes = _nodes(device)
    field = next((n for n in nodes if n["cls"] == "EditText"), None)
    if not field or not any(n["text"] == "List name" for n in nodes):
        raise RuntimeError("the new-list dialog did not open")
    device.tap(*_centre(field), delay=0.5)
    device.adb("shell", "input", "text", input_text_arg(name))
    time.sleep(0.5)
    save = next((n for n in _nodes(device) if n["text"] == "Save"), None)
    if not save:
        raise RuntimeError("Save not on screen")
    device.tap(*_centre(save), delay=1.8)
    return {"name": name, "before": before, "state": _wait(device)}


def select_list(device, params, context):
    name = str(params["name"]).strip()
    before = _wait(device)
    tab = _tab(device, name)
    if not tab:
        raise RuntimeError(f"list {name!r} not found: {before['lists']}")
    device.tap(*_centre(tab), delay=1.2)
    return {"name": name, "before": before, "state": _wait(device)}


def add_item(device, params, context):
    item = _ascii(params["item"], "item")
    before = _wait(device)
    field = next(n for n in _nodes(device) if n["cls"] == "EditText")
    device.tap(*_centre(field), delay=0.5)
    device.adb("shell", "input", "text", input_text_arg(item))
    time.sleep(0.6)
    fy = _centre(field)[1]
    # the add button sits in the input row, right of the field; header buttons (share, import) must never match
    btn = next((n for n in _nodes(device) if n["cls"] != "EditText" and n["bounds"][0] > 500 and abs(_centre(n)[1] - fy) < 30
                and n["bounds"][1] > 200), None)
    if not btn:
        raise RuntimeError("add button not on screen")
    device.tap(*_centre(btn), delay=1.2)
    return {"item": item, "before": before, "state": _wait(device)}


def remove_item(device, params, context):
    item = str(params["item"]).strip()
    before = _wait(device)
    row = next((n for n in _nodes(device) if n["cls"] == "TextView" and n["bounds"][1] >= 380 and n["bounds"][0] < 120
                and n["text"].lower() == item.lower()), None)
    if not row:
        raise RuntimeError(f"item {item!r} is not in this list: {before['items']}")
    y = _centre(row)[1]
    device.swipe(620, y, 80, y, 300)
    time.sleep(1.2)
    return {"item": row["text"], "before": before, "state": _wait(device)}


def get_items(device, params, context):
    return {"state": _wait(device)}


# ── validators ──────────────────────────────────────────────────────────────

def lists_open(device, context) -> bool:
    return read_state(device).get("screen") == "lists"


def list_created(device, context) -> bool:
    r = context.result
    s = read_state(device)
    return s.get("screen") == "lists" and any(r["name"].lower() in t.lower() for t in s["lists"]) and len(s["lists"]) == len(r["before"]["lists"]) + 1


def list_selected(device, context) -> bool:
    return read_state(device).get("screen") == "lists"


def item_added(device, context) -> bool:
    r = context.result
    s = read_state(device)
    return s.get("screen") == "lists" and s["items"].count(r["item"]) == r["before"]["items"].count(r["item"]) + 1


def item_removed(device, context) -> bool:
    r = context.result
    for _ in range(3):
        s = read_state(device)
        if s.get("screen") == "lists" and s["items"].count(r["item"]) == r["before"]["items"].count(r["item"]) - 1:
            return True
        time.sleep(0.8)
    return False


def items_read(device, context) -> bool:
    s = read_state(device)
    return s.get("screen") == "lists" and s["items"] == context.result["state"]["items"]
