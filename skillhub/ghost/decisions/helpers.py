"""decisions helpers (Decisions, de.markusfisch.android.libra): weigh pros and cons on a scale, offline.

Screens: the issue list (an add button), the issue screen (a balance, argument chips, a weight row -10..10 above an
argument field with a save button) and a rename dialog. Chip side is readable from its position (pros sit right of the
centre, cons left, weight 0 in the middle); the weight number and the balance totals are drawn, not in the tree.
"""
from __future__ import annotations

import html
import re
import time

from gitd.bots.common.adb import input_text_arg

_PKG = "de.markusfisch.android.libra"


def _nodes(device) -> list[dict]:
    out = []
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"id": a.get("resource-id", "").split("/")[-1], "text": html.unescape(a.get("text", "")),
                        "desc": html.unescape(a.get("content-desc", "")), "bounds": tuple(nums)})
    return out


def _by(nodes, ident):
    return next((n for n in nodes if n["id"] == ident), None)


def _centre(n):
    b = n["bounds"]
    return (b[0] + b[2]) // 2, (b[1] + b[3]) // 2


def _side(n) -> str:
    cx = _centre(n)[0]
    return "pro" if cx > 372 else "con" if cx < 348 else "neutral"


def read_state(device, nodes=None) -> dict:
    nodes = nodes if nodes is not None else _nodes(device)
    if _by(nodes, "edit_issue"):
        title = next((n["text"] for n in nodes if n["text"] and not n["id"] and n["bounds"][1] < 150), "")
        args = [{"text": n["text"], "side": _side(n)} for n in sorted((n for n in nodes if n["id"] == "text"), key=lambda n: n["bounds"][1])]
        return {"screen": "issue", "title": title, "arguments": args}
    if _by(nodes, "name") and _by(nodes, "button1") and not _by(nodes, "created"):
        return {"screen": "dialog"}
    if _by(nodes, "add"):
        issues = [{"name": n["text"]} for n in sorted((n for n in nodes if n["id"] == "name"), key=lambda n: n["bounds"][1])]
        for it, c in zip(issues, sorted((n for n in nodes if n["id"] == "created"), key=lambda n: n["bounds"][1])):
            it["created"] = c["text"]
        return {"screen": "list", "issues": issues}
    return {"screen": "other"}


def _wait(device, want, tries=12):
    for _ in range(tries):
        st = read_state(device)
        if st["screen"] == want:
            return st
        time.sleep(0.7)
    raise RuntimeError(f"the {want} screen is not on screen")


def _clear_and_type(device, field, text):
    device.tap(*_centre(field), delay=0.5)
    device.adb("shell", "input", "keycombination", "KEYCODE_CTRL_LEFT", "KEYCODE_A")
    device.adb("shell", "input", "keyevent", "KEYCODE_DEL")
    time.sleep(0.3)
    device.adb("shell", "input", "text", input_text_arg(text))
    time.sleep(0.5)


def _to_list(device):
    if read_state(device)["screen"] == "issue":
        up = next((n for n in _nodes(device) if n["desc"] == "Navigate up"), None)
        device.tap(*_centre(up), delay=1.4)
    _wait(device, "list")


# ── python_action targets ───────────────────────────────────────────────────

def restart_app(device, params, context):
    device.adb("shell", "am", "force-stop", _PKG)
    time.sleep(0.5)
    return {}


def open_issues(device, params, context):
    return {"state": _wait(device, "list")}


def list_issues(device, params, context):
    _to_list(device)
    return {"state": read_state(device)}


def new_issue(device, params, context):
    title = str(params.get("title", "")).strip()
    if not title or len(title) > 60:
        raise RuntimeError("title must be 1 to 60 characters")
    _to_list(device)
    device.tap(*_centre(_by(_nodes(device), "add")), delay=1.6)
    _wait(device, "issue")
    device.tap(*_centre(_by(_nodes(device), "edit_issue")), delay=1.2)
    _clear_and_type(device, _by(_nodes(device), "name"), title)
    ok = _by(_nodes(device), "button1")  # the dialog moves above the keyboard, so read its position now
    device.tap(*_centre(ok), delay=1.5)
    st = _wait(device, "issue")
    return {"title": st["title"], "requested": title, "arguments": st["arguments"]}


def add_argument(device, params, context):
    text = str(params.get("text", "")).strip()
    weight = int(params.get("weight", 1))
    if not text or len(text) > 60:
        raise RuntimeError("text must be 1 to 60 characters")
    if not -10 <= weight <= 10:
        raise RuntimeError("weight must be between -10 (against) and 10 (for)")
    _wait(device, "issue")
    _clear_and_type(device, _by(_nodes(device), "argument"), text)
    nodes = _nodes(device)
    field = _by(nodes, "argument")
    row_y = _centre(field)[1] - 101
    device.tap(360 + weight * 32, row_y, delay=0.6)
    device.tap(*_centre(_by(_nodes(device), "save_argument")), delay=1.5)
    st = read_state(device)
    chip = next((a for a in reversed(st.get("arguments", [])) if a["text"] == text), None)
    if not chip:
        raise RuntimeError("the argument did not show up")
    return {"text": text, "weight": weight, "side": chip["side"], "title": st["title"], "arguments": st["arguments"]}


def seed_issue(device, params, context):
    """Pre-step: make sure an issue with two arguments is open."""
    st = read_state(device)
    if st["screen"] == "issue" and len(st["arguments"]) >= 2:
        return {}
    if st["screen"] == "issue":
        add_argument(device, {"text": "Cheaper", "weight": 4}, context)
        return {}
    new_issue(device, {"title": "Buy a new phone"}, context)
    add_argument(device, {"text": "Cheaper", "weight": 4}, context)
    add_argument(device, {"text": "Slower", "weight": -3}, context)
    return {}


def get_issue(device, params, context):
    return {"state": _wait(device, "issue")}


# ── validators ──────────────────────────────────────────────────────────────

def issues_open(device, context) -> bool:
    return read_state(device)["screen"] == "list"


def issues_listed(device, context) -> bool:
    s = read_state(device)
    return s["screen"] == "list" and [i["name"] for i in s["issues"]] == [i["name"] for i in context.result["state"]["issues"]]


def issue_created(device, context) -> bool:
    r = context.result
    s = read_state(device)
    return s["screen"] == "issue" and s["title"] == r["requested"]


def argument_added(device, context) -> bool:
    r = context.result
    s = read_state(device)
    return s["screen"] == "issue" and any(a["text"] == r["text"] for a in s["arguments"]) and r["side"] == ("pro" if r["weight"] > 0 else "con" if r["weight"] < 0 else "neutral")


def issue_read(device, context) -> bool:
    s = read_state(device)
    return s["screen"] == "issue" and s["arguments"] == context.result["state"]["arguments"]
