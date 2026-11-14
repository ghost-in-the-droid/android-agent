"""prevo helpers (PReVo, uk.co.busydoingnothing.prevo): offline Esperanto dictionary (Plena Ilustrita Vortaro).

Three screens: a language picker (first launch), a search screen with a word list, and an entry screen. An entry shows the
Esperanto headword (for example kat/o) and one section_header per language with its translations underneath. The dictionary
is bundled, no network.
"""
from __future__ import annotations

import html
import re
import time

from gitd.bots.common.adb import input_text_arg

_PKG = "uk.co.busydoingnothing.prevo"
_MAX_PAGES = 14


def _nodes(device) -> list[dict]:
    out = []
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1]:
            out.append({"id": a.get("resource-id", "").split("/")[-1], "text": html.unescape(a.get("text", "")).strip(),
                        "desc": html.unescape(a.get("content-desc", "")).strip(), "cls": a.get("class", "").split(".")[-1],
                        "bounds": tuple(nums)})
    return out


def _centre(n):
    b = n["bounds"]
    return (b[0] + b[2]) // 2, (b[1] + b[3]) // 2


def _screen(nodes) -> str:
    if any(n["text"] == "Elekti lingvon" for n in nodes):
        return "languages"
    if any(n["id"] == "search_edit" for n in nodes):
        return "search"
    if any(n["id"] == "section_header" for n in nodes):
        return "entry"
    return "other"


def read_state(device, nodes=None) -> dict:
    nodes = nodes if nodes is not None else _nodes(device)
    scr = _screen(nodes)
    if scr == "search":
        q = next(n["text"] for n in nodes if n["id"] == "search_edit")
        words = [n["text"] for n in nodes if n["id"] == "text1" and n["bounds"][1] > 150]
        return {"screen": "search", "query": "" if q.startswith("Tajpi") else q, "results": words}
    if scr == "entry":
        head = next((n["text"] for n in nodes if n["bounds"][1] < 140 and n["text"] and n["id"] == "" and n["cls"] == "TextView"), "")
        return {"screen": "entry", "headword": head.lstrip("* ").strip()}
    return {"screen": scr}


def _wait(device, want, tries=14):
    for _ in range(tries):
        st = read_state(device)
        if st["screen"] == want:
            return st
        time.sleep(0.7)
    raise RuntimeError(f"the {want} screen is not on screen")


def _sections(device, want: str = "") -> dict:
    """Walk the entry page and collect LANGUAGE -> translation text."""
    found: dict[str, str] = {}
    last = None
    for _ in range(_MAX_PAGES):
        nodes = _nodes(device)
        cur = None
        for n in sorted((n for n in nodes if n["bounds"][1] >= 140 and n["bounds"][3] > n["bounds"][1]), key=lambda n: n["bounds"][1]):
            if n["id"] == "section_header":
                cur = n["text"]
                found.setdefault(cur, "")
            elif cur and n["text"] and n["bounds"][3] <= 1465 and n["bounds"][2] > n["bounds"][0]:
                if n["text"] not in found[cur]:
                    found[cur] = (found[cur] + " " + n["text"]).strip()
        sig = tuple(n["text"] for n in nodes if n["id"] == "section_header")
        heads = list(found)
        if want in heads and heads.index(want) < len(heads) - 1 and found[want]:
            break
        if sig == last:
            break
        last = sig
        device.swipe(360, 1300, 360, 500, 400)
        time.sleep(0.5)
    return found


def _type_query(device, term):
    nodes = _nodes(device)
    field = next(n for n in nodes if n["id"] == "search_edit")
    device.tap(*_centre(field), delay=0.5)
    device.adb("shell", "input", "keycombination", "KEYCODE_CTRL_LEFT", "KEYCODE_A")
    device.adb("shell", "input", "keyevent", "KEYCODE_DEL")
    device.adb("shell", "input", "text", input_text_arg(term))
    time.sleep(1.2)


# ── python_action targets ───────────────────────────────────────────────────

def restart_app(device, params, context):
    device.adb("shell", "am", "force-stop", _PKG)
    time.sleep(0.5)
    device.adb("shell", "monkey", "-p", _PKG, "-c", "android.intent.category.LAUNCHER", "1")  # later pre-steps need the app up
    time.sleep(2.5)
    return {}


def open_dictionary(device, params, context):
    lang = str(params.get("language") or "angla").strip().lower()
    st = {"screen": "other"}
    for _ in range(20):
        st = read_state(device)
        if st["screen"] in ("search", "languages"):
            break
        time.sleep(0.7)
    if st["screen"] not in ("search", "languages"):
        raise RuntimeError("the dictionary did not open")
    if st["screen"] == "languages":
        for _ in range(12):
            row = next((n for n in _nodes(device) if n["id"] == "text1" and n["text"].lower() == lang), None)
            if row:
                device.tap(*_centre(row), delay=1.5)
                break
            device.swipe(360, 1300, 360, 500, 400)
            time.sleep(0.5)
        else:
            raise RuntimeError(f"language {lang} not in the list (use names such as angla, germana, franca)")
        st = _wait(device, "search")
    return {"state": st}


def search(device, params, context):
    term = str(params.get("term") or "").strip()
    if not term:
        raise RuntimeError("term must be a word to look up")
    _wait(device, "search")
    _type_query(device, term)
    st = read_state(device)
    return {"term": term, "results": st["results"][:12]}


def open_entry(device, params, context):
    term = str(params.get("term") or "").strip()
    if not term:
        raise RuntimeError("term must be a word to look up")
    _wait(device, "search")
    _type_query(device, term)
    nodes = _nodes(device)
    rows = [n for n in nodes if n["id"] == "text1" and n["bounds"][1] > 230]
    hit = next((n for n in rows if n["text"].lower() == term.lower()), None) or (rows[0] if rows else None)
    if not hit:
        raise RuntimeError(f"nothing found for {term}")
    device.tap(*_centre(hit), delay=1.8)
    _wait(device, "entry")
    return _entry(device, params)


def _entry(device, params):
    st = _wait(device, "entry")
    want = str(params.get("language") or "angla").strip().upper()
    sections = _sections(device, want)
    return {"headword": st["headword"], "language": want.lower(), "translation": sections.get(want, ""), "languages_seen": len(sections)}


def get_entry(device, params, context):
    return _entry(device, params)


def back_to_search(device, params, context):
    _wait(device, "entry")
    for _ in range(3):
        nodes = _nodes(device)
        btn = next((n for n in nodes if n["id"] == "menu_search"), None)
        if btn:
            device.tap(*_centre(btn), delay=1.2)
            break
        device.swipe(360, 500, 360, 1300, 300)
        time.sleep(0.5)
    return {"state": _wait(device, "search")}


def seed_entry(device, params, context):
    st = read_state(device)
    if st["screen"] == "entry":
        return {}
    open_entry(device, {"term": "cat"}, context)
    return {}


# ── validators ──────────────────────────────────────────────────────────────

def dictionary_open(device, context) -> bool:
    return read_state(device)["screen"] == "search"


def searched(device, context) -> bool:
    s = read_state(device)
    return s["screen"] == "search" and bool(context.result["results"]) and s["results"][:3] == context.result["results"][:3]


def entry_opened(device, context) -> bool:
    s = read_state(device)
    r = context.result
    return s["screen"] == "entry" and bool(r["headword"]) and bool(r["translation"])


def entry_read(device, context) -> bool:
    return entry_opened(device, context)


def back_ok(device, context) -> bool:
    return read_state(device)["screen"] == "search"
