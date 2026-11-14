"""Google Messages skill helpers. python_action: (device, params, context) -> dict;
validators: (device, context) -> bool. Only on-screen nodes are read.

Safety: nothing here taps Send, a conversation row, or anything in the top band
where heads-up notifications appear (their smart-reply chips send immediately).
Conversations are opened with SENDTO intents and left with BACK."""
from __future__ import annotations

import re
import shlex

_ID = "com.google.android.apps.messaging:id/"


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


def _number(params) -> str:
    n = re.sub(r"[^\d+]", "", str(params["number"]))
    if not n:
        raise ValueError(f"no digits in number {params['number']!r}")
    return n


# ── python_action targets ───────────────────────────────────────────────────

def close_messages(device, params, context):
    device.adb("shell", "am", "force-stop", "com.google.android.apps.messaging")
    return {"success": True}


def open_conversation(device, params, context):
    """SENDTO smsto:<number>, with sms_body when `text` is given. Quoted here because
    `adb shell` re-splits intent extras that contain spaces."""
    cmd = ["am", "start", "-a", "android.intent.action.SENDTO", "-d", "smsto:" + _number(params)]
    if params.get("text"):
        cmd += ["--es", "sms_body", str(params["text"])]
    device.adb("shell", " ".join(shlex.quote(c) for c in cmd))
    return {"success": True}


def check_compose(device, params, context):
    """Abort (without sending) unless the compose box holds exactly the draft text."""
    box = next((n for n in visible_nodes(device) if n["id"] == _ID + "compose_message_text"), None)
    if box is None or box["text"] != str(params["text"]):
        return {"success": False, "error": f"compose box shows {box and box['text']!r}, expected the draft text"}
    return {"success": True}


def read_conversation_list(device, params, context):
    rows = []
    seen = set()
    for _ in range(5):
        nodes = visible_nodes(device)
        before = len(rows)
        for row in (n for n in nodes if n["id"] == _ID + "swipeableContainer"):
            inside = [n for n in nodes if _inside(n["bounds"], row["bounds"])]
            get = lambda suffix: next((n["text"] for n in inside if n["id"] == _ID + suffix), "")
            name, snippet, ts = get("conversation_name"), get("conversation_snippet"), get("conversation_timestamp")
            if not name or (name, snippet) in seen:
                continue
            seen.add((name, snippet))
            rows.append({"name": name, "snippet": snippet, "time": ts, "is_draft": ts == "Draft",
                         "unread": any(n["id"] == _ID + "unread_badge" for n in inside)})
        if len(rows) == before:
            break
        device.swipe(540, 1800, 540, 900, 300)
    return {"success": True, "data": {"conversations": rows, "count": len(rows)}}


_SAID = re.compile(r"^(.*?) said\s+(.*?)\s+\.,\s*(.*)$", re.S)


def read_messages(device, params, context):
    nodes = visible_nodes(device)
    title = next((n["text"] for n in nodes if n["id"] == _ID + "conversation_title"), "")
    msgs = []
    for n in nodes:
        if n["id"] != _ID + "message_content":
            continue
        m = _SAID.match(n["desc"])
        if m:
            meta = [p.strip() for p in m.group(3).split(",") if p.strip() and "press" not in p.lower()]
            msgs.append({"from": "me" if m.group(1) == "You" else m.group(1), "text": m.group(2).strip(),
                         "time": meta[0] if meta else ""})
    return {"success": bool(title), "data": {"conversation": title, "messages": msgs},
            "error": "conversation not on screen"}


# ── End-state validators: (device, context) -> bool ──────────────────────────

def draft_listed(device, context) -> bool:
    want = "You: " + str(context.params["text"])
    rows = read_conversation_list(device, {}, context)["data"]["conversations"]
    hit = next((r for r in rows if r["is_draft"] and r["snippet"] == want), None)
    context.result["draft"] = hit
    return hit is not None


def conversations_ok(device, context) -> bool:
    return isinstance(context.result.get("conversations"), list)


def messages_ok(device, context) -> bool:
    return bool(context.result.get("conversation")) and isinstance(context.result.get("messages"), list)
