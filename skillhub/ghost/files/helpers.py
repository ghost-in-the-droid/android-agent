"""Files (DocumentsUI) skill helpers. python_action: (device, params, context) -> dict;
validators: (device, context) -> bool. Only on-screen nodes are read."""
from __future__ import annotations

import re
import shlex
import time

_ID = "com.google.android.documentsui:id/"


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


def _uri_encode(s: str) -> str:
    """Percent-encode everything except unreserved characters (RFC 3986)."""
    keep = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")
    return "".join(c if c in keep else "".join(f"%{b:02X}" for b in c.encode()) for c in s)


def _inside(inner, outer) -> bool:
    return outer[0] <= inner[0] and outer[1] <= inner[1] and inner[2] <= outer[2] and inner[3] <= outer[3]


def read_items(device) -> list[dict]:
    """Items in the current grid or list: name, size, date, is_folder (folders have no size)."""
    items, seen = [], set()
    for _ in range(8):
        nodes = visible_nodes(device)
        before = len(items)
        for card in (n for n in nodes if n["id"] == _ID + "item_root"):
            inside = [n for n in nodes if _inside(n["bounds"], card["bounds"])]
            # Row text views use framework ids (android:id/title, android:id/date).
            get = lambda s: next((n["text"] for n in inside if n["id"].endswith(":id/" + s)), "")
            name = get("title")
            if not name or name in seen:
                continue
            seen.add(name)
            size = get("details")
            items.append({"name": name, "size": size, "date": get("date").replace(" ", " "), "is_folder": not size})
        if len(items) == before:
            break
        device.swipe(540, 1900, 540, 1000, 300)
    return items


def _tap(device, node):
    b = node["bounds"]
    device.tap((b[0] + b[2]) // 2, (b[1] + b[3]) // 2)


# ── python_action targets ───────────────────────────────────────────────────

def open_folder(device, params, context):
    """Open a folder under internal storage by path, e.g. Download or DCIM/Camera."""
    path = str(params.get("path") or "").strip("/")
    device.adb("shell", "am", "force-stop", "com.google.android.documentsui")
    uri = "content://com.android.externalstorage.documents/document/" + _uri_encode("primary:" + path)
    device.adb("shell", "am start -a android.intent.action.VIEW -t vnd.android.document/directory -d " + shlex.quote(uri))
    return {"success": True}


def list_items(device, params, context):
    items = read_items(device)
    return {"success": True, "data": {"path": params.get("path", ""), "items": items, "count": len(items)}}


def search(device, params, context):
    nodes = visible_nodes(device)
    btn = next((n for n in nodes if n["id"] == _ID + "option_menu_search"), None)
    if btn is None:
        return {"success": False, "error": "search button not on screen"}
    _tap(device, btn)
    time.sleep(1.5)
    device.adb("shell", "input", "text", shlex.quote(str(params["query"]).replace(" ", "%s")))
    device.adb("shell", "input", "keyevent", "KEYCODE_ENTER")
    time.sleep(3)
    items = read_items(device)
    return {"success": True, "data": {"query": params["query"], "items": items, "count": len(items)}}


def new_folder(device, params, context):
    """More options > New folder > type name > OK."""
    nodes = visible_nodes(device)
    more = next((n for n in nodes if n["desc"] == "More options"), None)
    if more is None:
        return {"success": False, "error": "More options not on screen"}
    _tap(device, more)
    time.sleep(1.5)
    item = next((n for n in visible_nodes(device) if n["text"] == "New folder" and n["id"].endswith(":id/title")), None)
    if item is None:
        device.adb("shell", "input", "keyevent", "KEYCODE_BACK")
        return {"success": False, "error": "New folder is not offered here (read-only location?)"}
    _tap(device, item)
    time.sleep(1.5)
    field = next((n for n in visible_nodes(device) if n["id"] == "android:id/text1"), None)
    if field is None:
        return {"success": False, "error": "folder name field not found"}
    _tap(device, field)
    time.sleep(0.8)
    device.adb("shell", "input", "text", shlex.quote(str(params["name"]).replace(" ", "%s")))
    time.sleep(0.8)
    ok = next((n for n in visible_nodes(device) if n["id"] == "android:id/button1"), None)  # dialog moves with the keyboard
    if ok is None:
        return {"success": False, "error": "OK button not found"}
    _tap(device, ok)
    time.sleep(2)
    return {"success": True}


# ── End-state validators: (device, context) -> bool ──────────────────────────

def _in_folder(device, path: str) -> bool:
    """The header reads 'Files in <last path segment>'; an unknown path opens some
    other view instead, which must not count as success."""
    leaf = str(path or "").strip("/").split("/")[-1]
    if not leaf:
        return True
    return any(n["id"] == _ID + "header_title" and n["text"] == f"Files in {leaf}" for n in visible_nodes(device))


def listing_ok(device, context) -> bool:
    return isinstance(context.result.get("items"), list) and _in_folder(device, context.params.get("path"))


def search_ok(device, context) -> bool:
    q = str(context.params["query"]).lower()
    items = context.result.get("items")
    return isinstance(items, list) and all(q in i["name"].lower() for i in items)


def folder_exists(device, context) -> bool:
    want = str(context.params["name"])
    if not _in_folder(device, context.params.get("path")):
        return False
    items = read_items(device)
    context.result["folder"] = next((i for i in items if i["name"] == want and i["is_folder"]), None)
    return context.result["folder"] is not None
