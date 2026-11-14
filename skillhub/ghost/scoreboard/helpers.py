"""scoreboard helpers (Scoreboard by vatbub, com.github.vatbub.scoreboard): a local score table for game nights.

Players are header EditTexts, each round is a row of score EditTexts, the totals are the TextViews under the table.
Everything is readable, so the table is parsed from the tree. No account, nothing leaves the phone.
"""
from __future__ import annotations

import html
import re
import time

_PKG = "com.github.vatbub.scoreboard"
_ID = _PKG + ":id/"


def _nodes(device) -> list[dict]:
    out = []
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"text": html.unescape(a.get("text", "")), "id": a.get("resource-id", "").split("/")[-1],
                        "cls": a.get("class", ""), "bounds": tuple(nums)})
    return out


def _centre(n):
    b = n["bounds"]
    return (b[0] + b[2]) // 2, (b[1] + b[3]) // 2


def read_table(device) -> dict:
    nodes = _nodes(device)
    edits = [n for n in nodes if n["cls"].endswith("EditText")]
    if not edits:
        return {"in_app": any(n["id"] == "fab" for n in nodes), "players": [], "rounds": [], "totals": []}
    head_y = min(n["bounds"][1] for n in edits)
    header = sorted((n for n in edits if n["bounds"][1] == head_y), key=lambda n: n["bounds"][0])
    cells = [n for n in edits if n["bounds"][1] > head_y]
    ys = sorted({n["bounds"][1] for n in cells})
    rounds = [[next((c["text"] for c in cells if c["bounds"][1] == y and c["bounds"][0] == h["bounds"][0]), "")
               for h in header] for y in ys]
    last_y = ys[-1] if ys else head_y
    tot_nodes = sorted((n for n in nodes if n["cls"].endswith("TextView") and n["id"] == "" and n["bounds"][1] > last_y + 60
                        and re.fullmatch(r"-?\d+(\.\d+)?", n["text"])), key=lambda n: n["bounds"][0])
    return {"in_app": True, "players": [h["text"] for h in header], "rounds": rounds,
            "totals": [n["text"] for n in tot_nodes]}


def _node(device, ident):
    return next((n for n in _nodes(device) if n["id"] == ident), None)


def _set_edit(device, n, text):
    device.tap(*_centre(n), delay=0.4)
    device.adb("shell", "input", "keyevent", "KEYCODE_MOVE_END")
    for _ in range(24):
        device.adb("shell", "input", "keyevent", "KEYCODE_DEL")
    device.adb("shell", "input", "text", text.replace(" ", "%s"))
    time.sleep(0.4)


def _commit(device):
    device.adb("shell", "input", "keyevent", "KEYCODE_BACK")  # close the keyboard
    time.sleep(0.8)


# ── python_action targets ───────────────────────────────────────────────────

def add_player(device, params, context):
    before = read_table(device)
    btn = _node(device, "action_add_player")
    if not btn:
        raise RuntimeError("add player button not found")
    device.tap(*_centre(btn), delay=1.2)
    name = str(params.get("name", "")).strip()
    if name:
        if not re.fullmatch(r"[A-Za-z0-9 ]{1,20}", name):
            raise RuntimeError("name: 1-20 letters, digits or spaces")
        header = sorted((n for n in _nodes(device) if n["cls"].endswith("EditText")), key=lambda n: (n["bounds"][1], n["bounds"][0]))
        head_y = header[0]["bounds"][1]
        newest = max((n for n in header if n["bounds"][1] == head_y), key=lambda n: n["bounds"][0])
        _set_edit(device, newest, name)
        _commit(device)
    return {"name": name, "before": before, "table": read_table(device)}


def add_round(device, params, context):
    before = read_table(device)
    fab = _node(device, "fab")
    if not fab:
        raise RuntimeError("round button not found")
    device.tap(*_centre(fab), delay=1.2)
    return {"before": before, "table": read_table(device)}


def set_score(device, params, context):
    rnd, player, value = int(params["round"]), int(params["player"]), int(params["value"])
    nodes = _nodes(device)
    edits = [n for n in nodes if n["cls"].endswith("EditText")]
    if not edits:
        raise RuntimeError("no table on screen")
    head_y = min(n["bounds"][1] for n in edits)
    header = sorted((n for n in edits if n["bounds"][1] == head_y), key=lambda n: n["bounds"][0])
    ys = sorted({n["bounds"][1] for n in edits if n["bounds"][1] > head_y})
    if not (1 <= player <= len(header)) or not (1 <= rnd <= len(ys)):
        raise RuntimeError(f"table has {len(header)} players and {len(ys)} rounds (1-based)")
    cell = next(n for n in edits if n["bounds"][1] == ys[rnd - 1] and n["bounds"][0] == header[player - 1]["bounds"][0])
    before = read_table(device)
    _set_edit(device, cell, str(value))
    _commit(device)
    return {"round": rnd, "player": player, "value": value, "before": before, "table": read_table(device)}


def get_scores(device, params, context):
    return {"table": read_table(device)}


# ── validators ──────────────────────────────────────────────────────────────

def player_added(device, context) -> bool:
    r = context.result
    now = read_table(device)
    return len(now["players"]) == len(r["before"]["players"]) + 1 and (not r["name"] or now["players"][-1] == r["name"])


def round_added(device, context) -> bool:
    return len(read_table(device)["rounds"]) == len(context.result["before"]["rounds"]) + 1


def score_set(device, context) -> bool:
    r = context.result
    now = read_table(device)
    return now["rounds"][r["round"] - 1][r["player"] - 1] == str(r["value"])


def table_read(device, context) -> bool:
    return read_table(device)["rounds"] == context.result["table"]["rounds"]
