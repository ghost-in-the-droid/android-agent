"""Phone (Google Dialer) skill helpers. python_action: (device, params, context) -> dict;
validators: (device, context) -> bool. Only on-screen nodes are read. Nothing here
ever presses Call."""
from __future__ import annotations

import re

_ID = "com.google.android.dialer:id/"


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


def digits_only(s: str) -> str:
    return re.sub(r"\D", "", s)


# ── python_action targets ───────────────────────────────────────────────────

def close_dialer(device, params, context):
    """Force-stop the dialer so it relaunches on a known tab state."""
    device.adb("shell", "am", "force-stop", "com.google.android.dialer")
    return {"success": True}


def open_dialpad(device, params, context):
    """ACTION_DIAL with tel:<number>. Built here rather than with launch_intent
    because `adb shell` re-splits a data URI that contains spaces."""
    import shlex
    number = re.sub(r"[^\d+*#,;]", "", str(params["number"]))
    if not number:
        return {"success": False, "error": f"no dialable digits in {params['number']!r}"}
    device.adb("shell", "am start -a android.intent.action.DIAL -d " + shlex.quote("tel:" + number.replace("#", "%23")))
    return {"success": True}


def read_dialpad(device, params, context):
    nodes = visible_nodes(device)
    digits = next((n["text"] for n in nodes if n["id"] == _ID + "digits"), "")
    matches = [n["text"] for n in nodes if n["id"] == _ID + "primary" and n["text"]]
    return {"success": True, "data": {"dialpad": {"number": digits, "matching_contacts": matches}}}


def read_call_log(device, params, context):
    limit = int(params.get("limit") or 20)
    entries: list[dict] = []
    seen = set()
    for _ in range(6):
        nodes = visible_nodes(device)
        before = len(entries)
        for card in (n for n in nodes if n["id"] == _ID + "new_call_log_entry_card"):
            inside = [n for n in nodes if _inside(n["bounds"], card["bounds"])]
            name = next((n["text"] for n in inside if n["id"] == _ID + "primary_text"), "")
            sub = next((n["text"] for n in inside if n["id"] == _ID + "secondary_text"), "")
            desc = card["desc"].lower()
            kind = next((k for k in ("missed", "incoming", "outgoing", "rejected", "blocked", "voicemail") if k in desc), "")
            key = (name, sub, card["desc"])
            if key in seen:
                continue
            seen.add(key)
            entries.append({"name": name, "detail": sub.replace("•", "|"), "type": kind})
        if len(entries) >= limit or len(entries) == before:
            break
        device.swipe(540, 1700, 540, 700, 300)
    entries = entries[:limit]
    return {"success": True, "data": {"calls": entries, "count": len(entries),
                                      "missed": sum(1 for e in entries if e["type"] == "missed")}}


def read_favorites(device, params, context):
    nodes = visible_nodes(device)
    names = []
    for n in nodes:
        m = re.match(r"(?:Call |Quick contact for )(.+)", n["desc"])
        if m and m.group(1) not in names and "key pad" not in n["desc"]:
            names.append(m.group(1))
    empty = any(n["id"] == _ID + "empty_content_view_message" for n in nodes)
    return {"success": True, "data": {"favorites": [] if empty else names}}


# ── End-state validators: (device, context) -> bool ──────────────────────────

def dialpad_has_number(device, context) -> bool:
    want = digits_only(str(context.params["number"]))
    shown = digits_only(next((n["text"] for n in visible_nodes(device) if n["id"] == _ID + "digits"), ""))
    return bool(want) and shown.endswith(want[-7:]) and len(shown) >= min(len(want), 7)


def call_log_ok(device, context) -> bool:
    calls = context.result.get("calls")
    return isinstance(calls, list) and all(c.get("name") for c in calls)


def favorites_ok(device, context) -> bool:
    return isinstance(context.result.get("favorites"), list)
