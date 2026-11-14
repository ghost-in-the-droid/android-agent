"""qonvert helpers (Qonvert, org.tessoft.qonvert): convert numbers between bases and number representations.

Pick the input base and the output base (BIN, OCT, DEC, DOZ, HEX), type a number and read every representation the
app computes (the number in the output base, fractions, continued fractions, Roman numerals and so on).
"""
from __future__ import annotations

import html
import re
import time

from gitd.bots.common.adb import input_text_arg

_PKG = "org.tessoft.qonvert"
_BASES = ("2", "8", "10", "12", "16")
_NAMES = {"bin": "2", "oct": "8", "dec": "10", "doz": "12", "hex": "16"}


def _nodes(device) -> list[dict]:
    out = []
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"text": html.unescape(a.get("text", "") or a.get("content-desc", "")),
                        "id": a.get("resource-id", "").split("/")[-1], "checked": a.get("checked") == "true", "bounds": tuple(nums)})
    return out


def _centre(n):
    b = n["bounds"]
    return (b[0] + b[2]) // 2, (b[1] + b[3]) // 2


def _by(nodes, ident):
    return next((n for n in nodes if n["id"] == ident), None)


def _base(value, what) -> str:
    v = str(value).strip().lower()
    v = _NAMES.get(v, v)
    if v not in _BASES:
        raise RuntimeError(f"{what} must be one of 2 (bin), 8 (oct), 10 (dec), 12 (doz), 16 (hex)")
    return v


def read_state(device) -> dict:
    nodes = _nodes(device)
    inp = _by(nodes, "editInput")
    if not inp:
        return {"screen": "other"}
    outs = [n["text"] for n in sorted((n for n in nodes if re.fullmatch(r"textOutput\d+", n["id"])), key=lambda n: n["bounds"][1]) if n["text"]]
    in_b = (_by(nodes, "inBaseText") or {"text": ""})["text"]
    out_b = (_by(nodes, "outBaseText") or {"text": ""})["text"]
    return {"screen": "converter", "input": inp["text"], "in_base": in_b, "out_base": out_b, "result": outs[0] if outs else "", "outputs": outs}


def _wait(device, tries=10):
    for _ in range(tries):
        st = read_state(device)
        if st.get("screen") == "converter":
            return st
        time.sleep(0.8)
    raise RuntimeError("the converter is not on screen")


def _pick_base(device, side, base):
    n = _by(_nodes(device), f"{side}ToggleButton{base}")
    if not n:
        raise RuntimeError(f"{side} base button {base} not on screen")
    if not n["checked"]:
        device.tap(*_centre(n), delay=0.6)


def _clear(device):
    n = _by(_nodes(device), "clearButton")
    if n:
        device.tap(*_centre(n), delay=0.5)


# ── python_action targets ───────────────────────────────────────────────────

def restart_app(device, params, context):
    device.adb("shell", "am", "force-stop", _PKG)
    time.sleep(0.5)
    return {}


def open_converter(device, params, context):
    return {"state": _wait(device)}


def convert(device, params, context):
    value = str(params["value"]).strip()
    if not value or not re.fullmatch(r"[0-9A-Za-z._/+-]+", value):
        raise RuntimeError("value must use digits/letters of the input base, plus . _ / + -")
    in_b = _base(params.get("from_base", "10"), "from_base")
    out_b = _base(params.get("to_base", "16"), "to_base")
    _wait(device)
    _pick_base(device, "in", in_b)
    _pick_base(device, "out", out_b)
    _clear(device)
    field = _by(_nodes(device), "editInput")
    device.tap(*_centre(field), delay=0.5)
    device.adb("shell", "input", "text", input_text_arg(value))
    time.sleep(1.2)
    return {"value": value, "from_base": in_b, "to_base": out_b, "state": read_state(device)}


def get_result(device, params, context):
    return {"state": _wait(device)}


def clear_input(device, params, context):
    _wait(device)
    _clear(device)
    time.sleep(0.5)
    return {"state": read_state(device)}


# ── validators ──────────────────────────────────────────────────────────────

def converter_open(device, context) -> bool:
    return read_state(device).get("screen") == "converter"


def converted(device, context) -> bool:
    r = context.result
    s = read_state(device)
    return (s.get("screen") == "converter" and s["input"].lower() == r["value"].lower()
            and f"base {r['from_base']}" in s["in_base"] and f"base {r['to_base']}" in s["out_base"] and bool(s["result"]))


def result_read(device, context) -> bool:
    s = read_state(device)
    return s.get("screen") == "converter" and s["result"] == context.result["state"]["result"]


def cleared(device, context) -> bool:
    s = read_state(device)
    return s.get("screen") == "converter" and s["input"].startswith("Type a number")  # the empty field shows its hint
