"""outdoor-food-calculator helpers (Outdoor Food Calculator, org.birdbird.outdoorfoodcalc): plan trip food and nutrition, offline.

A Compose app. The calculator tab has the trip length in days, trip type chips (Short activity, Multi-day hike, Long
distance), a Food Items section with an Add Food button, and a bottom bar of five nutrient meters (Calories, Protein, Carbs,
Fat, Fiber) showing eaten per day / daily target. Add Food opens a dialog with an amount field and a long category list
where every food has an "Add <name>" button.
"""
from __future__ import annotations

import html
import re
import time

from gitd.bots.common.adb import input_text_arg

_PKG = "org.birdbird.outdoorfoodcalc"
_NUTRIENTS = ("Calories", "Protein", "Carbs", "Fat", "Fiber")
_TYPES = ("Short activity", "Multi-day hike", "Long distance")


def _nodes(device) -> list[dict]:
    out = []
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"text": html.unescape(a.get("text", "")).strip(), "desc": html.unescape(a.get("content-desc", "")).strip(),
                        "cls": a.get("class", "").split(".")[-1], "bounds": tuple(nums)})
    return out


def _centre(n):
    b = n["bounds"]
    return (b[0] + b[2]) // 2, (b[1] + b[3]) // 2


def _text(nodes, text):
    return next((n for n in nodes if n["text"] == text), None)


def _totals(nodes) -> dict:
    out = {}
    for name in _NUTRIENTS:
        lab = _text(nodes, name)
        if not lab:
            continue
        lx, ly = _centre(lab)
        cand = [n for n in nodes if re.fullmatch(r"\d+/\d+g?", n["text"]) and abs(_centre(n)[0] - lx) < 70 and 0 < n["bounds"][1] - lab["bounds"][1] < 80]
        pct = [n for n in nodes if re.fullmatch(r"\d+%", n["text"]) and abs(_centre(n)[0] - lx) < 70 and 0 < lab["bounds"][1] - n["bounds"][1] < 120]
        if cand:
            have, goal = re.match(r"(\d+)/(\d+)", cand[0]["text"]).groups()
            out[name.lower()] = {"per_day": int(have), "target": int(goal), "percent": int(pct[0]["text"][:-1]) if pct else None}
    return out


def read_state(device, nodes=None) -> dict:
    nodes = nodes if nodes is not None else _nodes(device)
    if _text(nodes, "Browse by category"):
        return {"screen": "dialog"}
    if _text(nodes, "Calories") and _text(nodes, "Trip duration and type"):
        days = next((n["text"] for n in nodes if n["cls"] == "EditText" and re.fullmatch(r"\d+", n["text"])), "")
        return {"screen": "calculator", "days": int(days) if days else None, "totals": _totals(nodes)}
    if _text(nodes, "Calories") and _text(nodes, "Food Items"):
        return {"screen": "calculator", "days": None, "totals": _totals(nodes)}
    return {"screen": "other"}


def _wait(device, want, tries=12):
    for _ in range(tries):
        st = read_state(device)
        if st["screen"] == want:
            return st
        time.sleep(0.7)
    raise RuntimeError(f"the {want} screen is not on screen")


def _to_top(device):
    for _ in range(3):
        if _text(_nodes(device), "Add Food") and _text(_nodes(device), "Trip duration and type"):
            return
        device.swipe(360, 500, 360, 1200, 300)
        time.sleep(0.5)


def _type_into(device, field, text):
    device.tap(*_centre(field), delay=0.5)
    device.adb("shell", "input", "keycombination", "KEYCODE_CTRL_LEFT", "KEYCODE_A")
    device.adb("shell", "input", "keyevent", "KEYCODE_DEL")
    device.adb("shell", "input", "text", input_text_arg(text))
    time.sleep(0.4)
    for _ in range(2):
        shown = device.adb("shell", "dumpsys", "input_method") or ""
        if "mInputShown=true" not in shown:
            break
        device.adb("shell", "input", "keyevent", "KEYCODE_BACK")  # only reached while the keyboard is up: it just hides it
        time.sleep(0.8)


