"""shopping-list helpers (Shopping List by woefe, com.woefe.shoppinglist).

python_action signature: (device, params, context) -> {"data": {...}} (the engine merges "data" into context.result; a bare dict is dropped)
validator signature:     (device, context) -> bool
"""
from __future__ import annotations

import re
import time

_ID = "com.woefe.shoppinglist:id/"


def visible_nodes(device) -> list[dict]:
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


def _type(device, text):
    device.adb("shell", "input", "text", str(text).replace(" ", "%s"))
    time.sleep(0.3)


def read_items_from(nodes) -> list[dict]:
    """Rows = text_description nodes; quantity = the text_quantity node on the same row (may be empty)."""
    qty = _by_id(nodes, "text_quantity")
    rows = []
    for d in _by_id(nodes, "text_description"):
        cy = (d["bounds"][1] + d["bounds"][3]) // 2
        q = next((n["text"] for n in qty if n["bounds"][1] <= cy <= n["bounds"][3]), "")
        rows.append({"name": d["text"], "quantity": q})
    return rows


def _ensure_panel(device):
    """Open the add-item panel (it stays open between items) and return its nodes."""
    nodes = visible_nodes(device)
    if not _by_id(nodes, "new_item_description"):
        fab = _by_id(nodes, "fab_add")
        if not fab:
            raise RuntimeError("add button not on screen")
        device.tap(*_center(fab[0]["bounds"]))
        time.sleep(1.0)
        nodes = visible_nodes(device)
    return nodes


def _add_one(device, name, quantity=""):
    nodes = _ensure_panel(device)
    desc = _by_id(nodes, "new_item_description")[0]
    device.tap(*_center(desc["bounds"]))
    time.sleep(0.4)
    _type(device, name)
    if quantity not in ("", None):
        qty = _by_id(visible_nodes(device), "new_item_quantity")[0]
        device.tap(*_center(qty["bounds"]))
        time.sleep(0.3)
        _type(device, quantity)
    done = _by_id(visible_nodes(device), "button_add_new_item")[0]
    device.tap(*_center(done["bounds"]))
    time.sleep(0.8)


# ── python_action targets ───────────────────────────────────────────────────

def add_item(device, params, context):
    _add_one(device, params["name"], params.get("quantity", ""))
    return {"data": {"added": [{"name": str(params["name"]), "quantity": str(params.get("quantity", ""))}]}}


def add_items(device, params, context):
    raw = params["items"]
    items = raw if isinstance(raw, list) else [s.strip() for s in str(raw).split(",") if s.strip()]
    for it in items:
        _add_one(device, it)
    return {"data": {"added": [{"name": str(i), "quantity": ""} for i in items]}}


def check_item(device, params, context):
    want = str(params["name"])
    rows = [n for n in _by_id(visible_nodes(device), "text_description") if n["text"] == want]
    if not rows:
        raise RuntimeError(f"no item named {want!r} on the list")
    device.tap(*_center(rows[0]["bounds"]))
    time.sleep(0.6)
    return {"data": {"tapped": want}}


def require_confirm(device, params, context):
    # the CLI parses `confirm=yes` as a YAML boolean, so True arrives as well as "yes"
    if str(params.get("confirm", "")).lower() not in ("yes", "true", "1"):
        raise RuntimeError("remove_checked deletes the checked items: pass confirm=yes")
    return {}


def read_items(device, params, context):
    # the add panel stays open at the bottom (first BACK hides the keyboard, the second closes the panel)
    for _ in range(3):
        if _by_id(visible_nodes(device), "fab_add"):
            break
        device.back()
        time.sleep(0.7)
    return {"data": {"items": read_items_from(visible_nodes(device))}}


# ── validators ──────────────────────────────────────────────────────────────

def items_added(device, context) -> bool:
    shown = read_items_from(visible_nodes(device))
    for a in context.result.get("added", []):
        if not any(r["name"] == a["name"] and (not a["quantity"] or r["quantity"] == a["quantity"]) for r in shown):
            return False
    return bool(context.result.get("added"))


def items_read(device, context) -> bool:
    got = context.result.get("items")
    return isinstance(got, list) and got == read_items_from(visible_nodes(device))


def item_tapped(device, context) -> bool:
    want = context.result.get("tapped")
    return bool(want) and any(r["name"] == want for r in read_items_from(visible_nodes(device)))
