"""oblique-strategies helpers (Oblique Strategies, garden.lina.oblique_strategies): draw Eno and Schmidt cards.

The deck is a stack of cards. Every card is a View with the card text in its content-desc, all at the same
bounds; the LAST one in the dump is the card on top, the one before it is the next card (not shown yet).
"""
from __future__ import annotations

import html
import re
import time

_PKG = "garden.lina.oblique_strategies"
_CARD = (38, 331, 683, 1269)


def _cards(device) -> list[str]:
    out = []
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = tuple(int(v) for v in re.findall(r"-?\d+", a.get("bounds", "")))
        text = html.unescape(a.get("content-desc", "")).strip()
        if nums == _CARD and text:
            out.append(text)
    return out


def _kind(text: str) -> str:
    if text.startswith("Using This App"):
        return "help"
    if text.startswith("OBLIQUE STRATEGIES"):
        return "title"
    return "strategy"


def read_state(device) -> dict:
    cards = _cards(device)
    if not cards:
        return {"screen": "other"}
    top = cards[-1]
    return {"screen": "deck", "card": top.replace("\n", " "), "kind": _kind(top)}


def _wait(device, tries=10):
    for _ in range(tries):
        st = read_state(device)
        if st["screen"] == "deck":
            return st
        time.sleep(0.8)
    raise RuntimeError("the card deck is not on screen")


def _draw_once(device, before: str) -> dict:
    """Swipe the top card away and wait until a different card is on top."""
    device.adb("shell", "input", "swipe", "620", "800", "90", "800", "300")
    time.sleep(1.2)
    for _ in range(8):
        st = read_state(device)
        if st["screen"] == "deck" and st["card"] != before:
            time.sleep(0.6)
            st2 = read_state(device)
            if st2.get("card") == st["card"]:
                return st
        time.sleep(0.7)
    raise RuntimeError("the card did not change after the swipe")


# ── python_action targets ───────────────────────────────────────────────────

def restart_app(device, params, context):
    device.adb("shell", "am", "force-stop", _PKG)
    time.sleep(0.5)
    return {}


def open_deck(device, params, context):
    return {"state": _wait(device)}


def draw_card(device, params, context):
    st = _wait(device)
    new = _draw_once(device, st["card"])
    return {"previous": st["card"], "card": new["card"], "kind": new["kind"]}


def draw_cards(device, params, context):
    n = int(str(params.get("count", 3)))
    if not 1 <= n <= 10:
        raise RuntimeError("count must be 1 to 10")
    st = _wait(device)
    cur, cards = st["card"], []
    for _ in range(n):
        new = _draw_once(device, cur)
        cards.append({"card": new["card"], "kind": new["kind"]})
        cur = new["card"]
    return {"count": n, "cards": cards, "strategies": [c["card"] for c in cards if c["kind"] == "strategy"],
            "state": read_state(device)}


def get_card(device, params, context):
    return {"state": _wait(device)}


# ── validators ──────────────────────────────────────────────────────────────

def deck_open(device, context) -> bool:
    return read_state(device).get("screen") == "deck"


def drawn(device, context) -> bool:
    r = context.result
    s = read_state(device)
    return s.get("screen") == "deck" and s["card"] == r["card"] and r["card"] != r["previous"]


def drawn_many(device, context) -> bool:
    r = context.result
    s = read_state(device)
    return (s.get("screen") == "deck" and len(r["cards"]) == r["count"] and s["card"] == r["cards"][-1]["card"]
            and all(c["card"] for c in r["cards"]))


def card_read(device, context) -> bool:
    s = read_state(device)
    return s.get("screen") == "deck" and s["card"] == context.result["state"]["card"]
