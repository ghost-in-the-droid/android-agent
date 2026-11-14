"""Fossify Gallery skill helpers. python_action: (device, params, context) -> dict;
validators: (device, context) -> bool. Only on-screen nodes are read.

Album cards, the filename toggle and the Properties button sit in the top band of
the screen where heads-up notifications appear. Taps there go through
`guarded_tap`, which refuses while SystemUI reports a pinned heads-up."""
from __future__ import annotations

import re
import shlex
import time

_ID = "org.fossify.gallery:id/"
_TOP_BAND = 700


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
            if box[2] > box[0] and box[3] > box[1] and box[0] >= 0:
                out.append({"text": n.get("text") or "", "desc": n.get("contentDescription") or "",
                            "id": n.get("resourceId") or "", "bounds": box})
            stack.extend(reversed(n.get("children") or []))
        out.sort(key=lambda n: (n["bounds"][1], n["bounds"][0]))
        return out
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"text": a.get("text", ""), "desc": a.get("content-desc", ""),
                        "id": a.get("resource-id", ""), "bounds": tuple(nums)})
    return out


def _inside(inner, outer) -> bool:
    return outer[0] <= inner[0] and outer[1] <= inner[1] and inner[2] <= outer[2] and inner[3] <= outer[3]


def heads_up_showing(device) -> bool:
    out = device.adb("shell", "dumpsys activity service com.android.systemui/.SystemUIService | grep -m1 mHeadsUpPinnedMode")
    return "mHeadsUpPinnedMode=true" in (out or "")


def guarded_tap(device, node, wait_s: float = 15) -> bool:
    """Tap; when the node is in the top band, only while no heads-up is pinned."""
    b = node["bounds"]
    if b[1] < _TOP_BAND:
        deadline = time.monotonic() + wait_s
        while heads_up_showing(device):
            if time.monotonic() > deadline:
                return False
            time.sleep(1)
    device.tap((b[0] + b[2]) // 2, (b[1] + b[3]) // 2)
    return True


def read_albums(device) -> list[dict]:
    albums, seen = [], set()
    for _ in range(6):
        nodes = visible_nodes(device)
        before = len(albums)
        for card in (n for n in nodes if n["id"] == _ID + "dir_holder"):
            inside = [n for n in nodes if _inside(n["bounds"], card["bounds"])]
            name = next((n["text"] for n in inside if n["id"] == _ID + "dir_name"), "")
            cnt = next((n["text"] for n in inside if n["id"] == _ID + "photo_cnt"), "")
            if name and name not in seen:
                seen.add(name)
                albums.append({"name": name, "count": int(cnt) if cnt.isdigit() else None, "node": card})
        if len(albums) == before:
            break
        device.swipe(540, 1900, 540, 1000, 300)
    return albums


def _media_id(device, name: str) -> str | None:
    """MediaStore id for a display name (images first, then videos)."""
    for table in ("images", "video"):
        where = "_display_name=" + "'" + name.replace("'", "''") + "'"
        out = device.adb("shell", "content query --uri content://media/external/%s/media --projection _id --where %s"
                         % (table, shlex.quote(where))) or ""
        m = re.search(r"_id=(\d+)", out)
        if m:
            return f"content://media/external/{table}/media/{m.group(1)}"
    return None


# ── python_action targets ───────────────────────────────────────────────────

def close_gallery(device, params, context):
    device.adb("shell", "am", "force-stop", "org.fossify.gallery")
    return {"success": True}


def list_albums(device, params, context):
    albums = [{k: v for k, v in a.items() if k != "node"} for a in read_albums(device)]
    return {"success": True, "data": {"albums": albums, "count": len(albums)}}


def open_album_and_list(device, params, context):
    want = str(params["album"])
    hit = next((a for a in read_albums(device) if a["name"] == want), None)
    if hit is None:
        return {"success": False, "error": f"no album named {want!r}"}
    if not guarded_tap(device, hit["node"]):
        return {"success": False, "error": "heads-up notification over the album; not tapping"}
    time.sleep(2)
    nodes = visible_nodes(device)
    if not any(n["id"] == _ID + "medium_name" for n in nodes) and any(n["id"] == _ID + "media_item_holder" for n in nodes):
        toggle = next((n for n in nodes if n["id"] == _ID + "toggle_filename"), None)
        if toggle is None or not guarded_tap(device, toggle):
            return {"success": False, "error": "cannot show file names"}
        time.sleep(1.5)
    names, seen = [], set()
    for _ in range(10):
        before = len(names)
        for n in visible_nodes(device):
            if n["id"] == _ID + "medium_name" and n["text"] and n["text"] not in seen:
                seen.add(n["text"])
                names.append(n["text"])
        if len(names) == before:
            break
        device.swipe(540, 1900, 540, 1000, 300)
    return {"success": True, "data": {"album": want, "photos": names, "count": len(names)}}


def open_photo(device, params, context):
    uri = _media_id(device, str(params["name"]))
    if uri is None:
        return {"success": False, "error": f"no image or video named {params['name']!r} in MediaStore"}
    mime = "video/*" if "/video/" in uri else "image/*"
    device.adb("shell", "am start -a android.intent.action.VIEW -p org.fossify.gallery -t %s -d %s"
               % (shlex.quote(mime), shlex.quote(uri)))
    return {"success": True, "data": {"uri": uri}}


def read_properties(device, params, context):
    btn = next((n for n in visible_nodes(device) if n["id"] == _ID + "menu_properties"), None)
    if btn is None:
        return {"success": False, "error": "Properties button not on screen"}
    if not guarded_tap(device, btn):
        return {"success": False, "error": "heads-up notification over the toolbar; not tapping"}
    time.sleep(1.5)
    nodes = visible_nodes(device)
    labels = [n for n in nodes if n["id"] == _ID + "property_label"]
    values = [n for n in nodes if n["id"] == _ID + "property_value"]
    props = {}
    for lab in labels:
        val = next((v for v in values if 0 <= v["bounds"][1] - lab["bounds"][3] <= 10), None)
        if val:
            props[lab["text"].lower().replace(" ", "_")] = val["text"]
    ok = next((n for n in nodes if n["id"] == "android:id/button1"), None)
    if ok:
        device.tap((ok["bounds"][0] + ok["bounds"][2]) // 2, (ok["bounds"][1] + ok["bounds"][3]) // 2)
    return {"success": bool(props), "data": {"properties": props}, "error": "no properties read"}


# ── End-state validators: (device, context) -> bool ──────────────────────────

def albums_ok(device, context) -> bool:
    return isinstance(context.result.get("albums"), list)


def photos_ok(device, context) -> bool:
    return isinstance(context.result.get("photos"), list) and any(
        n["text"] == f"Search in {context.params['album']}" for n in visible_nodes(device))


def photo_shown(device, context) -> bool:
    want = str(context.params["name"])
    return any(n["text"] == want for n in visible_nodes(device))


def properties_ok(device, context) -> bool:
    p = context.result.get("properties") or {}
    return p.get("name") == str(context.params["name"]) and bool(p.get("resolution") or p.get("size"))
