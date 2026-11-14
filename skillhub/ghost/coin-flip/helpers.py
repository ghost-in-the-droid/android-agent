"""coin-flip helpers (Flip a coin, org.ecos.logic.flip_a_coin): flip a coin and read head or tail.

The coin label (head or tail) is a text node, so the skill flips one or many times and counts the outcomes.
"""
from __future__ import annotations

import html
import re
import time

_PKG = "org.ecos.logic.flip_a_coin"


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
    if not _by(nodes, "flipAction"):
        return {"screen": "other"}
    label = _by(nodes, "coinLabel")
    return {"screen": "coin", "result": label["text"] if label else ""}


def _wait(device, tries=10):
    for _ in range(tries):
        st = read_state(device)
        if st.get("screen") == "coin":
            return st
        time.sleep(0.8)
    raise RuntimeError("the coin screen is not on screen")


def _flip_once(device):
    """Tap Flip and wait for the label to settle on head or tail."""
    device.tap(*_centre(_by(_nodes(device), "flipAction")), delay=1.8)
    last = None
    for _ in range(8):
        st = read_state(device)
        if st.get("result") in ("head", "tail") and st["result"] == last:
            return st["result"]
        last = st.get("result")
        time.sleep(0.7)
    raise RuntimeError("the coin result did not settle")


# ── python_action targets ───────────────────────────────────────────────────

def restart_app(device, params, context):
    device.adb("shell", "am", "force-stop", _PKG)
    time.sleep(0.5)
    return {}


def open_coin(device, params, context):
    return {"state": _wait(device)}


def flip(device, params, context):
    _wait(device)
    res = _flip_once(device)
    return {"flip": res, "state": read_state(device)}


def flip_many(device, params, context):
    n = int(str(params.get("count", 5)))
    if not 1 <= n <= 20:
        raise RuntimeError("count must be 1 to 20")
    _wait(device)
    flips = [_flip_once(device) for _ in range(n)]
    return {"count": n, "flips": flips, "heads": flips.count("head"), "tails": flips.count("tail"), "state": read_state(device)}


def get_result(device, params, context):
    return {"state": _wait(device)}


# ── validators ──────────────────────────────────────────────────────────────

def coin_open(device, context) -> bool:
    return read_state(device).get("screen") == "coin"


def flipped(device, context) -> bool:
    s = read_state(device)
    return s.get("screen") == "coin" and s["result"] == context.result["flip"] and s["result"] in ("head", "tail")


def flipped_many(device, context) -> bool:
    r = context.result
    s = read_state(device)
    return (s.get("screen") == "coin" and len(r["flips"]) == r["count"] and r["heads"] + r["tails"] == r["count"]
            and s["result"] == r["flips"][-1])


def result_read(device, context) -> bool:
    s = read_state(device)
    return s.get("screen") == "coin" and s["result"] == context.result["state"]["result"]
