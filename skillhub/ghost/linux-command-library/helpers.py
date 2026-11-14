"""linux-command-library helpers (Linux Command Library, com.inspiredandroid.linuxcommandbibliotheca).

An offline reference of thousands of Linux commands: search by name, open a command page and read its sections
(TLDR examples, SYNOPSIS, DESCRIPTION, PARAMETERS, ...). Sections are accordions: tapping the header shows the text.
"""
from __future__ import annotations

import html
import re
import time

from gitd.bots.common.adb import input_text_arg

_PKG = "com.inspiredandroid.linuxcommandbibliotheca"


def _nodes(device) -> list[dict]:
    out = []
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"text": html.unescape(a.get("text", "") or a.get("content-desc", "")),
                        "cls": a.get("class", "").split(".")[-1], "bounds": tuple(nums)})
    return out


def _centre(n):
    b = n["bounds"]
    return (b[0] + b[2]) // 2, (b[1] + b[3]) // 2


def _find(nodes, text):
    return next((n for n in nodes if n["text"] == text), None)


def _headers(nodes):
    """Section headers of a command page: upper case TextViews at the left margin."""
    return sorted((n for n in nodes if n["cls"] == "TextView" and n["bounds"][0] == 45 and n["text"].isupper() and n["bounds"][1] > 140),
                  key=lambda n: n["bounds"][1])


def read_state(device) -> dict:
    nodes = _nodes(device)
    if _find(nodes, "Back") and _find(nodes, "Add bookmark"):
        title = next((n["text"] for n in nodes if n["cls"] == "TextView" and 100 < n["bounds"][0] < 120 and n["bounds"][1] < 130), "")
        return {"screen": "command", "command": title, "sections": [h["text"] for h in _headers(nodes)]}
    field = next((n for n in nodes if n["cls"] == "EditText"), None)
    if field:
        count = next((n["text"] for n in nodes if re.fullmatch(r"Commands \(\d+\)", n["text"])), "")
        results = [n["text"] for n in sorted(nodes, key=lambda n: n["bounds"][1])
                   if n["cls"] == "TextView" and n["bounds"][0] == 30 and n["bounds"][1] > 240 and not n["text"].startswith("Commands (")]
        if count or results:
            return {"screen": "search", "query": field["text"], "count": int(re.search(r"\d+", count).group()) if count else len(results), "results": results}
        return {"screen": "home", "query": field["text"]}
    return {"screen": "other"}


def _wait(device, want, tries=10):
    for _ in range(tries):
        st = read_state(device)
        if st.get("screen") in want:
            return st
        time.sleep(0.8)
    raise RuntimeError(f"expected the {'/'.join(want)} screen")


# ── python_action targets ───────────────────────────────────────────────────

def restart_app(device, params, context):
    device.adb("shell", "am", "force-stop", _PKG)
    time.sleep(0.5)
    return {}


def open_library(device, params, context):
    return {"state": _wait(device, ("home", "search"))}


def search_commands(device, params, context):
    query = str(params["query"]).strip()
    if not query or not query.isascii():
        raise RuntimeError("query must be a non-empty ASCII word")
    st = _wait(device, ("home", "search", "command"))
    if st["screen"] == "command":  # in-app Back to the search results
        device.tap(*_centre(_find(_nodes(device), "Back")), delay=1.2)
        st = _wait(device, ("home", "search"))
    field = next(n for n in _nodes(device) if n["cls"] == "EditText")
    device.tap(*_centre(field), delay=0.6)
    device.adb("shell", "input", "keyevent", "KEYCODE_MOVE_END", *(["KEYCODE_DEL"] * 40))
    device.adb("shell", "input", "text", input_text_arg(query))
    time.sleep(2.0)
    return {"query": query, "state": _wait(device, ("search",))}


def open_command(device, params, context):
    name = str(params["name"]).strip()
    st = _wait(device, ("home", "search", "command"))
    if st["screen"] == "command" and st["command"] == name:
        return {"name": name, "state": st}
    if st["screen"] != "search" or name not in st["results"]:
        search_commands(device, {"query": name}, context)
        st = _wait(device, ("search",))
    row = next((n for n in _nodes(device) if n["text"] == name and n["bounds"][0] == 30), None)
    if not row:
        raise RuntimeError(f"command {name!r} not found in the results: {st['results'][:10]}")
    device.tap(*_centre(row), delay=2.0)
    return {"name": name, "state": _wait(device, ("command",))}


def _to_top(device):
    for _ in range(3):
        device.swipe(360, 400, 360, 1300, 250)
        time.sleep(0.4)


def read_section(device, params, context):
    want = str(params.get("section", "TLDR")).strip().upper()
    _wait(device, ("command",))
    _to_top(device)
    st = read_state(device)
    seen_headers = list(st["sections"])
    for _ in range(8):  # an expanded section pushes the others below the fold: scroll until the header shows
        if want in st["sections"]:
            break
        device.swipe(360, 1200, 360, 500, 400)
        time.sleep(0.8)
        st = read_state(device)
        seen_headers += [h for h in st["sections"] if h not in seen_headers]
    if want not in st["sections"]:
        raise RuntimeError(f"section {want!r} not on this page: {seen_headers}")
    nodes = _nodes(device)
    hs = _headers(nodes)
    hdr = next(h for h in hs if h["text"] == want)
    nxt = [h for h in hs if h["bounds"][1] > hdr["bounds"][1]]
    below = [n for n in nodes if n["cls"] == "TextView" and n["bounds"][1] > hdr["bounds"][3] and n["bounds"][0] in (53, 76) and n["text"]]
    if not below or (nxt and below[0]["bounds"][1] > nxt[0]["bounds"][1]):  # collapsed: open it
        device.tap(*_centre(hdr), delay=1.2)
    lines = []
    for _ in range(6):
        nodes = _nodes(device)
        hs = _headers(nodes)
        hdr = next((h for h in hs if h["text"] == want), None)
        start = hdr["bounds"][3] if hdr else 140
        end = next((h["bounds"][1] for h in hs if hdr and h["bounds"][1] > hdr["bounds"][1]), None)
        ordered = [n["text"] for n in sorted((n for n in nodes if n["cls"] == "TextView" and start <= n["bounds"][1] < (end or 10**6)
                                              and n["bounds"][0] in (53, 76) and n["text"]), key=lambda n: n["bounds"][1])]
        new = [t for t in ordered if t not in lines]
        lines.extend(new)
        if end is not None or not new:  # the next header is visible, or scrolling revealed nothing new
            break
        device.swipe(360, 1200, 360, 500, 400)
        time.sleep(0.8)
    return {"section": want, "lines": lines, "command": st["command"], "state": read_state(device)}


def get_state(device, params, context):
    return {"state": _wait(device, ("home", "search", "command"))}


# ── validators ──────────────────────────────────────────────────────────────

def library_open(device, context) -> bool:
    return read_state(device).get("screen") in ("home", "search")


def searched(device, context) -> bool:
    s = read_state(device)
    return s.get("screen") == "search" and s["query"] == context.result["query"] and s["count"] > 0


def command_open(device, context) -> bool:
    s = read_state(device)
    return s.get("screen") == "command" and s["command"] == context.result["name"] and len(s["sections"]) > 0


def section_read(device, context) -> bool:
    r = context.result
    s = read_state(device)
    return s.get("screen") == "command" and s["command"] == r["command"] and len(r["lines"]) > 0


def state_read(device, context) -> bool:
    return read_state(device).get("screen") in ("home", "search", "command")
