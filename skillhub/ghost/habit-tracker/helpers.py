"""habit-tracker helpers (Loop Habit Tracker, org.isoron.uhabits).

List screen: one row per habit (name TextView) and four day cells to its right (today, yesterday, ...). A tap on a cell
opens a small dialog with yes/no buttons (`yesBtn` / `noBtn`); the check mark itself is drawn, so the state is read from
the habit's detail screen (Score, Total).

python_action signature: (device, params, context) -> {"data": {...}} (the engine merges "data" into context.result; a bare dict is dropped)
validator signature:     (device, context) -> bool
"""
from __future__ import annotations

import re
import time

_ID = "org.isoron.uhabits:id/"
_DAY_X = [400, 490, 580, 670]


def _nodes(device) -> list[dict]:
    out = []
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"text": a.get("text", ""), "desc": a.get("content-desc", ""), "id": a.get("resource-id", ""),
                        "bounds": tuple(nums)})
    return out


def _by(nodes, suffix):
    return [n for n in nodes if n["id"] == _ID + suffix]


def _centre(n):
    b = n["bounds"]
    return (b[0] + b[2]) // 2, (b[1] + b[3]) // 2


def _tap(device, n, delay=1.0):
    device.tap(*_centre(n), delay=delay)


def _wait(device, suffix, timeout=6.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        hit = _by(_nodes(device), suffix)
        if hit:
            return hit[0]
        time.sleep(0.5)
    raise RuntimeError(f"{suffix} did not appear")


def habit_rows(nodes) -> list[dict]:
    """Habit names on the list screen: TextViews below the day header, left of the day cells."""
    return [n for n in nodes if not n["id"] and n["text"] and n["bounds"][1] > 235 and n["bounds"][2] < 360
            and n["bounds"][0] < 120 and n["text"] not in ("You have no active habits",)]


# ── python_action targets ───────────────────────────────────────────────────

def create(device, params, context):
    name = str(params["name"]).strip()
    if not name:
        raise RuntimeError("name is empty")
    _tap(device, _by(_nodes(device), "actionCreateHabit")[0], delay=1.5)
    _tap(device, _wait(device, "buttonYesNo"), delay=1.5)
    field = _wait(device, "nameInput")
    _tap(device, field, delay=0.6)
    device.adb("shell", "input", "text", name.replace(" ", "%s"))
    device.back()  # hide the keyboard
    time.sleep(0.6)
    q = str(params.get("question", "")).strip()
    if q:
        _tap(device, _by(_nodes(device), "questionInput")[0], delay=0.6)
        device.adb("shell", "input", "text", q.replace(" ", "%s"))
        device.back()
        time.sleep(0.6)
    _tap(device, _by(_nodes(device), "buttonSave")[0], delay=2.0)
    return {"data": {"created": name, "habits": [n["text"] for n in habit_rows(_nodes(device))]}}


def check(device, params, context):
    name = str(params["name"]).strip()
    day = int(params.get("day", 0))
    result = {"yes": "done", "true": "done", "1": "done", "no": "missed", "false": "missed", "0": "missed"}.get(
        str(params.get("result", "done")).lower(), str(params.get("result", "done")).lower())
    if day not in (0, 1, 2, 3) or result not in ("done", "missed"):
        raise RuntimeError("day must be 0 (today) to 3 and result done or missed")
    row = next((n for n in habit_rows(_nodes(device)) if n["text"] == name), None)
    if not row:
        raise RuntimeError(f"no habit named {name!r} on the list")
    y = (row["bounds"][1] + row["bounds"][3]) // 2
    device.tap(_DAY_X[day], y, delay=1.0)
    btn = _wait(device, "yesBtn" if result == "done" else "noBtn")
    _tap(device, btn, delay=1.2)
    return {"data": {"habit": name, "day": day, "result": result}}


def list_habits(device, params, context):
    return {"data": {"habits": [n["text"] for n in habit_rows(_nodes(device))]}}


def stats(device, params, context):
    name = str(params["name"]).strip()
    row = next((n for n in habit_rows(_nodes(device)) if n["text"] == name), None)
    if not row:
        raise RuntimeError(f"no habit named {name!r} on the list")
    _tap(device, row, delay=2.5)
    _wait(device, "scoreLabel")
    nodes = _nodes(device)

    def get(sfx):
        return next((n["text"] for n in _by(nodes, sfx)), "")
    out = {"habit": name, "score": get("scoreLabel"), "month": get("monthDiffLabel"), "year": get("yearDiffLabel"),
           "total": get("totalCountLabel"), "frequency": get("frequencyLabel")}
    device.back()
    time.sleep(1.2)
    return {"data": {"stats": out}}


# ── validators ──────────────────────────────────────────────────────────────

def on_list(device, context) -> bool:
    return bool(_by(_nodes(device), "actionCreateHabit"))


def created(device, context) -> bool:
    name = context.result.get("created")
    return on_list(device, context) and any(n["text"] == name for n in habit_rows(_nodes(device)))


def checked(device, context) -> bool:
    return on_list(device, context) and not _by(_nodes(device), "yesBtn")


def listed(device, context) -> bool:
    got = context.result.get("habits")
    return on_list(device, context) and got == [n["text"] for n in habit_rows(_nodes(device))]


def stats_read(device, context) -> bool:
    s = context.result.get("stats", {})
    return on_list(device, context) and s.get("total", "").isdigit() and s.get("score", "").endswith("%")
