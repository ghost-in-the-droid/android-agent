"""survival-manual helpers (Survival Manual, org.ligi.survivalmanual): read an offline survival guide chapter by chapter.

A navigation drawer lists the chapters (Introduction, Psychology, Water, Fire ...). A chapter is a few big TextViews. The
toolbar hides while scrolling down and returns on a small swipe up (down-drag).
"""
from __future__ import annotations

import html
import re
import time

_PKG = "org.ligi.survivalmanual"
_MAX_TEXT = 1800


def _nodes(device) -> list[dict]:
    out = []
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"id": a.get("resource-id", "").split("/")[-1], "text": html.unescape(a.get("text", "")).strip(),
                        "desc": html.unescape(a.get("content-desc", "")), "bounds": tuple(nums)})
    return out


def _centre(n):
    b = n["bounds"]
    return (b[0] + b[2]) // 2, (b[1] + b[3]) // 2


def read_state(device, nodes=None) -> dict:
    nodes = nodes if nodes is not None else _nodes(device)
    items = [n for n in nodes if n["id"] == "design_menu_item_text"]
    if items:
        return {"screen": "drawer", "chapters": [n["text"] for n in items]}
    title = next((n["text"] for n in nodes if n["bounds"][0] == 135 and 100 <= n["bounds"][1] <= 110 and n["text"]), "")
    body = [n["text"] for n in sorted(nodes, key=lambda n: n["bounds"][1]) if n["text"] and not n["id"] and n["bounds"][1] >= 150 and len(n["text"]) > 3]
    if body or title:
        return {"screen": "page", "chapter": title, "text": "\n".join(body)[:_MAX_TEXT], "toolbar": any(n["desc"] in ("open", "close") for n in nodes)}
    return {"screen": "other"}


def _wait(device, want, tries=10):
    for _ in range(tries):
        st = read_state(device)
        if st["screen"] == want:
            return st
        time.sleep(0.7)
    raise RuntimeError(f"the {want} screen is not on screen")


def _open_drawer(device):
    st = read_state(device)
    if st["screen"] == "drawer":
        return st
    nav = next((n for n in _nodes(device) if n["desc"] == "open"), None)
    if not nav:
        device.swipe(360, 600, 360, 900, 300)  # a small drag down brings the toolbar back
        time.sleep(0.8)
        nav = next((n for n in _nodes(device) if n["desc"] == "open"), None)
    if not nav:
        raise RuntimeError("the menu button is not showing")
    device.tap(*_centre(nav), delay=1.2)
    return _wait(device, "drawer")


def _drawer_to_top(device):
    for _ in range(4):
        device.swipe(260, 500, 260, 1300, 250)
        time.sleep(0.4)


def _drawer_scan(device, want: str | None = None):
    """Walk the drawer from the top; returns (all chapters, tap node for want or None)."""
    _drawer_to_top(device)
    seen: list[str] = []
    for _ in range(8):
        nodes = _nodes(device)
        items = [n for n in nodes if n["id"] == "design_menu_item_text"]
        for n in items:
            if n["text"] not in seen:
                seen.append(n["text"])
            if want and n["text"].lower() == want.lower():
                return seen, n
        before = len(seen)
        device.swipe(260, 1300, 260, 500, 600)
        time.sleep(0.5)
        if len(seen) == before and before and all(i["text"] in seen for i in [n for n in _nodes(device) if n["id"] == "design_menu_item_text"]):
            break
    return seen, None


# ── python_action targets ───────────────────────────────────────────────────

def restart_app(device, params, context):
    device.adb("shell", "am", "force-stop", _PKG)
    time.sleep(0.5)
    return {}


def open_manual(device, params, context):
    time.sleep(1.0)
    st = read_state(device)
    if st["screen"] == "drawer":
        intro = next(n for n in _nodes(device) if n["id"] == "design_menu_item_text" and n["text"] == "Introduction")
        device.tap(*_centre(intro), delay=1.6)
    st = _wait(device, "page")
    for _ in range(6):
        if st["text"]:
            break
        time.sleep(0.7)
        st = read_state(device)
    return {"state": st}


def list_chapters(device, params, context):
    _open_drawer(device)
    seen, _ = _drawer_scan(device)
    return {"count": len(seen), "chapters": seen}


def open_chapter(device, params, context):
    name = str(params.get("name", "")).strip()
    if not name:
        raise RuntimeError("name must be a chapter name, for example Water")
    _open_drawer(device)
    seen, node = _drawer_scan(device, name)
    if not node:
        raise RuntimeError(f"no chapter named {name}; chapters: {', '.join(seen)}")
    device.tap(*_centre(node), delay=1.8)
    st = _wait(device, "page")
    return {"chapter": node["text"], "state": st}


def seed_page(device, params, context):
    """Pre-step: make sure a chapter page is on screen."""
    if read_state(device)["screen"] != "page":
        open_chapter(device, {"name": "Water"}, context)
    return {}


def read_page(device, params, context):
    return {"state": _wait(device, "page")}


def scroll_page(device, params, context):
    pages = int(params.get("pages", 1))
    if not 1 <= pages <= 5:
        raise RuntimeError("pages must be 1 to 5")
    before = _wait(device, "page")["text"]
    for _ in range(pages):
        device.swipe(360, 1250, 360, 400, 500)
        time.sleep(0.8)
    st = _wait(device, "page")
    st["moved"] = st["text"] != before
    return {"pages": pages, "state": st}


# ── validators ──────────────────────────────────────────────────────────────

def page_open(device, context) -> bool:
    return read_state(device)["screen"] == "page"


def chapters_listed(device, context) -> bool:
    return len(context.result["chapters"]) >= 10 and context.result["chapters"][0] == "Introduction"


def chapter_opened(device, context) -> bool:
    s = read_state(device)
    return s["screen"] == "page" and bool(context.result["state"]["text"])


def page_read(device, context) -> bool:
    s = read_state(device)
    return s["screen"] == "page" and bool(context.result["state"]["text"])


def page_scrolled(device, context) -> bool:
    return read_state(device)["screen"] == "page" and context.result["state"]["moved"]
