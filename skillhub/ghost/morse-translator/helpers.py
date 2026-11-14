"""morse-translator helpers (Morse, rocks.poopjournal.morse): translate text to Morse code and back, live.

The input field and the translated output are plain nodes and the TEXT/MORSE labels show the direction, so the skill
sets the direction, types the input and reads the output. The camera/flash permission dialog is denied.
"""
from __future__ import annotations

import html
import re
import time

from gitd.bots.common.adb import input_text_arg

_PKG = "rocks.poopjournal.morse"


def _nodes(device) -> list[dict]:
    out = []
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"text": html.unescape(a.get("text", "") or a.get("content-desc", "")),
                        "id": a.get("resource-id", "").split("/")[-1], "bounds": tuple(nums)})
    return out


def _centre(n):
    b = n["bounds"]
    return (b[0] + b[2]) // 2, (b[1] + b[3]) // 2


def _by(nodes, ident):
    return next((n for n in nodes if n["id"] == ident), None)


def read_state(device) -> dict:
    nodes = _nodes(device)
    one, inp = _by(nodes, "buttonOne"), _by(nodes, "input")
    if not one or not inp:
        return {"screen": "other"}
    out = _by(nodes, "output")
    direction = "text_to_morse" if one["text"].upper() == "TEXT" else "morse_to_text"
    return {"screen": "translator", "direction": direction, "input": inp["text"], "output": out["text"] if out else ""}


def _wait(device, tries=12):
    for _ in range(tries):
        nodes = _nodes(device)
        # the camera permission dialog of this demo app (and only of it): deny it
        msg = _by(nodes, "permission_message")
        deny = next((n for n in nodes if n["id"].startswith("permission_deny")), None)
        if msg and deny and "Morse" in msg["text"]:
            device.tap(*_centre(deny), delay=1.2)
            continue
        st = read_state(device)
        if st.get("screen") == "translator":
            return st
        time.sleep(0.8)
    raise RuntimeError("the translator is not on screen")


def _ascii(text) -> str:
    text = str(text)
    if not text.strip() or not text.isascii():
        raise RuntimeError("text must be non-empty plain ASCII (adb text input cannot type other characters)")
    return text


def _set_direction(device, direction):
    st = _wait(device)
    for _ in range(3):
        if st["direction"] == direction:
            return
        sw = _by(_nodes(device), "switchImageContainer")
        device.tap(*_centre(sw), delay=1.0)
        for _ in range(5):  # the labels swap with a short animation
            st = read_state(device)
            if st.get("screen") == "translator" and st["direction"] == direction:
                return
            time.sleep(0.6)
    raise RuntimeError("could not switch the direction")


# ── python_action targets ───────────────────────────────────────────────────

def restart_app(device, params, context):
    device.adb("shell", "am", "force-stop", _PKG)
    time.sleep(0.5)
    return {}


def open_translator(device, params, context):
    return {"state": _wait(device)}


def translate(device, params, context):
    direction = str(params.get("direction", "text_to_morse")).strip().lower()
    if direction not in ("text_to_morse", "morse_to_text"):
        raise RuntimeError("direction must be text_to_morse or morse_to_text")
    text = _ascii(params["text"])
    if direction == "morse_to_text" and not re.fullmatch(r"[.\-/ ]+", text):
        raise RuntimeError("morse input may only contain . - / and spaces")
    _set_direction(device, direction)
    field = _by(_nodes(device), "input")
    device.tap(*_centre(field), delay=0.6)
    device.adb("shell", "input", "keyevent", "KEYCODE_MOVE_END", *(["KEYCODE_DEL"] * 80))
    device.adb("shell", "input", "text", input_text_arg(text))
    time.sleep(1.2)
    return {"direction": direction, "text": text, "state": read_state(device)}


def get_translation(device, params, context):
    return {"state": _wait(device)}


def clear_input(device, params, context):
    _wait(device)
    field = _by(_nodes(device), "input")
    device.tap(*_centre(field), delay=0.6)
    device.adb("shell", "input", "keyevent", "KEYCODE_MOVE_END", *(["KEYCODE_DEL"] * 80))
    time.sleep(0.8)
    return {"state": read_state(device)}


# ── validators ──────────────────────────────────────────────────────────────

def translator_open(device, context) -> bool:
    return read_state(device).get("screen") == "translator"


def translated(device, context) -> bool:
    r = context.result
    s = read_state(device)
    return s.get("screen") == "translator" and s["direction"] == r["direction"] and s["input"] == r["text"] and bool(s["output"])


def translation_read(device, context) -> bool:
    s = read_state(device)
    r = context.result["state"]
    return s.get("screen") == "translator" and s["output"] == r["output"] and s["input"] == r["input"]


def cleared(device, context) -> bool:
    s = read_state(device)
    return s.get("screen") == "translator" and s["input"] == ""
