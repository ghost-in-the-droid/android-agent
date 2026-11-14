"""Tasks.org skill helpers (local lists only). python_action: (device, params, context) -> dict;
validators: (device, context) -> bool. Only on-screen nodes are read.

The task editor's only Save control sits in the top toolbar, inside the band where
heads-up notifications appear; a heads-up there can carry one-tap actions. Every
top-band tap goes through `guarded_top_tap`, which refuses while SystemUI reports a
pinned heads-up."""

from __future__ import annotations

import re
import shlex
import time
import xml.etree.ElementTree as ET

_ID = "org.tasks:id/"
_TOP_BAND = 700  # px: heads-up notifications occupy roughly y < 650 on 1080x2400


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
                out.append(
                    {
                        "text": n.get("text") or "",
                        "desc": n.get("contentDescription") or "",
                        "id": n.get("resourceId") or "",
                        "bounds": box,
                    }
                )
            stack.extend(reversed(n.get("children") or []))
        out.sort(key=lambda n: (n["bounds"][1], n["bounds"][0]))
        return out
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append(
                {
                    "text": a.get("text", ""),
                    "desc": a.get("content-desc", ""),
                    "id": a.get("resource-id", ""),
                    "bounds": tuple(nums),
                }
            )
    return out


def _center(node):
    b = node["bounds"]
    return (b[0] + b[2]) // 2, (b[1] + b[3]) // 2


def heads_up_showing(device) -> bool | None:
    try:
        out = device.adb(
            "shell", "dumpsys activity service com.android.systemui/.SystemUIService | grep -m1 mHeadsUpPinnedMode"
        )
    except RuntimeError:
        return None
    match = re.search(r"mHeadsUpPinnedMode=(true|false)", out or "")
    return match.group(1) == "true" if match else None


def app_control_exposed(device, node) -> bool:
    """OEM fallback: require app focus and the same unobscured app-owned target.

    A missing AOSP dump field is unknown, not evidence that a tap is safe.
    Inspect only window identity and the active accessibility tree.
    """
    try:
        focus = device.adb("shell", "dumpsys window | grep -m1 mCurrentFocus")
        if not re.search(r"\borg\.tasks/", focus):
            return False
        tree = ET.fromstring(device.dump_xml(use_portal=False))
    except (RuntimeError, ET.ParseError):
        return False
    target = tuple(node["bounds"])
    found = False
    for entry in tree.iter("node"):
        box = tuple(map(int, re.findall(r"-?\d+", entry.get("bounds", ""))))
        if len(box) != 4:
            continue
        package = entry.get("package", "")
        if package == "org.tasks" and box == target:
            found |= bool(
                (node.get("id") and entry.get("resource-id") == node["id"])
                or (node.get("desc") and entry.get("content-desc") == node["desc"])
            )
        if (
            package
            and package != "org.tasks"
            and max(box[0], target[0]) < min(box[2], target[2])
            and max(box[1], target[1]) < min(box[3], target[3])
        ):
            return False
    if found:
        return True
    # Compose semantics can be absent from native UI Automator while Portal
    # still exposes the control. Verify the focused window and every window
    # above it before accepting a fresh matching accessibility target.
    return focused_window_exposes(device, node, focus)


def focused_window_exposes(device, node, focus):
    match = re.search(r"mCurrentFocus=Window\{(\w+) u\d+ org\.tasks/", focus)
    if not match:
        return False
    try:
        windows = device.adb("shell", "dumpsys window windows")
    except RuntimeError:
        return False
    blocks = re.split(r"(?m)^\s*Window #\d+ ", windows)[1:]
    target = tuple(node["bounds"])
    for block in blocks:
        current = block.startswith("Window{" + match.group(1) + " ")
        visible = re.search(r"\bisVisible=(true|false)", block)
        if not visible:
            return False
        if visible.group(1) == "false":
            if current:
                return False
            continue
        frame = re.search(r"\bframe=\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]", block)
        if not frame:
            return False
        left, top, right, bottom = map(int, frame.groups())
        if current:
            if not re.search(r"\bpackage=org\.tasks\s", block):
                return False
            if not (left <= target[0] < target[2] <= right and top <= target[1] < target[3] <= bottom):
                return False
            return any(
                n["bounds"] == target
                and ((node.get("id") and n["id"] == node["id"]) or (node.get("desc") and n["desc"] == node["desc"]))
                for n in visible_nodes(device)
            )
        if max(left, target[0]) < min(right, target[2]) and max(top, target[1]) < min(bottom, target[3]):
            return False
    return False


def guarded_top_tap(device, node, wait_s: float = 15) -> bool:
    """Tap a control in the top band only when no heads-up notification is pinned."""
    deadline = time.monotonic() + wait_s
    while True:
        pinned = heads_up_showing(device)
        if pinned is False or (pinned is None and app_control_exposed(device, node)):
            device.tap(*_center(node))
            return True
        if time.monotonic() > deadline:
            return False
        time.sleep(1)


