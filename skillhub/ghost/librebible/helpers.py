"""librebible helpers (LibreBible, xyz.yeikoff.librebible): read the Latin Vulgate offline.

Three screens: the book list, a chapter grid (header has Back and the book name) and the verses of one chapter
(header title is "Book N"). Verses are unnumbered text rows, so verse n is the nth row.
"""
from __future__ import annotations

import html
import re
import time

_PKG = "xyz.yeikoff.librebible"
_HEADER_Y = 160


def _nodes(device) -> list[dict]:
    out = []
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"text": html.unescape(a.get("text", "")), "desc": html.unescape(a.get("content-desc", "")),
                        "bounds": tuple(nums)})
    return out


def _centre(n):
    b = n["bounds"]
    return (b[0] + b[2]) // 2, (b[1] + b[3]) // 2


def read_state(device, nodes=None) -> dict:
    nodes = nodes if nodes is not None else _nodes(device)
    head = [n for n in nodes if n["bounds"][3] <= _HEADER_Y and n["text"]]
    if not any(n["text"] == "LibreBible" for n in head):
        return {"screen": "other"}
    back = any(n["desc"] == "Back" for n in nodes)
    titles = [n["text"] for n in head if n["text"] != "LibreBible"]
    if not back:
        return {"screen": "books"}
    title = titles[0] if titles else ""
    m = re.match(r"^(.+) (\d+)$", title)
    if m:
        return {"screen": "verses", "book": m.group(1), "chapter": int(m.group(2))}
    return {"screen": "chapters", "book": title}


def _body(nodes):
    return [n for n in nodes if n["text"] and n["bounds"][1] >= _HEADER_Y and n["bounds"][3] > _HEADER_Y]


def _wait(device, tries=10):
    for _ in range(tries):
        st = read_state(device)
        if st["screen"] != "other":
            return st
        time.sleep(0.8)
    raise RuntimeError("LibreBible is not on screen")


def _up(device):
    """Tap the in-app Back arrow until the book list shows (never the system Back key)."""
    for _ in range(4):
        nodes = _nodes(device)
        if read_state(device, nodes)["screen"] == "books":
            return
        back = next((n for n in nodes if n["desc"] == "Back"), None)
        if not back:
            raise RuntimeError("cannot find the in-app Back arrow")
        device.tap(*_centre(back), delay=1.2)
    raise RuntimeError("could not return to the book list")


def _merge(acc: list[str], page: list[str]) -> int:
    """Append the part of page that follows what is already in acc; return how many were added."""
    start = 0
    if acc:
        for i in range(len(page) - 1, -1, -1):
            if page[i] == acc[-1]:
                start = i + 1
                break
    new = page[start:]
    acc.extend(new)
    return len(new)


def _scroll_collect(device, max_pages=40) -> list[str]:
    acc: list[str] = []
    for _ in range(max_pages):
        page = [n["text"] for n in sorted(_body(_nodes(device)), key=lambda n: n["bounds"][1])]
        added = _merge(acc, page)
        if not added and acc:
            break
        device.swipe(360, 1300, 360, 450, 600)
        time.sleep(0.9)
    return acc


def _top(device):
    for _ in range(12):
        device.swipe(360, 400, 360, 1300, 300)
        time.sleep(0.4)


def _find_and_tap(device, text: str) -> bool:
    for _ in range(40):
        nodes = _body(_nodes(device))
        hit = next((n for n in nodes if n["text"] == text), None)
        if hit:
            device.tap(*_centre(hit), delay=1.4)
            return True
        before = [n["text"] for n in nodes]
        device.swipe(360, 1300, 360, 600, 500)
        time.sleep(0.7)
        if [n["text"] for n in _body(_nodes(device))] == before:
            return False
    return False


# ── python_action targets ───────────────────────────────────────────────────

def restart_app(device, params, context):
    device.adb("shell", "am", "force-stop", _PKG)
    time.sleep(0.5)
    return {}


def open_books(device, params, context):
    _wait(device)
    _up(device)
    return {"state": read_state(device)}


def list_books(device, params, context):
    _wait(device)
    _up(device)
    _top(device)
    books = _scroll_collect(device)
    return {"count": len(books), "books": books, "state": read_state(device)}


def open_chapter(device, params, context):
    book = str(params.get("book", "")).strip()
    chapter = str(params.get("chapter", "1")).strip()
    if not book or not chapter.isdigit() or int(chapter) < 1:
        raise RuntimeError("give book (for example Ruth) and chapter (a number)")
    _wait(device)
    _up(device)
    _top(device)
    if not _find_and_tap(device, book):
        raise RuntimeError(f"book not found: {book}")
    time.sleep(0.8)
    if read_state(device)["screen"] != "chapters":
        raise RuntimeError("the chapter list did not open")
    if not _find_and_tap(device, chapter):
        raise RuntimeError(f"chapter {chapter} not found in {book}")
    st = _wait(device)
    if st.get("screen") != "verses" or st["chapter"] != int(chapter):
        raise RuntimeError(f"chapter did not open (screen: {st})")
    return {"state": st}


def open_ruth(device, params, context):
    return open_chapter(device, {"book": "Ruth", "chapter": "1"}, context)


def read_chapter(device, params, context):
    st = _wait(device)
    if st["screen"] != "verses":
        raise RuntimeError("open a chapter first (open_chapter)")
    _top(device)
    verses = _scroll_collect(device)
    return {"book": st["book"], "chapter": st["chapter"], "verse_count": len(verses),
            "verses": [{"verse": i + 1, "text": t} for i, t in enumerate(verses)], "state": read_state(device)}


# ── validators ──────────────────────────────────────────────────────────────

def books_open(device, context) -> bool:
    return read_state(device).get("screen") == "books"


def books_listed(device, context) -> bool:
    r = context.result
    return read_state(device).get("screen") == "books" and r["count"] >= 60 and "Genesis" in r["books"] and "Ruth" in r["books"]


def chapter_opened(device, context) -> bool:
    s = read_state(device)
    st = context.result["state"]
    return s.get("screen") == "verses" and s["book"] == st["book"] and s["chapter"] == st["chapter"]


def chapter_read(device, context) -> bool:
    r = context.result
    s = read_state(device)
    return (s.get("screen") == "verses" and s["book"] == r["book"] and s["chapter"] == r["chapter"]
            and r["verse_count"] >= 1 and all(v["text"] for v in r["verses"]))
