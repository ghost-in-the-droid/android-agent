"""flip-a-coin helpers (Flip a coin, org.ecos.logic.flip_a_coin): one screen with a big coin and a Flip button.

The big coin is an ImageView (resource id coin) whose content-desc is "head" or "tail" once the flip animation settles.
"""
from __future__ import annotations

import re
import time

_PKG = "org.ecos.logic.flip_a_coin"
_MAX_FLIPS = 20


def _nodes(device) -> list[dict]:
    out = []
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1]:
            out.append({"id": a.get("resource-id", "").split("/")[-1], "desc": a.get("content-desc", "").strip(),
                        "text": a.get("text", "").strip(), "bounds": tuple(nums)})
    return out


def _centre(n):
    b = n["bounds"]
    return (b[0] + b[2]) // 2, (b[1] + b[3]) // 2


def read_state(device, nodes=None) -> dict:
    nodes = nodes if nodes is not None else _nodes(device)
    coin = next((n for n in nodes if n["id"] == "coin"), None)
    btn = next((n for n in nodes if n["id"] == "flipAction"), None)
    if not coin or not btn:
        return {"screen": "other"}
    return {"screen": "coin", "face": coin["desc"] if coin["desc"] in ("head", "tail") else None, "button": btn}


def _wait(device, tries=12):
    for _ in range(tries):
        st = read_state(device)
        if st["screen"] == "coin" and st["face"]:
            return st
        time.sleep(0.7)
    raise RuntimeError("the coin screen is not on screen")


def _flip(device) -> str:
    st = _wait(device)
    device.tap(*_centre(st["button"]), delay=3.5)
    prev = None
    for _ in range(6):
        cur = read_state(device)
        if cur["screen"] == "coin" and cur["face"] and cur["face"] == prev:
            return cur["face"]
        prev = cur.get("face")
        time.sleep(0.8)
    raise RuntimeError("the coin did not settle")


# ── python_action targets ───────────────────────────────────────────────────

def restart_app(device, params, context):
    device.adb("shell", "am", "force-stop", _PKG)
    time.sleep(0.5)
    device.adb("shell", "monkey", "-p", _PKG, "-c", "android.intent.category.LAUNCHER", "1")  # later pre-steps need the app up
    time.sleep(2.5)
    return {}


def open_coin(device, params, context):
    st = _wait(device)
    return {"face": st["face"]}


def flip(device, params, context):
    return {"face": _flip(device)}


def flip_many(device, params, context):
    n = int(params.get("count") or 5)
    if not 1 <= n <= _MAX_FLIPS:
        raise RuntimeError(f"count must be 1 to {_MAX_FLIPS}")
    faces = [_flip(device) for _ in range(n)]
    return {"flips": faces, "heads": faces.count("head"), "tails": faces.count("tail"), "last": faces[-1]}


def get_coin(device, params, context):
    st = _wait(device)
    return {"face": st["face"]}


# ── validators ──────────────────────────────────────────────────────────────

def coin_open(device, context) -> bool:
    return read_state(device)["screen"] == "coin"


def flipped(device, context) -> bool:
    s = read_state(device)
    return s["screen"] == "coin" and s["face"] == context.result["face"] and context.result["face"] in ("head", "tail")


def flipped_many(device, context) -> bool:
    s = read_state(device)
    r = context.result
    return s["screen"] == "coin" and s["face"] == r["last"] and r["heads"] + r["tails"] == len(r["flips"])
