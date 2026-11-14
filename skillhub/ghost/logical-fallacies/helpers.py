"""logical-fallacies helpers (Logical Defence, za.co.lukestonehm.logicaldefence): an offline encyclopedia of logical fallacies.

Each list entry is one accessibility node whose description is 'number / name / definition / example'. The list is scrolled
to collect entries; the sticky header above the list names the current category.
"""
from __future__ import annotations

import html
import re
import time

_ENTRY = re.compile(r"^(\d+)\n([^\n]+)\n(.*?)(?:\n(.*))?$", re.S)


def _nodes(device) -> list[dict]:
    out = []
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"text": html.unescape(a.get("text", "") or a.get("content-desc", "")), "cls": a.get("class", ""),
                        "bounds": tuple(nums)})
    return out


def _visible(device) -> tuple[str, list[dict]]:
    nodes = _nodes(device)
    entries, category = [], ""
    for n in nodes:
        m = _ENTRY.match(n["text"])
        if m and n["bounds"][1] > 140:
            entries.append({"number": int(m.group(1)), "name": m.group(2).strip(), "definition": m.group(3).strip(),
                            "example": (m.group(4) or "").strip(), "y": n["bounds"][1]})
        elif n["bounds"][1] in range(140, 160) and not n["text"].startswith(("Open", "Logical")) and n["text"]:
            category = n["text"]
    return category, entries


def _scroll(device, up: bool):
    if up:
        device.swipe(360, 400, 360, 1200, 300, delay=0.5)
    else:
        device.swipe(360, 1250, 360, 450, 350, delay=0.6)


def _to_top(device):
    """Swipe down until the first visible entry stops changing (numbers continue across categories)."""
    last = None
    for _ in range(25):
        _c, e = _visible(device)
        first = e[0]["number"] if e else None
        if first is not None and first == last:
            return
        last = first
        _scroll(device, up=True)
        time.sleep(0.3)


def _drawer_open(nodes) -> bool:
    return any(n["text"].startswith("Logical Defence\nThe beautiful") for n in nodes)


def go_list(device, params, context):
    for _ in range(4):
        nodes = _nodes(device)
        if _drawer_open(nodes):
            device.back()
            time.sleep(0.8)
            continue
        if _visible(device)[1]:
            return {}
        device.back()
        time.sleep(0.8)
    raise RuntimeError("the fallacy list is not on screen")


def _drawer_categories(device) -> list[dict]:
    """Open the navigation drawer and return the category entries (name + node)."""
    nodes = _nodes(device)
    if not _drawer_open(nodes):
        btn = next((n for n in nodes if n["text"] == "Open navigation menu"), None)
        if not btn:
            raise RuntimeError("navigation menu button not found")
        device.tap(*_centre(btn), delay=1.2)
    return [n for n in _nodes(device) if 340 < n["bounds"][1] and n["bounds"][2] <= 600 and n["text"]
            and "\n" not in n["text"] and n["cls"].endswith("View")]


def _centre(n):
    b = n["bounds"]
    return (b[0] + b[2]) // 2, (b[1] + b[3]) // 2


def _open_category(device, name: str):
    cats = _drawer_categories(device)
    hit = next((c for c in cats if c["text"].lower() == name.lower()), None)
    if not hit:
        device.back()
        raise RuntimeError(f"no category {name!r}; categories: {[c['text'] for c in cats]}")
    device.tap(*_centre(hit), delay=1.0)
    for i in range(5):  # wait for the drawer to close and the list to show
        nodes = _nodes(device)
        if not _drawer_open(nodes) and _visible(device)[1]:
            return
        if i == 2 and _drawer_open(nodes):
            device.back()  # the drawer did not close by itself
        time.sleep(0.6)


def collect(device, limit: int = 200) -> list[dict]:
    _to_top(device)
    seen: dict[int, dict] = {}
    stalls = 0
    for _ in range(60):
        cat, entries = _visible(device)
        new = 0
        for e in entries:
            if e["number"] not in seen:
                e = dict(e)
                e.pop("y", None)
                e["category"] = cat
                seen[e["number"]] = e
                new += 1
        if len(seen) >= limit:
            break
        stalls = stalls + 1 if not new else 0
        if stalls >= 2:
            break
        _scroll(device, up=False)
    return [seen[k] for k in sorted(seen)]


def list_categories(device, params, context):
    cats = [c["text"] for c in _drawer_categories(device)]
    device.back()
    time.sleep(0.8)
    return {"categories": cats}


def list_fallacies(device, params, context):
    cat = str(params.get("category", "")).strip()
    limit = int(params.get("limit", 30))
    if cat:
        _open_category(device, cat)
    items = collect(device, limit=limit)
    return {"category": items[0]["category"] if items else cat, "count": len(items),
            "fallacies": [{"number": e["number"], "name": e["name"]} for e in items[:limit]]}


def get_fallacy(device, params, context):
    want = str(params["name"]).strip().lower()
    cats = [c["text"] for c in _drawer_categories(device)]
    device.back()
    time.sleep(0.8)
    for cat in cats:
        _open_category(device, cat)
        for e in collect(device):
            if e["name"].lower() == want:
                e["category"] = cat
                return {"fallacy": e}
    raise RuntimeError(f"no fallacy named {params['name']!r}")


# ── validators ──────────────────────────────────────────────────────────────

def listed(device, context) -> bool:
    r = context.result
    nums = [f["number"] for f in r["fallacies"]]
    return r["count"] >= 3 and nums == sorted(nums) and len(set(nums)) == len(nums)


def found(device, context) -> bool:
    f = context.result["fallacy"]
    return bool(f["definition"]) and bool(f["category"]) and f["number"] >= 1


def categories_read(device, context) -> bool:
    return len(context.result["categories"]) >= 4
