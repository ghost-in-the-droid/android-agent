"""kfz-a helpers (KFZ-A, de.herk.kfza): look up the district behind an Austrian licence plate code, offline.

One screen: an EditText for the code and three result blocks (District / Authority, Federal state, Type) that
update as you type. Each block is a label TextView followed by a value TextView.
"""
from __future__ import annotations

import html
import re
import time

from gitd.bots.common.adb import input_text_arg

_PKG = "de.herk.kfza"
_LABELS = {"District / Authority": "district", "Federal state": "state", "Type": "type"}


def _nodes(device) -> list[dict]:
    out = []
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"text": html.unescape(a.get("text", "")), "cls": a.get("class", "").split(".")[-1], "bounds": tuple(nums)})
    return out


def _centre(n):
    b = n["bounds"]
    return (b[0] + b[2]) // 2, (b[1] + b[3]) // 2


def read_state(device, nodes=None) -> dict:
    nodes = nodes if nodes is not None else _nodes(device)
    edit = next((n for n in nodes if n["cls"] == "EditText"), None)
    if not edit or not any(n["text"] == "District / Authority" for n in nodes):
        return {"screen": "other"}
    texts = [n for n in sorted(nodes, key=lambda n: n["bounds"][1]) if n["text"] and n["cls"] == "TextView" and 400 < n["bounds"][1] < 1300]
    out = {"screen": "lookup", "code": edit["text"]}
    for i, n in enumerate(texts):
        key = _LABELS.get(n["text"])
        if key and i + 1 < len(texts):
            out[key] = [ln.strip() for ln in texts[i + 1]["text"].split("\n") if ln.strip()]
    status = next((n["text"] for n in nodes if n["text"].startswith("Data status")), "")
    out["data_status"] = status.replace("Data status", "").strip()
    out["match"] = bool(out.get("district")) and out["district"] != ["No match"]
    return out


def _wait(device, tries=10):
    for _ in range(tries):
        st = read_state(device)
        if st["screen"] == "lookup":
            return st
        time.sleep(0.8)
    raise RuntimeError("the lookup screen is not on screen")


def _lookup_one(device, code: str) -> dict:
    code = str(code).strip()
    if not re.fullmatch(r"[A-Za-zÄÖÜäöü]{1,3}", code):
        raise RuntimeError("code must be 1 to 3 letters, for example W or GU")
    code = code.upper()
    _wait(device)
    edit = next(n for n in _nodes(device) if n["cls"] == "EditText")
    device.tap(*_centre(edit), delay=0.5)
    device.adb("shell", "input", "keycombination", "KEYCODE_CTRL_LEFT", "KEYCODE_A")
    device.adb("shell", "input", "keyevent", "KEYCODE_DEL")
    time.sleep(0.5)
    device.adb("shell", "input", "text", input_text_arg(code))
    last = None
    for _ in range(8):
        time.sleep(0.7)
        st = read_state(device)
        if st.get("screen") == "lookup" and st["code"].upper() == code:
            snap = (tuple(st.get("district", [])), tuple(st.get("state", [])))
            if snap == last:
                return st
            last = snap
    raise RuntimeError("the result did not settle")


# ── python_action targets ───────────────────────────────────────────────────

def restart_app(device, params, context):
    device.adb("shell", "am", "force-stop", _PKG)
    time.sleep(0.5)
    return {}


def open_lookup(device, params, context):
    return {"state": _wait(device)}


def lookup(device, params, context):
    st = _lookup_one(device, params.get("code", ""))
    return {"code": st["code"].upper(), "match": st["match"], "district": st.get("district", []),
            "state": st.get("state", []), "type": st.get("type", []), "data_status": st["data_status"]}


def lookup_many(device, params, context):
    codes = [c.strip() for c in str(params.get("codes", "")).replace(";", ",").split(",") if c.strip()]
    if not 1 <= len(codes) <= 15:
        raise RuntimeError("codes must list 1 to 15 plate codes separated by commas, for example W,G,S")
    results = []
    for c in codes:
        st = _lookup_one(device, c)
        results.append({"code": st["code"].upper(), "match": st["match"], "district": st.get("district", []), "state": st.get("state", [])})
    return {"count": len(results), "results": results}


def seed_code(device, params, context):
    """Pre-step: make sure a code is typed so get_result has something to read."""
    if not read_state(device).get("code"):
        _lookup_one(device, "W")
    return {}


def get_result(device, params, context):
    return {"state": _wait(device)}


# ── validators ──────────────────────────────────────────────────────────────

def lookup_open(device, context) -> bool:
    return read_state(device).get("screen") == "lookup"


def looked_up(device, context) -> bool:
    r = context.result
    s = read_state(device)
    return s.get("screen") == "lookup" and s["code"].upper() == r["code"] and s.get("district") == r["district"]


def looked_up_many(device, context) -> bool:
    r = context.result
    s = read_state(device)
    return s.get("screen") == "lookup" and r["count"] == len(r["results"]) and s["code"].upper() == r["results"][-1]["code"]


def result_read(device, context) -> bool:
    s = read_state(device)
    return s.get("screen") == "lookup" and s["code"] == context.result["state"]["code"]
