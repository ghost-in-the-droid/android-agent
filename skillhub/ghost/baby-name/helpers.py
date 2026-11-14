"""baby-name helpers (Baby Name, fr.hnit.babyname): filter a database of about 46000 first names offline.

Screens: a list screen (after a search is saved), a preferences form (gender radios, a regular expression pattern, origin
checkboxes, a live "(N Names)" counter) and a name view (name, gender and origin line, "(i/N)" position, PREVIOUS / NEXT).
"""
from __future__ import annotations

import html
import re
import time

from gitd.bots.common.adb import input_text_arg

_PKG = "fr.hnit.babyname"
_GENDERS = {"male": "gender_male_radio", "female": "gender_female_radio", "neutral": "gender_neutral_radio", "all": "gender_all_radio"}


def _nodes(device) -> list[dict]:
    out = []
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"id": a.get("resource-id", "").split("/")[-1], "text": html.unescape(a.get("text", "")),
                        "desc": html.unescape(a.get("content-desc", "")), "checked": a.get("checked") == "true", "bounds": tuple(nums)})
    return out


def _by(nodes, ident):
    return next((n for n in nodes if n["id"] == ident), None)


def _centre(n):
    b = n["bounds"]
    return (b[0] + b[2]) // 2, (b[1] + b[3]) // 2


def read_state(device, nodes=None) -> dict:
    nodes = nodes if nodes is not None else _nodes(device)
    if _by(nodes, "name_text"):
        pos = _by(nodes, "progress_counter")
        m = re.search(r"\((\d+)/(\d+)\)", pos["text"] if pos else "")
        extra = _by(nodes, "extra_text")
        return {"screen": "name", "name": _by(nodes, "name_text")["text"], "details": extra["text"] if extra else "",
                "position": int(m.group(1)) if m else None, "total": int(m.group(2)) if m else None}
    if _by(nodes, "counter_text"):
        m = re.search(r"\((\d+) Names\)", _by(nodes, "counter_text")["text"])
        gender = next((k for k, i in _GENDERS.items() if (_by(nodes, i) or {}).get("checked")), "")
        pat = _by(nodes, "pattern_text")
        return {"screen": "prefs", "count": int(m.group(1)) if m else None, "gender": gender, "pattern": pat["text"] if pat else ""}
    if _by(nodes, "list_flip_find"):
        return {"screen": "list"}
    if _by(nodes, "backgroundTextView"):
        return {"screen": "empty"}
    return {"screen": "other"}


def _wait(device, want, tries=12):
    for _ in range(tries):
        st = read_state(device)
        if st["screen"] in (want if isinstance(want, tuple) else (want,)):
            return st
        time.sleep(0.7)
    raise RuntimeError(f"the {want} screen is not on screen")


def _to_list(device):
    if read_state(device)["screen"] == "name":
        up = next((n for n in _nodes(device) if n["desc"] == "Navigate up"), None)
        device.tap(*_centre(up), delay=1.3)
        _wait(device, ("list", "empty"))


def _open_prefs(device):
    st = read_state(device)["screen"]
    if st == "prefs":
        return
    if st == "name":
        _to_list(device)
    elif st not in ("list", "empty"):
        raise RuntimeError("the app is not on one of its known screens")
    menu = next((n for n in _nodes(device) if n["desc"] == "More options"), None)
    device.tap(*_centre(menu), delay=1.2)
    item = next((n for n in _nodes(device) if n["text"] == "New Baby"), None)
    if not item:
        raise RuntimeError("the New Baby menu entry is not showing")
    device.tap(*_centre(item), delay=1.5)
    _wait(device, "prefs")


def _clear_searches(device):
    """Delete the saved searches on the list screen so a new one is the only card."""
    for _ in range(12):
        dels = [n for n in _nodes(device) if n["id"] == "list_delete"]
        if not dels:
            return
        device.tap(*_centre(dels[0]), delay=1.0)
        yes = next((n for n in _nodes(device) if n["id"] == "button1"), None)
        if not yes:
            raise RuntimeError("the delete confirmation did not show")
        device.tap(*_centre(yes), delay=1.2)


def _settled_count(device):
    last = None
    for _ in range(8):
        time.sleep(0.6)
        st = read_state(device)
        if st["screen"] == "prefs" and st["count"] == last:
            return st
        last = st.get("count")
    return read_state(device)