# ── python_action targets ───────────────────────────────────────────────────

def restart_app(device, params, context):
    device.adb("shell", "am", "force-stop", _PKG)
    time.sleep(0.5)
    return {}


def open_calculator(device, params, context):
    return {"state": _wait(device, "calculator")}


def set_trip(device, params, context):
    days = params.get("days")
    trip = str(params.get("type") or "").strip()
    st = _wait(device, "calculator")
    _to_top(device)
    if days:
        d = int(days)
        if not 1 <= d <= 60:
            raise RuntimeError("days must be 1 to 60")
        field = next(n for n in _nodes(device) if n["cls"] == "EditText" and re.fullmatch(r"\d+", n["text"]))
        _type_into(device, field, str(d))
    if trip:
        match = next((t for t in _TYPES if t.lower() == trip.lower() or trip.lower() in t.lower()), None)
        if not match:
            raise RuntimeError(f"type must be one of {', '.join(_TYPES)}")
        _to_top(device)
        device.tap(*_centre(_text(_nodes(device), match)), delay=1.0)
    after = _wait(device, "calculator")
    return {"days": after["days"], "type": trip or None, "totals": after["totals"]}


def add_food(device, params, context):
    name = str(params.get("name") or "").strip().lower()
    grams = int(params.get("grams") or 100)
    if not name:
        raise RuntimeError("name must be a food such as Rice (dry) or Oat Flakes")
    if not 1 <= grams <= 5000:
        raise RuntimeError("grams must be 1 to 5000")
    before = _wait(device, "calculator")
    _to_top(device)
    device.tap(*_centre(_text(_nodes(device), "Add Food")), delay=1.5)
    _wait(device, "dialog")
    amount = next(n for n in _nodes(device) if n["cls"] == "EditText")
    _type_into(device, amount, str(grams))
    hit = None
    for _ in range(24):
        nodes = _nodes(device)
        names = [n for n in nodes if n["desc"].lower().startswith("add ") and n["desc"] != "Add Food"]
        hit = next((n for n in names if n["desc"][4:].lower() == name), None) or next((n for n in names if name in n["desc"][4:].lower()), None)
        if hit:
            break
        device.swipe(360, 1250, 360, 450, 500)
        time.sleep(0.6)
    if not hit:
        raise RuntimeError(f"no food matching {params.get('name')} in the list")
    food = hit["desc"][4:]
    device.tap(*_centre(hit), delay=1.4)
    after = _wait(device, "calculator")
    return {"food": food, "grams": grams, "totals": after["totals"], "calories_before": before["totals"].get("calories", {}).get("per_day"), "days": after["days"]}


def seed_food(device, params, context):
    """Pre-step: make sure something has been added so the totals are not empty."""
    st = _wait(device, "calculator")
    if not (st["totals"].get("calories") or {}).get("per_day"):
        add_food(device, {"name": "Rice (dry)", "grams": 200}, context)
    return {}


def get_totals(device, params, context):
    return {"state": _wait(device, "calculator")}


# ── validators ──────────────────────────────────────────────────────────────

def calculator_open(device, context) -> bool:
    return read_state(device)["screen"] == "calculator"


def trip_set(device, context) -> bool:
    s = read_state(device)
    return s["screen"] == "calculator" and (context.result["days"] is None or s["days"] == context.result["days"])


def food_added(device, context) -> bool:
    s = read_state(device)
    r = context.result
    return s["screen"] == "calculator" and (s["totals"].get("calories") or {}).get("per_day", 0) > 0 and bool(r["food"])


def totals_read(device, context) -> bool:
    s = read_state(device)
    return s["screen"] == "calculator" and s["totals"] == context.result["state"]["totals"]
