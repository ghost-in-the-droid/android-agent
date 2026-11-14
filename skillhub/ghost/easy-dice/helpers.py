"""easy-dice helpers (Easy Dice, net.pejici.easydice): roll a hand of polyhedral dice offline.

The bottom palette holds nine dice (d2 d4 d6 d8 d10 d100 d12 d20 d30); tapping one adds it to the hand shown in the play area.
ROLL animates, then hand_sum_text_view reads "Adds to N". Individual faces are drawn, not text, so only the sum is readable.
"""
from __future__ import annotations

import html
import re
import time

_PKG = "net.pejici.easydice"
# palette centres by die size: two rows under the ROLL button
_PALETTE = {2: (85, 1385), 4: (195, 1385), 6: (305, 1385), 8: (415, 1385), 10: (525, 1385), 100: (635, 1385),
            12: (85, 1490), 20: (195, 1490), 30: (305, 1490)}
_MAX_DICE = 12


def _nodes(device) -> list[dict]:
    out = []
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1]:
            out.append({"id": a.get("resource-id", "").split("/")[-1], "text": html.unescape(a.get("text", "")).strip(),
                        "cls": a.get("class", "").split(".")[-1], "bounds": tuple(nums)})
    return out


def _centre(n):
    b = n["bounds"]
    return (b[0] + b[2]) // 2, (b[1] + b[3]) // 2


def read_state(device, nodes=None) -> dict:
    nodes = nodes if nodes is not None else _nodes(device)
    sumn = next((n for n in nodes if n["id"] == "hand_sum_text_view"), None)
    if not sumn or not any(n["id"] == "roll_button" for n in nodes):
        return {"screen": "other"}
    m = re.search(r"Adds to (\d+)", sumn["text"])
    dice = [n for n in nodes if n["cls"] == "View" and 200 < n["bounds"][1] < 1140 and n["bounds"][2] - n["bounds"][0] > 90]
    return {"screen": "dice", "dice_count": len(dice), "sum": int(m.group(1)) if m else None}


def _wait(device, tries=12):
    for _ in range(tries):
        st = read_state(device)
        if st["screen"] == "dice":
            return st
        time.sleep(0.7)
    raise RuntimeError("the dice screen is not on screen")


def _button(device, rid):
    return next(n for n in _nodes(device) if n["id"] == rid)


def _add(device, sides, count):
    if sides not in _PALETTE:
        raise RuntimeError(f"sides must be one of {sorted(_PALETTE)}")
    if not 1 <= count <= _MAX_DICE:
        raise RuntimeError(f"count must be 1 to {_MAX_DICE}")
    for _ in range(count):
        device.tap(*_PALETTE[sides], delay=0.5)


def _roll(device) -> dict:
    st = _wait(device)
    if not st["dice_count"]:
        raise RuntimeError("add some dice first")
    device.tap(*_centre(_button(device, "roll_button")), delay=3.0)
    prev = None
    for _ in range(8):
        cur = read_state(device)
        if cur["sum"] is not None and cur["sum"] == prev:
            return cur
        prev = cur["sum"]
        time.sleep(1.0)
    return read_state(device)


# ── python_action targets ───────────────────────────────────────────────────

def restart_app(device, params, context):
    device.adb("shell", "am", "force-stop", _PKG)
    time.sleep(0.5)
    device.adb("shell", "monkey", "-p", _PKG, "-c", "android.intent.category.LAUNCHER", "1")  # later pre-steps need the app up
    time.sleep(2.5)
    return {}


def open_dice(device, params, context):
    return {"state": _wait(device)}


def add_dice(device, params, context):
    sides = int(params.get("sides") or 6)
    count = int(params.get("count") or 1)
    _wait(device)
    _add(device, sides, count)
    return {"sides": sides, "added": count, "state": read_state(device)}


def roll(device, params, context):
    return {"state": _roll(device)}


def reset_hand(device, params, context):
    _wait(device)
    device.tap(*_centre(_button(device, "reset_button")), delay=1.0)
    return {"state": read_state(device)}


def roll_dice(device, params, context):
    spec = str(params.get("spec") or "").lower().replace(" ", "")
    parts = re.findall(r"(\d*)d(\d+)", spec)
    if not parts or re.sub(r"(\d*)d(\d+)|\+", "", spec):
        raise RuntimeError("spec must look like 2d6+d20")
    _wait(device)
    device.tap(*_centre(_button(device, "reset_button")), delay=1.0)
    dice = []
    for n, s in parts:
        c = int(n or 1)
        _add(device, int(s), c)
        dice += [int(s)] * c
    st = _roll(device)
    return {"spec": spec, "dice": dice, "sum": st["sum"], "dice_count": st["dice_count"]}


def seed_hand(device, params, context):
    st = _wait(device)
    if not st["dice_count"]:
        _add(device, 6, 2)
    return {}


# ── validators ──────────────────────────────────────────────────────────────

def dice_open(device, context) -> bool:
    return read_state(device)["screen"] == "dice"


def dice_added(device, context) -> bool:
    s = read_state(device)
    return s["screen"] == "dice" and s["dice_count"] >= context.result["added"] and s["sum"] is not None


def rolled(device, context) -> bool:
    s = read_state(device)
    return s["screen"] == "dice" and s["sum"] == context.result["state"]["sum"] and s["sum"] is not None and s["sum"] >= s["dice_count"]


def hand_reset(device, context) -> bool:
    s = read_state(device)
    return s["screen"] == "dice" and s["dice_count"] == 0 and s["sum"] is None


def hand_rolled(device, context) -> bool:
    s = read_state(device)
    r = context.result
    return s["screen"] == "dice" and s["sum"] == r["sum"] and r["sum"] >= len(r["dice"]) and r["sum"] <= sum(r["dice"])