def _name_view(device) -> dict:
    st = read_state(device)
    if st["screen"] == "name":
        return st
    _wait(device, "list")
    flips = sorted((n for n in _nodes(device) if n["id"] == "list_flip_find"), key=lambda n: n["bounds"][1])
    device.tap(*_centre(flips[-1]), delay=1.6)
    return _wait(device, "name")


# ── python_action targets ───────────────────────────────────────────────────

def restart_app(device, params, context):
    device.adb("shell", "am", "force-stop", _PKG)
    time.sleep(0.5)
    return {}


def open_filter(device, params, context):
    _open_prefs(device)
    return {"state": _settled_count(device)}


def set_filter(device, params, context):
    gender = str(params.get("gender", "all")).strip().lower() or "all"
    if gender not in _GENDERS:
        raise RuntimeError("gender must be male, female, neutral or all")
    pattern = str(params.get("pattern", ".*")).strip() or ".*"
    if read_state(device)["screen"] in ("name", "list"):
        _to_list(device)
        _clear_searches(device)
    _open_prefs(device)
    device.tap(*_centre(_by(_nodes(device), _GENDERS[gender])), delay=0.6)
    device.tap(*_centre(_by(_nodes(device), "pattern_text")), delay=0.5)
    device.adb("shell", "input", "keycombination", "KEYCODE_CTRL_LEFT", "KEYCODE_A")
    device.adb("shell", "input", "keyevent", "KEYCODE_DEL")
    time.sleep(0.4)
    device.adb("shell", "input", "text", input_text_arg(pattern))
    st = _settled_count(device)
    if not st["count"]:
        raise RuntimeError(f"no name matches gender={gender} pattern={pattern}")
    save = next((n for n in _nodes(device) if n["text"] == "SAVE"), None)
    device.tap(*_centre(save), delay=1.8)
    first = _name_view(device)
    return {"gender": gender, "pattern": pattern, "count": st["count"], "first": first["name"], "details": first["details"]}


def seed_names(device, params, context):
    """Pre-step: make sure a name view is on screen."""
    if read_state(device)["screen"] != "name":
        set_filter(device, {"gender": "female", "pattern": "Ma.*a"}, context)
    return {}


def seed_second(device, params, context):
    """Pre-step: stand on the second name so PREVIOUS has somewhere to go."""
    seed_names(device, params, context)
    if read_state(device)["position"] == 1:
        _step(device, "next_button")
    return {}


def get_name(device, params, context):
    return {"state": _name_view(device)}


def _step(device, button) -> dict:
    before = _wait(device, "name")
    device.tap(*_centre(_by(_nodes(device), button)), delay=1.0)
    after = _wait(device, "name")
    after["moved"] = after["position"] != before["position"]
    return after


def next_name(device, params, context):
    return {"state": _step(device, "next_button")}


def previous_name(device, params, context):
    return {"state": _step(device, "previous_button")}


def list_names(device, params, context):
    n = int(params.get("count", 5))
    if not 1 <= n <= 20:
        raise RuntimeError("count must be 1 to 20")
    st = _name_view(device)
    names = [{"name": st["name"], "details": st["details"], "position": st["position"]}]
    while len(names) < n:
        st = _step(device, "next_button")
        if not st["moved"]:
            break
        names.append({"name": st["name"], "details": st["details"], "position": st["position"]})
    return {"total": st["total"], "count": len(names), "names": names}


# ── validators ──────────────────────────────────────────────────────────────

def filter_open(device, context) -> bool:
    return read_state(device)["screen"] == "prefs"


def filter_set(device, context) -> bool:
    r = context.result
    s = read_state(device)
    return s["screen"] == "name" and s["total"] == r["count"] and s["name"] == r["first"]


def name_read(device, context) -> bool:
    s = read_state(device)
    return s["screen"] == "name" and s["name"] == context.result["state"]["name"]


def name_moved(device, context) -> bool:
    s = read_state(device)
    return s["screen"] == "name" and s["position"] == context.result["state"]["position"]


def names_listed(device, context) -> bool:
    r = context.result
    s = read_state(device)
    return s["screen"] == "name" and r["count"] == len(r["names"]) and s["position"] == r["names"][-1]["position"]
