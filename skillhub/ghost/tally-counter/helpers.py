"""tally-counter helpers (Counter by gentlecat, me.tsukanov.counter).

python_action signature: (device, params, context) -> {"data": {...}} (the engine merges "data" into context.result; a bare dict is dropped)
validator signature:     (device, context) -> bool
"""
from __future__ import annotations

import re
import time

_ID = "me.tsukanov.counter:id/"


def visible_nodes(device) -> list[dict]:
    """On-screen nodes: text, desc, id, bounds."""
    out: list[dict] = []
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"text": a.get("text", ""), "desc": a.get("content-desc", ""),
                        "id": a.get("resource-id", ""), "bounds": tuple(nums)})
    return out


def _by_id(nodes, suffix):
    return [n for n in nodes if n["id"] == _ID + suffix]


def _center(b):
    return (b[0] + b[2]) // 2, (b[1] + b[3]) // 2


def _label(device):
    n = _by_id(visible_nodes(device), "counterLabel")
    return int(n[0]["text"]) if n and n[0]["text"].lstrip("-").isdigit() else None


# ── python_action targets ───────────────────────────────────────────────────

def select_counter(device, params, context):
    """Tap the drawer row whose title equals params.name (drawer must be open)."""
    want = str(params["name"])
    rows = [n for n in _by_id(visible_nodes(device), "row_title") if n["text"] == want]
    if not rows:
        raise RuntimeError(f"no counter named {want!r} in the list")
    device.tap(*_center(rows[0]["bounds"]))
    time.sleep(1.0)
    return {"data": {"selected": want}}


def tap_counter(device, params, context):
    """Tap the big counter area params.times times and report before/after."""
    times = int(params.get("times", 1))
    before = _label(device)
    node = _by_id(visible_nodes(device), "counterFrame")
    if before is None or not node:
        raise RuntimeError("counter screen not showing")
    x, y = _center(node[0]["bounds"])
    for _ in range(times):
        device.tap(x, y, delay=0.35)
    time.sleep(0.5)
    return {"data": {"before": before, "after": _label(device), "times": times}}


def read_counters(device, params, context):
    """Read every row of the open counters list."""
    nodes = visible_nodes(device)
    titles = [n["text"] for n in _by_id(nodes, "row_title")]
    counts = [n["text"] for n in _by_id(nodes, "row_count")]
    return {"data": {"counters": [{"name": t, "value": int(c)} for t, c in zip(titles, counts) if c.lstrip("-").isdigit()]}}


def type_value(device, params, context):
    """Type params.value (digits, may arrive as an int) into the focused field."""
    device.adb("shell", "input", "text", str(params.get("value", "0")))
    time.sleep(0.3)
    return {}


def read_active(device, params, context):
    """Active counter: its title (toolbar) and value."""
    nodes = visible_nodes(device)
    title = next((n["text"] for n in nodes if n["id"] == "" and n["bounds"][1] < 160 and n["text"]), "")
    return {"data": {"active": {"name": title, "value": _label(device)}}}


def note_before(device, params, context):
    return {"data": {"before": _label(device)}}


def close_drawer(device, params, context):
    if _by_id(visible_nodes(device), "add_counter"):
        device.back()
        time.sleep(0.6)
    return {}


# ── validators ──────────────────────────────────────────────────────────────

def counter_created(device, context) -> bool:
    nodes = visible_nodes(device)
    title_ok = any(n["text"] == str(context.params["name"]) for n in nodes if n["id"] == "")
    return title_ok and _label(device) == int(context.params.get("value", 0))


def incremented(device, context) -> bool:
    r = context.result
    return (r.get("after") is not None and r["after"] == r["before"] + int(context.params.get("times", 1))
            and _label(device) == r["after"])


def counters_read(device, context) -> bool:
    got = context.result.get("counters")
    nodes = visible_nodes(device)
    titles = [n["text"] for n in _by_id(nodes, "row_title")]
    return isinstance(got, list) and len(got) > 0 and [c["name"] for c in got] == titles


def active_read(device, context) -> bool:
    a = context.result.get("active", {})
    return a.get("value") == _label(device) and a.get("value") is not None


def was_reset(device, context) -> bool:
    a = context.result.get("active", {})
    return a.get("value") == 0 and _label(device) == 0 and context.result.get("before") is not None
