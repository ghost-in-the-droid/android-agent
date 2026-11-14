"""Antimine skill helpers. python_action: (device, params, context) -> dict;
validators: (device, context) -> bool. Only on-screen nodes are read.

The minefield is drawn on a canvas and is not in the accessibility tree, so the
skill only reads the app bar (timer, mine counter), menus, stats and settings."""
from __future__ import annotations

import re
import time

_ID = "dev.lucanlm.antimine:id/"
MINES = {"beginner": 10, "intermediate": 40, "expert": 99, "master": 450}
BUTTON = {"beginner": "startBeginner", "intermediate": "startIntermediate", "expert": "startExpert", "master": "startMaster"}


def visible_nodes(device) -> list[dict]:
    """On-screen nodes: text, desc, id, bounds, checked (Portal tree keeps switch state)."""
    out: list[dict] = []
    tree = device.dump_portal_json() if hasattr(device, "dump_portal_json") else None
    if tree:
        stack = list(tree) if isinstance(tree, list) else [tree]
        while stack:
            n = stack.pop()
            b = n.get("boundsInScreen") or {}
            box = (b.get("left", 0), b.get("top", 0), b.get("right", 0), b.get("bottom", 0))
            if box[2] > box[0] and box[3] > box[1] and box[0] >= 0:
                out.append({"text": n.get("text") or "", "desc": n.get("contentDescription") or "",
                            "id": n.get("resourceId") or "", "bounds": box,
                            "checked": bool(n.get("isChecked")), "checkable": bool(n.get("isCheckable"))})
            stack.extend(reversed(n.get("children") or []))
        out.sort(key=lambda n: (n["bounds"][1], n["bounds"][0]))
        return out
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"text": a.get("text", ""), "desc": a.get("content-desc", ""), "id": a.get("resource-id", ""),
                        "bounds": tuple(nums), "checked": a.get("checked") == "true",
                        "checkable": a.get("checkable") == "true"})
    return out


def _get(nodes, suffix):
    return next((n["text"] for n in nodes if n["id"] == _ID + suffix), "")


def _wait(device, pred, timeout=15.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        nodes = visible_nodes(device)
        if pred(nodes):
            return nodes
        time.sleep(0.8)
    return None


# ── python_action targets ───────────────────────────────────────────────────

def close_app(device, params, context):
    device.adb("shell", "am", "force-stop", "dev.lucanlm.antimine")
    return {"success": True}


def check_difficulty(device, params, context):
    if str(params.get("difficulty", "")).lower() not in MINES:
        return {"success": False, "error": f"difficulty must be one of {sorted(MINES)}"}
    return {"success": True}


def reveal_center(device, params, context):
    """First tap in Antimine never hits a mine, so tapping the centre of the
    untouched board is a safe, deterministic opening move."""
    nodes = _wait(device, lambda ns: any(n["id"] == _ID + "tapToBegin" for n in ns), 15)
    if nodes is None:
        return {"success": False, "error": "board is not in its untouched state (TAP TO BEGIN missing)"}
    hint = next(n for n in nodes if n["id"] == _ID + "tapToBegin")
    b = hint["bounds"]
    device.tap((b[0] + b[2]) // 2, (b[1] + b[3]) // 2)
    time.sleep(2)
    return {"success": True}


def read_game(device, params, context):
    nodes = visible_nodes(device)
    mines = _get(nodes, "minesCount")
    data = {"difficulty": str(params.get("difficulty", "")).lower(),
            "mines_left": int(mines) if mines.isdigit() else None,
            "timer": _get(nodes, "timer") or None,
            "hints": int(_get(nodes, "hintCounter")) if _get(nodes, "hintCounter").isdigit() else None,
            "started": not any(n["id"] == _ID + "tapToBegin" for n in nodes)}
    return {"success": data["mines_left"] is not None, "data": {"game": data}, "error": "game bar not on screen"}


def read_stats(device, params, context):
    nodes = visible_nodes(device)
    if any(n["id"] == _ID + "empty" for n in nodes):
        return {"success": True, "data": {"stats": {}, "games_finished": 0}}
    texts = [n for n in nodes if n["text"] and n["bounds"][1] > 300]
    stats: dict[str, str] = {}
    for i, n in enumerate(texts[:-1]):
        nxt = texts[i + 1]
        if abs(nxt["bounds"][1] - n["bounds"][1]) <= 10 and nxt["bounds"][0] > n["bounds"][2]:
            stats[n["text"]] = nxt["text"]
    return {"success": True, "data": {"stats": stats, "games_finished": None}}


def read_settings(device, params, context):
    settings: dict[str, bool] = {}
    for _ in range(4):
        before = len(settings)
        for n in visible_nodes(device):
            if n["checkable"] and n["text"]:
                settings.setdefault(n["text"], n["checked"])
        if len(settings) == before and settings:
            break
        device.swipe(540, 1900, 540, 900, 300)
        time.sleep(0.8)
    return {"success": bool(settings), "data": {"settings": settings}, "error": "no switches found"}


# ── End-state validators: (device, context) -> bool ──────────────────────────

def new_game_ok(device, context) -> bool:
    g = context.result.get("game") or {}
    return g.get("mines_left") == MINES[g.get("difficulty", "")] and g.get("started") is False


def opened_ok(device, context) -> bool:
    g = context.result.get("game") or {}
    return g.get("started") is True and bool(g.get("timer"))


def stats_ok(device, context) -> bool:
    return isinstance(context.result.get("stats"), dict)


def settings_ok(device, context) -> bool:
    s = context.result.get("settings") or {}
    return len(s) >= 5