def read_rows(device) -> list[dict]:
    rows, seen = [], set()
    for _ in range(6):
        nodes = visible_nodes(device)
        before = len(rows)
        header = ""
        for n in nodes:
            if n["id"] == _ID + "header":
                header = n["text"]
            if n["id"] != _ID + "rowBody":
                continue
            b = n["bounds"]
            inside = [x for x in nodes if b[1] <= x["bounds"][1] and x["bounds"][3] <= b[3]]
            title = next((x["text"] for x in inside if x["id"] == _ID + "title"), "")
            desc = next((x["text"] for x in inside if x["id"] == _ID + "description"), "")
            if not title or (title, desc) in seen:
                continue
            seen.add((title, desc))
            rows.append({"title": title, "notes": desc, "section": header})
        if len(rows) == before:
            break
        device.swipe(540, 1900, 540, 1100, 300)
    return rows


# ── python_action targets ───────────────────────────────────────────────────


def close_tasks(device, params, context):
    device.adb("shell", "am", "force-stop", "org.tasks")
    return {"success": True}


def open_editor(device, params, context):
    """Open a prefilled task editor via the app's share target (subject = title,
    text = notes). Quoted here because `adb shell` re-splits extras with spaces."""
    cmd = [
        "am",
        "start",
        "-a",
        "android.intent.action.SEND",
        "-t",
        "text/plain",
        "-p",
        "org.tasks",
        "--es",
        "android.intent.extra.SUBJECT",
        str(params["title"]),
    ]
    if params.get("notes"):
        cmd += ["--es", "android.intent.extra.TEXT", str(params["notes"])]
    device.adb("shell", " ".join(shlex.quote(c) for c in cmd))
    return {"success": True}


def save_task(device, params, context):
    nodes = visible_nodes(device)
    title = next((n for n in nodes if n["text"] == str(params["title"])), None)
    save = next((n for n in nodes if n["desc"] == "Save" and n["bounds"][1] < _TOP_BAND), None)
    if title is None or save is None:
        return {"success": False, "error": "editor with the task title and Save button not on screen"}
    if not guarded_top_tap(device, save):
        return {"success": False, "error": "a heads-up notification covers the Save button; not tapping"}
    time.sleep(2)
    return {"success": True}


def list_tasks(device, params, context):
    rows = read_rows(device)
    return {"success": True, "data": {"tasks": rows, "count": len(rows)}}


def complete(device, params, context):
    want = str(params["title"])
    nodes = visible_nodes(device)
    for n in nodes:
        if n["id"] == _ID + "title" and n["text"] == want:
            b = n["bounds"]
            box = next(
                (
                    x
                    for x in nodes
                    if x["id"] == _ID + "completeBox" and x["bounds"][1] <= b[1] + 5 and x["bounds"][3] >= b[1]
                ),
                None,
            )
            if box is None:
                break
            if box["bounds"][1] < _TOP_BAND and not guarded_top_tap(device, box):
                return {"success": False, "error": "heads-up notification over the task row"}
            if box["bounds"][1] >= _TOP_BAND:
                device.tap(*_center(box))
            time.sleep(2)
            return {"success": True, "data": {"completed": want}}
    return {"success": False, "error": f"no open task titled {want!r} on screen"}


def search(device, params, context):
    btn = next((n for n in visible_nodes(device) if n["id"] == _ID + "menu_search"), None)
    if btn is None:
        return {"success": False, "error": "search button not on screen"}
    device.tap(*_center(btn))
    time.sleep(1.5)
    device.adb("shell", "input", "text", shlex.quote(str(params["query"]).replace(" ", "%s")))
    time.sleep(2)
    # Search opens the IME. Fixed list swipes otherwise cross its gesture-typing
    # surface and can append text to the still-focused query during validation.
    device.adb("shell", "input", "keyevent", "KEYCODE_BACK")
    time.sleep(0.5)
    if not query_matches(device, params["query"]):
        return {"success": False, "error": "requested search query not visible after dismissing the keyboard"}
    rows = read_rows(device)
    return {"success": True, "data": {"query": params["query"], "tasks": rows, "count": len(rows)}}


# ── End-state validators: (device, context) -> bool ──────────────────────────


def task_listed(device, context) -> bool:
    want = str(context.params["title"])
    hit = next((r for r in read_rows(device) if r["title"] == want), None)
    context.result["task"] = hit
    return hit is not None


def task_gone(device, context) -> bool:
    return all(r["title"] != str(context.params["title"]) for r in read_rows(device))


def rewind_rows(device):
    for _ in range(6):
        device.swipe(540, 800, 540, 1900, 300)


def tasks_ok(device, context, *, query=None) -> bool:
    # Collection also collapses the search toolbar. Reveal it before checking
    # the query, and again after the independent read scrolls it offscreen.
    rewind_rows(device)
    if query is not None and not query_matches(device, query):
        return False
    rows = read_rows(device)
    if query is not None:
        rewind_rows(device)
        if not query_matches(device, query):
            return False
    tasks = context.result.get("tasks")
    return isinstance(tasks, list) and tasks == rows and context.result.get("count") == len(rows)


def query_matches(device, query) -> bool:
    return any(n["id"] == _ID + "search_src_text" and n["text"] == str(query) for n in visible_nodes(device))


def search_ok(device, context) -> bool:
    q = str(context.params["query"]).lower()
    tasks = context.result.get("tasks")
    return tasks_ok(device, context, query=context.params["query"]) and all(
        q in (t["title"] + " " + t["notes"]).lower() for t in tasks
    )
