"""kin-nai-d helpers (Kin Nai D, com.icesu.kinnaid): let the app pick what you eat from your own list, offline.

Screens: the picker (mode buttons, a food field with ADD FOOD, the food list with a delete icon per row, START RANDOM)
and the result (Your Food is ..., the chosen food, RANDOM AGAIN, which goes back to the picker). The food list is kept
between launches. The picker is the root of the back stack, so the skill never uses BACK.
"""
from __future__ import annotations

import html
import re
import time

from gitd.bots.common.adb import input_text_arg

_PKG = "com.icesu.kinnaid"


def _nodes(device) -> list[dict]:
    out = []
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"id": a.get("resource-id", "").split("/")[-1], "text": html.unescape(a.get("text", "")).strip(), "bounds": tuple(nums)})
    return out


def _by(nodes, ident):
    return next((n for n in nodes if n["id"] == ident), None)


def _centre(n):
    b = n["bounds"]
    return (b[0] + b[2]) // 2, (b[1] + b[3]) // 2


def _foods(nodes) -> list[dict]:
    names = sorted((n for n in nodes if n["id"] == "txtfood"), key=lambda n: n["bounds"][1])
    dels = sorted((n for n in nodes if n["id"] == "food_delete"), key=lambda n: n["bounds"][1])
    return [{"name": n["text"], "delete": d} for n, d in zip(names, dels)]


def read_state(device, nodes=None) -> dict:
    nodes = nodes if nodes is not None else _nodes(device)
    if _by(nodes, "tvResultTitle"):
        won = _by(nodes, "food_result")
        return {"screen": "result", "food": won["text"] if won else ""}
    if _by(nodes, "edt_addfood"):
        return {"screen": "picker", "foods": [f["name"] for f in _foods(nodes)]}
    return {"screen": "other"}


def _wait(device, want, tries=12):
    for _ in range(tries):
        st = read_state(device)
        if st["screen"] in (want if isinstance(want, tuple) else (want,)):
            return st
        time.sleep(0.7)
    raise RuntimeError(f"the {want} screen is not on screen")


def _to_picker(device):
    if read_state(device)["screen"] == "result":
        device.tap(*_centre(_by(_nodes(device), "spin_again")), delay=1.5)  # RANDOM AGAIN returns to the picker
    return _wait(device, "picker")


def _result(device, tries=16):
    for _ in range(tries):
        st = read_state(device)
        if st["screen"] == "result" and st["food"]:
            return st
        time.sleep(0.7)
    raise RuntimeError("no result appeared")


# ── python_action targets ───────────────────────────────────────────────────

def restart_app(device, params, context):
    device.adb("shell", "am", "force-stop", _PKG)
    time.sleep(0.5)
    return {}


def open_picker(device, params, context):
    return {"state": _wait(device, "picker")}


def list_foods(device, params, context):
    return {"state": _to_picker(device)}


def add_food(device, params, context):
    name = str(params.get("name") or "").strip()
    if not name or len(name) > 30:
        raise RuntimeError("name must be a food of 1 to 30 characters")
    st = _to_picker(device)
    device.tap(*_centre(_by(_nodes(device), "edt_addfood")), delay=0.5)
    device.adb("shell", "input", "text", input_text_arg(name))
    time.sleep(0.5)
    device.tap(*_centre(_by(_nodes(device), "addFood")), delay=1.0)
    after = _wait(device, "picker")
    if len(after["foods"]) <= len(st["foods"]):
        raise RuntimeError("the food was not added (duplicate or empty?)")
    return {"added": name, "foods": after["foods"]}


def remove_food(device, params, context):
    name = str(params.get("name") or "").strip().lower()
    _to_picker(device)
    row = next((f for f in _foods(_nodes(device)) if f["name"].lower() == name), None)
    if not row:
        raise RuntimeError(f"no food named {params.get('name')} in the list")
    device.tap(*_centre(row["delete"]), delay=1.0)
    after = _wait(device, "picker")
    return {"removed": row["name"], "foods": after["foods"]}


def seed_foods(device, params, context):
    """Pre-step: make sure at least two foods are listed."""
    foods = _to_picker(device)["foods"]
    for f in ("Pizza", "Sushi", "Ramen"):
        if len(foods) >= 2:
            break
        if f not in foods:
            foods = add_food(device, {"name": f}, context)["foods"]
    return {}


def seed_pizza(device, params, context):
    """Pre-step: make sure Pizza is in the list."""
    if "Pizza" not in _to_picker(device)["foods"]:
        add_food(device, {"name": "Pizza"}, context)
    return {}


def spin(device, params, context):
    st = _to_picker(device)
    if len(st["foods"]) < 2:
        raise RuntimeError("add at least two foods first")
    device.tap(*_centre(_by(_nodes(device), "btnSpinFood")), delay=1.0)
    won = _result(device)
    return {"food": won["food"], "from": st["foods"]}


# ── validators ──────────────────────────────────────────────────────────────

def picker_open(device, context) -> bool:
    return read_state(device)["screen"] == "picker"


def foods_listed(device, context) -> bool:
    s = read_state(device)
    return s["screen"] == "picker" and s["foods"] == context.result["state"]["foods"]


def food_added(device, context) -> bool:
    s = read_state(device)
    return s["screen"] == "picker" and context.result["added"] in s["foods"]


def food_removed(device, context) -> bool:
    s = read_state(device)
    return s["screen"] == "picker" and context.result["removed"] not in s["foods"]


def spun(device, context) -> bool:
    s = read_state(device)
    return s["screen"] == "result" and s["food"] == context.result["food"]
