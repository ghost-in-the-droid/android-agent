"""AntennaPod skill helpers (browse only). python_action: (device, params, context) -> dict;
validators: (device, context) -> bool. Only on-screen nodes are read.

Never taps Subscribe, Download or Play. Taps in the top band (where heads-up
notifications appear) go through `guarded_tap`."""
from __future__ import annotations

import re
import shlex
import time

_ID = "de.danoeh.antennapod:id/"
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


def heads_up_showing(device) -> bool:
    out = device.adb("shell", "dumpsys activity service com.android.systemui/.SystemUIService | grep -m1 mHeadsUpPinnedMode")
    return "mHeadsUpPinnedMode=true" in (out or "")


def guarded_tap(device, node, wait_s: float = 15) -> bool:
    b = node["bounds"]
    if b[1] < _TOP_BAND:
        deadline = time.monotonic() + wait_s
        while heads_up_showing(device):
            if time.monotonic() > deadline:
                return False
            time.sleep(1)
    device.tap((b[0] + b[2]) // 2, (b[1] + b[3]) // 2)
    return True


def _clean(s: str) -> str:
    return s.replace("&#x27;", "'").replace("&quot;", '"').replace("&amp;", "&").strip()


def read_results(device) -> list[dict]:
    nodes = visible_nodes(device)
    titles = [n for n in nodes if n["id"] == _ID + "txtvTitle"]
    authors = [n for n in nodes if n["id"] == _ID + "txtvAuthor"]
    out = []
    for t in titles:
        a = next((x["text"] for x in authors if 0 <= x["bounds"][1] - t["bounds"][3] <= 10), "")
        out.append({"title": _clean(t["text"]), "author": _clean(a), "node": t})
    return out


# ── python_action targets ───────────────────────────────────────────────────

def close_app(device, params, context):
    device.adb("shell", "am", "force-stop", "de.danoeh.antennapod")
    return {"success": True}


def open_search(device, params, context):
    """AntennaPod's own deep link opens the search screen with the query filled in."""
    q = str(params["query"]).replace("%", "%25").replace("&", "%26").replace("#", "%23").replace(" ", "%20")
    url = "https://antennapod.org/deeplink/search?query=" + q
    device.adb("shell", "am start -a android.intent.action.VIEW -p de.danoeh.antennapod -d " + shlex.quote(url))
    return {"success": True}


def search_online(device, params, context):
    btn = next((n for n in visible_nodes(device) if n["id"] == _ID + "actionButton" and n["text"] == "Search online"), None)
    if btn is None:
        return {"success": False, "error": "'Search online' button not on screen"}
    if not guarded_tap(device, btn):
        return {"success": False, "error": "heads-up notification over the button; not tapping"}
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        time.sleep(1.5)
        res = read_results(device)
        if res:
            return {"success": True, "data": {"results": [{"title": r["title"], "author": r["author"]} for r in res],
                                              "count": len(res)}}
        if any(n["text"].startswith("No results") for n in visible_nodes(device) if n["id"] == _ID + "txtvEmpty"):
            break
    return {"success": True, "data": {"results": [], "count": 0}}


def open_result(device, params, context):
    want = str(params.get("title") or "").lower()
    res = read_results(device)
    if not res:
        return {"success": False, "error": "no search results on screen"}
    hit = next((r for r in res if want and want in r["title"].lower()), res[0])
    if not guarded_tap(device, hit["node"]):
        return {"success": False, "error": "heads-up notification over the result; not tapping"}
    return {"success": True}


def read_preview(device, params, context):
    nodes = visible_nodes(device)
    get = lambda s: next((_clean(n["text"]) for n in nodes if n["id"] == _ID + s), "")
    episodes = []
    for t in (n for n in nodes if n["id"] == _ID + "txtvTitle" and n["bounds"][1] > 1100):
        row = [n for n in nodes if abs(n["bounds"][1] - t["bounds"][1]) <= 110]
        date = next((n["desc"] or n["text"] for n in row if n["id"] == _ID + "txtvPubDate"), "")
        dur = next((n["text"] for n in row if n["id"] == _ID + "txtvDuration"), "")
        size = next((n["text"] for n in row if n["id"] == _ID + "size"), "")
        episodes.append({"title": _clean(t["text"]), "date": date, "duration": dur, "size": size})
    data = {"title": get("txtvTitle"), "author": get("txtvAuthor"),
            "description": get("headerDescriptionLabel"), "episodes": episodes}
    return {"success": bool(data["title"]), "data": {"podcast": data}, "error": "podcast preview not on screen"}


def read_subscriptions(device, params, context):
    nodes = visible_nodes(device)
    names = [ _clean(n["text"]) for n in nodes if n["id"] in (_ID + "txtvTitle", _ID + "titleLabel") and n["text"]
              and n["bounds"][1] > 300]
    empty = any("not subscribed" in n["text"] or "No subscriptions" in n["text"] for n in nodes)
    return {"success": True, "data": {"subscriptions": [] if empty else names}}


# ── End-state validators: (device, context) -> bool ──────────────────────────

def results_ok(device, context) -> bool:
    return isinstance(context.result.get("results"), list) and context.result.get("count", 0) > 0


def preview_ok(device, context) -> bool:
    p = context.result.get("podcast") or {}
    subscribe_visible = any(n["id"] == _ID + "butSubscribe" for n in visible_nodes(device))
    return bool(p.get("title")) and subscribe_visible


def subs_ok(device, context) -> bool:
    return isinstance(context.result.get("subscriptions"), list)
