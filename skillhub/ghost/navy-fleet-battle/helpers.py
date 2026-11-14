"""navy-fleet-battle helpers (Navy Fleet Battle, net.tigr.navyfleetbattle): classic sea battle against the computer.

The two 10x10 fields are drawn on a canvas, so cells are tapped by pinned coordinates (720x1600 screen). What is
readable as text: whose turn it is, the hint line (hit - shoot again), and how many enemy and own ships of each
size are left. A miss is recognised because the computer answers ("Computer's shot"). The result of the
computer's own shot is not readable.
"""
from __future__ import annotations

import html
import re
import time

_PKG = "net.tigr.navyfleetbattle"
# battle screen: enemy field cell centres (column 1 / row A) and step, Fire button
_X0, _Y0, _STEP = 124, 364, 58.6
_FIRE = (360, 992)


def _nodes(device) -> list[dict]:
    out = []
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"text": html.unescape(a.get("text", "")), "bounds": tuple(nums)})
    return out


def _centre(n):
    b = n["bounds"]
    return (b[0] + b[2]) // 2, (b[1] + b[3]) // 2


def _text(nodes, t):
    return next((n for n in nodes if n["text"] == t), None)


def _counts(nodes, y_lo, y_hi, by_x: bool) -> list[int]:
    cells = [n for n in nodes if re.fullmatch(r"× \d+", n["text"]) and y_lo <= n["bounds"][1] <= y_hi]
    cells.sort(key=lambda n: n["bounds"][0] if by_x else n["bounds"][1])
    return [int(n["text"][2:]) for n in cells]


def read_state(device, nodes=None) -> dict:
    nodes = nodes if nodes is not None else _nodes(device)
    if _text(nodes, "Play the computer"):
        return {"screen": "menu"}
    if _text(nodes, "Place your ships"):
        return {"screen": "placing"}
    if _text(nodes, "Fire!") and _text(nodes, "The other field"):
        head = sorted((n for n in nodes if n["text"] and n["bounds"][1] < 170 and n["bounds"][0] < 600), key=lambda n: n["bounds"][1])
        title = head[0]["text"] if head else ""
        hint = head[1]["text"] if len(head) > 1 else ""
        return {"screen": "battle", "status": title, "hint": hint,
                "enemy_ships_left": _counts(nodes, 200, 300, True), "own_ships_left": _counts(nodes, 1090, 1300, False),
                "game_over": title not in ("Your turn", "Computer's shot")}
    return {"screen": "other"}


def _wait(device, want, tries=12):
    for _ in range(tries):
        st = read_state(device)
        if st["screen"] == want:
            return st
        time.sleep(0.8)
    raise RuntimeError(f"the {want} screen is not on screen")


def _cell(cell: str):
    m = re.fullmatch(r"([A-Ja-j])(10|[1-9])", str(cell).strip())
    if not m:
        raise RuntimeError(f"bad cell {cell!r}: use a letter A-J and a number 1-10, for example B5")
    row = "ABCDEFGHIJ".index(m.group(1).upper())
    col = int(m.group(2)) - 1
    return f"{m.group(1).upper()}{col + 1}", int(_X0 + _STEP * col), int(_Y0 + _STEP * row)


def _settle(device, tries=20) -> dict:
    """After Fire: wait until it is the player's turn again (or the game ends). Returns the result and state."""
    saw_computer = False
    for _ in range(tries):
        st = read_state(device)
        if st["screen"] != "battle":
            time.sleep(0.4)
            continue
        if st["status"] == "Computer's shot":
            saw_computer = True
        elif st["game_over"]:
            return {"result": "game over", "state": st}
        elif "hit" in st["hint"].lower() or "sunk" in st["hint"].lower():
            return {"result": "sunk" if "sunk" in st["hint"].lower() else "hit", "state": st}
        elif saw_computer or "Tap a cell" in st["hint"]:
            if saw_computer:
                return {"result": "miss", "state": st}
        time.sleep(0.4)
    st = read_state(device)
    return {"result": "miss" if saw_computer else "unknown", "state": st}


def _fire_one(device, cell: str) -> dict:
    name, x, y = _cell(cell)
    st = _wait(device, "battle")
    if st["game_over"]:
        raise RuntimeError(f"the game is over: {st['status']}")
    if st["status"] != "Your turn":
        raise RuntimeError(f"not your turn (status: {st['status']})")
    device.tap(x, y, delay=0.6)
    aimed = read_state(device)
    if aimed.get("screen") != "battle" or "again" not in aimed["hint"]:
        raise RuntimeError(f"cell {name} was not aimed (already fired at?): {aimed.get('hint')!r}")
    device.tap(*_FIRE, delay=0.4)
    res = _settle(device)
    return {"cell": name, **res}


# ── python_action targets ───────────────────────────────────────────────────

def restart_app(device, params, context):
    device.adb("shell", "am", "force-stop", _PKG)
    time.sleep(0.5)
    return {}


def open_menu(device, params, context):
    return {"state": _wait(device, "menu")}


def new_game(device, params, context):
    device.adb("shell", "am", "force-stop", _PKG)
    time.sleep(0.5)
    device.adb("shell", "monkey", "-p", _PKG, "-c", "android.intent.category.LAUNCHER", "1")
    time.sleep(2.5)
    menu = _wait(device, "menu")
    device.tap(*_centre(_text(_nodes(device), "Play the computer")), delay=1.5)
    _wait(device, "placing")
    device.tap(*_centre(_text(_nodes(device), "Random")), delay=1.0)
    device.tap(*_centre(_text(_nodes(device), "Ready")), delay=2.0)
    st = _wait(device, "battle")
    return {"menu": menu, "state": st}


def ensure_game(device, params, context):
    """Pre-step: keep a running game, otherwise start one."""
    st = read_state(device)
    if st.get("screen") == "battle" and not st["game_over"]:
        return {}
    new_game(device, params, context)
    return {}


def fire(device, params, context):
    return _fire_one(device, params.get("cell", ""))


def fire_many(device, params, context):
    cells = [c.strip() for c in str(params.get("cells", "")).replace(";", ",").split(",") if c.strip()]
    if not 1 <= len(cells) <= 20:
        raise RuntimeError("cells must list 1 to 20 cells separated by commas, for example A1,B2,C3")
    shots = []
    for c in cells:
        r = _fire_one(device, c)
        shots.append({"cell": r["cell"], "result": r["result"]})
        if r["result"] == "game over":
            break
    return {"shots": shots, "hits": sum(s["result"] in ("hit", "sunk") for s in shots), "state": read_state(device)}


def get_state(device, params, context):
    return {"state": _wait(device, "battle")}


# ── validators ──────────────────────────────────────────────────────────────

def menu_open(device, context) -> bool:
    return read_state(device).get("screen") == "menu"


def game_started(device, context) -> bool:
    s = read_state(device)
    return s.get("screen") == "battle" and s["status"] == "Your turn" and s["enemy_ships_left"] == [1, 2, 3, 4]


def fired(device, context) -> bool:
    r = context.result
    s = read_state(device)
    return s.get("screen") == "battle" and r["result"] in ("hit", "sunk", "miss", "game over")


def fired_many(device, context) -> bool:
    r = context.result
    return read_state(device).get("screen") == "battle" and len(r["shots"]) >= 1 and all(s["result"] != "unknown" for s in r["shots"])


def state_read(device, context) -> bool:
    s = read_state(device)
    return s.get("screen") == "battle" and s["status"] == context.result["state"]["status"]
