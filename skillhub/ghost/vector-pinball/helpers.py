"""vector-pinball helpers (Vector Pinball, com.dozingcatsoftware.bouncy).

The table is drawn on a canvas and the score is painted in the header (not in the accessibility tree).
Menus are real widgets with ids. State: main menu has `startGameButton`; paused has `resumeGameButton`;
neither of them means a ball is in play. The left half of the screen drives the left flipper, the right half the right one.

python_action signature: (device, params, context) -> {"data": {...}} (the engine merges "data" into context.result; a bare dict is dropped)
validator signature:     (device, context) -> bool
"""
from __future__ import annotations

import re
import time

_ID = "com.dozingcatsoftware.bouncy:id/"


def visible_nodes(device) -> list[dict]:
    out = []
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"text": a.get("text", ""), "id": a.get("resource-id", ""), "bounds": tuple(nums)})
    return out


def _by(nodes, suffix):
    return [n for n in nodes if n["id"] == _ID + suffix]


def _tap_node(device, node):
    b = node["bounds"]
    device.tap((b[0] + b[2]) // 2, (b[1] + b[3]) // 2, delay=0.8)


def _dims(device):
    m = re.search(r"(\d+)x(\d+)", device.adb("shell", "wm", "size"))
    return (int(m.group(1)), int(m.group(2))) if m else (720, 1600)


def state_of(nodes) -> str:
    if _by(nodes, "startGameButton"):
        return "menu"
    if _by(nodes, "resumeGameButton"):
        return "paused"
    if _by(nodes, "hideHighScoreButton"):
        return "high_scores"
    if _by(nodes, "scoreView"):
        return "playing"
    return "unknown"


def _read_high_scores(device) -> list[str]:
    """Open High Scores from the current menu, read the lines, close it again."""
    nodes = visible_nodes(device)
    btn = _by(nodes, "highScoreButton")
    if not btn:
        return []
    _tap_node(device, btn[0])
    time.sleep(0.8)
    nodes = visible_nodes(device)
    lines = [n["text"] for n in nodes if n["text"] and n["id"] != _ID + "hideHighScoreButton"
             and n["text"] != "High scores"]
    ok = _by(nodes, "hideHighScoreButton")
    if ok:
        _tap_node(device, ok[0])
    return lines


def to_menu(device):
    """Whatever the state: pause, END GAME if a game runs, until the main menu shows."""
    for _ in range(6):
        nodes = visible_nodes(device)
        st = state_of(nodes)
        if st == "menu":
            return
        if st == "playing":
            w, _h = _dims(device)
            device.tap(52, 98, delay=1.0)  # pause icon
        elif st == "paused":
            end = _by(nodes, "endGameButton")
            if end:
                _tap_node(device, end[0])
        elif st == "high_scores":
            _tap_node(device, _by(nodes, "hideHighScoreButton")[0])
        else:
            device.back()
        time.sleep(0.8)
    raise RuntimeError("could not reach the main menu")


# ── python_action targets ───────────────────────────────────────────────────

def go_to_menu(device, params, context):
    to_menu(device)
    return {}


def pick_table(device, params, context):
    """params.steps: 0, +N (next table) or -N (previous); on the main menu only."""
    steps = int(params.get("steps", 0))
    nodes = visible_nodes(device)
    btn = _by(nodes, "nextTableButton" if steps > 0 else "previousTableButton")
    for _ in range(abs(steps)):
        if not btn:
            raise RuntimeError("table buttons not on screen (open the main menu first)")
        _tap_node(device, btn[0])
    label = next((n["text"] for n in visible_nodes(device) if n["id"] == _ID + "selectTableLabel"), "")
    return {"data": {"table_label": label, "steps": steps}}


def press_start(device, params, context):
    nodes = visible_nodes(device)
    start = _by(nodes, "startGameButton")
    if not start:
        raise RuntimeError("START GAME not on screen")
    if str(params.get("unlimited_balls", "")).lower() in ("true", "yes", "1"):
        cb = _by(nodes, "unlimitedBallsToggle")
        if cb:
            _tap_node(device, cb[0])
    _tap_node(device, start[0])
    time.sleep(1.5)
    return {}


def launch_ball(device, params, context):
    """The first touch on the table launches the ball."""
    w, h = _dims(device)
    device.tap(w // 2, int(h * 0.5), delay=1.0)
    return {"data": {"state": state_of(visible_nodes(device))}}


def flip(device, params, context):
    side = str(params.get("side", "both")).lower()
    times = max(1, min(int(params.get("times", 1)), 30))
    w, h = _dims(device)
    if state_of(visible_nodes(device)) != "playing":
        raise RuntimeError("no ball in play: run start_game first")
    y = int(h * 0.82)
    xs = {"left": [w // 4], "right": [3 * w // 4], "both": [w // 4, 3 * w // 4]}.get(side)
    if xs is None:
        raise RuntimeError("side must be left, right or both")
    for _ in range(times):
        for x in xs:
            device.tap(x, y, delay=0.12)
        time.sleep(0.25)
    return {"data": {"side": side, "times": times, "state": state_of(visible_nodes(device))}}


def read_status(device, params, context):
    nodes = visible_nodes(device)
    st = state_of(nodes)
    out = {"state": st}
    if st == "menu":
        out["table_label"] = next((n["text"] for n in _by(nodes, "selectTableLabel")), "")
        out["high_scores"] = _read_high_scores(device)
    elif st == "paused":
        out["high_scores"] = _read_high_scores(device)
    return {"data": {"status": out}}


# ── validators ──────────────────────────────────────────────────────────────

def in_menu(device, context) -> bool:
    return state_of(visible_nodes(device)) == "menu"


def in_play(device, context) -> bool:
    return state_of(visible_nodes(device)) == "playing"


def flipped(device, context) -> bool:
    r = context.result
    return r.get("times", 0) >= 1 and state_of(visible_nodes(device)) in ("playing", "menu", "paused")


def table_picked(device, context) -> bool:
    return bool(context.result.get("table_label")) and state_of(visible_nodes(device)) == "menu"


def status_read(device, context) -> bool:
    st = context.result.get("status", {})
    return st.get("state") in ("menu", "paused", "playing") and state_of(visible_nodes(device)) == st["state"]
