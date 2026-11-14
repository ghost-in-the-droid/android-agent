"""Google Photos skill helpers (no account, device-only library).

Signature for python_action targets: (device, params, context) -> dict.
Validators: (device, context) -> bool.
Grid tiles carry no resource id; each is a clickable node whose content-desc
reads "Photo taken on Oct 5, 2026 8:12:33 PM" (or "Video taken on ...").
"""
from __future__ import annotations

import re
import time

PKG = "com.google.android.apps.photos"
_ID = PKG + ":id/"
_TILE = re.compile(r"^(Photo|Video) taken on (.+)$")


def visible_nodes(device) -> list[dict]:
    """Flatten the current screen into on-screen nodes: text, desc, id, bounds."""
    out: list[dict] = []
    tree = device.dump_portal_json() if hasattr(device, "dump_portal_json") else None
    if tree:
        stack = list(tree) if isinstance(tree, list) else [tree]
        while stack:
            n = stack.pop()
            b = n.get("boundsInScreen") or {}
            box = (b.get("left", 0), b.get("top", 0), b.get("right", 0), b.get("bottom", 0))
            if box[2] > box[0] and box[3] > box[1] and box[0] >= 0 and box[1] < 2400:
                out.append({"text": n.get("text") or "", "desc": n.get("contentDescription") or "",
                            "id": n.get("resourceId") or "", "bounds": box})
            stack.extend(reversed(n.get("children") or []))
        return sorted(out, key=lambda n: (n["bounds"][1], n["bounds"][0]))
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"text": a.get("text", ""), "desc": a.get("content-desc", ""),
                        "id": a.get("resource-id", ""), "bounds": tuple(nums)})
    return sorted(out, key=lambda n: (n["bounds"][1], n["bounds"][0]))


def open_home(device, params, context):
    """Cold-start Photos on its home grid, dismiss the sign-in backup sheet (tap outside it), select the Photos tab."""
    device.adb("shell", "am", "force-stop", PKG)
    device.adb("shell", "monkey", "-p", PKG, "-c", "android.intent.category.LAUNCHER", "1")
    stable = 0
    for _ in range(30):
        nodes = visible_nodes(device)
        ids = {n["id"] for n in nodes}
        if _ID + "backup_understandability_title" in ids or _ID + "sign_in_button" in ids:
            device.tap(540, 600)          # sheet has no dismiss button; tapping the dimmed area closes it
            stable = 0
            time.sleep(1.5)
            continue
        later = next((n for n in nodes if n["id"] == _ID + "negative_button" and n["text"] == "Not now"), None)
        if later:                         # "You're missing out / Update" promo for the preinstalled build
            x1, y1, x2, y2 = later["bounds"]
            device.tap((x1 + x2) // 2, (y1 + y2) // 2)
            stable = 0
            time.sleep(1.5)
            continue
        tab = next((n for n in nodes if n["id"] == _ID + "tab_photos"), None)
        stable = stable + 1 if tab else 0
        if stable == 1:
            x1, y1, x2, y2 = tab["bounds"]
            device.tap((x1 + x2) // 2, (y1 + y2) // 2)
        elif stable >= 3:                 # the backup sheet can slide in a few seconds after launch
            return {"success": True}
        time.sleep(1)
    return {"success": False, "error": "Photos home tab not reached"}


def _tiles(nodes) -> list[dict]:
    return [n for n in nodes if _TILE.match(n["desc"]) and not n["id"]]


def _merge(acc: list, page: list) -> list:
    """Append a scrolled page, skipping its longest prefix that repeats the tail of acc (tiles can share a date)."""
    for k in range(min(len(acc), len(page)), 0, -1):
        if [x[0] for x in acc[-k:]] == [x[0] for x in page[:k]]:
            return acc + page[k:]
    return acc + page


def list_photos(device, params, context):
    """Walk the grid (scrolling) and return folders seen and every item with kind + date, newest first."""
    limit = int(params.get("max_items") or 50)
    items: list[tuple] = []
    folders: list[str] = []
    last_page = None
    for _ in range(10):
        folder = None
        page = []
        for n in visible_nodes(device):
            if n["id"] == _ID + "collection_title" and n["text"]:
                folder = n["text"]
                if folder not in folders:
                    folders.append(folder)
            m = _TILE.match(n["desc"]) if not n["id"] else None
            if m:
                page.append((n["desc"], {"kind": m.group(1).lower(), "taken": m.group(2), "folder": folder}))
        if page == last_page:
            break
        items = _merge(items, page)
        last_page = page
        if len(items) >= limit:
            break
        device.swipe(540, 1800, 540, 700, 400)
        time.sleep(1.2)
    listed = [x[1] for x in items][:limit]
    return {"success": True, "data": {"items": listed, "count": len(listed), "folders": folders}}


def open_photo(device, params, context):
    """Open the index-th grid item (0 = newest) in the viewer and report its date."""
    index = int(params.get("index") or 0)
    seen: list[tuple] = []
    last = None
    for _ in range(6):
        tiles = _tiles(visible_nodes(device))
        page = [(t["desc"], t) for t in tiles]
        if [p[0] for p in page] == last:
            break
        last = [p[0] for p in page]
        before = len(seen)
        seen = _merge(seen, page)
        for i in range(before, len(seen)):
            t = seen[i][1]
            if i == index:
                x1, y1, x2, y2 = t["bounds"]
                device.tap((x1 + x2) // 2, (y1 + y2) // 2)
                time.sleep(2)
                m = _TILE.match(t["desc"])
                return {"success": True, "data": {"opened": {"kind": m.group(1).lower(), "taken": m.group(2)}}}
        device.swipe(540, 1800, 540, 700, 400)
        time.sleep(1.2)
    return {"success": False, "error": f"library has fewer than {index + 1} items ({len(seen)} seen)"}


def count_trash(device, params, context):
    nodes = visible_nodes(device)
    empty = any(n["id"] == _ID + "photos_trash_ui_empty_state_title_view" for n in nodes)
    count = 0 if empty else len(_tiles(nodes))
    return {"success": True, "data": {"trash_count": count, "trash_empty": empty}}


# ── End-state validators: (device, context) -> bool ──────────────────────────

def items_listed(device, context) -> bool:
    return isinstance(context.result.get("items"), list) and context.result.get("count") == len(context.result["items"])


def viewer_open(device, context) -> bool:
    """Photo items open in the photo view (its content-desc carries the date); video items
    open in the video player, which has no date to compare."""
    opened = context.result.get("opened") or {}
    deadline = time.monotonic() + 8
    while opened:
        nodes = visible_nodes(device)
        if opened.get("kind") == "video":
            if any(n["id"].endswith("photos_videoplayer_videolayout") for n in nodes):
                return True
        else:
            viewer = next((n for n in nodes if n["id"].endswith("photos_photofragment_components_background_photo_view")), None)
            if viewer and opened["taken"] in viewer["desc"]:
                return True
        if time.monotonic() > deadline:
            return False
        time.sleep(0.8)
    return False


def trash_read(device, context) -> bool:
    return isinstance(context.result.get("trash_count"), int)
