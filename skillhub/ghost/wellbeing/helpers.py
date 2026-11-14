"""Digital Wellbeing skill helpers. python_action: (device, params, context) -> dict;
validators: (device, context) -> bool. Only on-screen nodes are read."""
from __future__ import annotations

import html
import re
import time

_ID = "com.google.android.apps.wellbeing:id/"


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
                out.append({"text": n.get("text") or "", "desc": html.unescape(n.get("contentDescription") or ""),
                            "id": n.get("resourceId") or "", "bounds": box})
            stack.extend(reversed(n.get("children") or []))
        out.sort(key=lambda n: (n["bounds"][1], n["bounds"][0]))
        return out
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"text": html.unescape(a.get("text", "")), "desc": html.unescape(a.get("content-desc", "")),
                        "id": a.get("resource-id", ""), "bounds": tuple(nums)})
    return out


def _tap_xy(device, x, y):
    device.tap(int(x), int(y))


def _tap(device, node):
    b = node["bounds"]
    _tap_xy(device, (b[0] + b[2]) // 2, (b[1] + b[3]) // 2)


def _get(nodes, suffix, key="text"):
    return next((n[key] for n in nodes if n["id"] == _ID + suffix), "")


def read_app_rows(nodes) -> list[dict]:
    rows = []
    for lab in (n for n in nodes if n["id"] == _ID + "app_label"):
        y0, y1 = lab["bounds"][1] - 20, lab["bounds"][3] + 80
        used = next((n["text"] for n in nodes if n["id"] == _ID + "app_time" and y0 <= n["bounds"][1] <= y1), "")
        limit = next((n for n in nodes if n["id"] == _ID + "limit_button" and n["bounds"][1] <= lab["bounds"][1] <= n["bounds"][3]), None)
        ldesc = limit["desc"] if limit else ""
        m = None if ldesc.startswith("No timer") else re.match(r"(.+?) set for ", ldesc)
        rows.append({"app": lab["text"], "used": used, "timer": m.group(1) if m else None,
                     "timer_allowed": bool(limit) and "Can't set timer" not in ldesc, "limit_node": limit})
    return rows


def _collect_rows(device, until_app: str | None = None) -> list[dict]:
    rows, seen = [], set()
    for _ in range(12):
        nodes = visible_nodes(device)
        before = len(rows)
        for r in read_app_rows(nodes):
            if r["app"] not in seen:
                seen.add(r["app"])
                rows.append(r)
        if until_app and any(r["app"].lower() == until_app.lower() for r in rows):
            break
        if len(rows) == before and rows:
            break
        device.swipe(540, 2000, 540, 1100, 300)
        time.sleep(0.8)
    return rows


# ── python_action targets ───────────────────────────────────────────────────

def open_wellbeing(device, params, context):
    device.adb("shell", "am", "force-stop", "com.google.android.apps.wellbeing")
    device.adb("shell", "am", "start", "-n", "com.google.android.apps.wellbeing/.settings.TopLevelSettingsActivity")
    return {"success": True}


def read_today(device, params, context):
    nodes = visible_nodes(device)
    data = {"screen_time": _get(nodes, "today_screen_time"),
            "summary": _get(nodes, "pie_chart", "desc").strip(),
            "unlocks": _get(nodes, "unlock_count"),
            "notifications": _get(nodes, "notification_count")}
    for k in ("unlocks", "notifications"):
        data[k] = int(data[k]) if data[k].isdigit() else None
    return {"success": bool(data["screen_time"]), "data": {"today": data}, "error": "screen time not on screen"}


def open_dashboard(device, params, context):
    btn = next((n for n in visible_nodes(device) if n["id"] == _ID + "pie_chart_center_labels_container"), None)
    if btn is None:
        return {"success": False, "error": "'Go to dashboard' not on screen"}
    _tap(device, btn)
    for _ in range(15):
        time.sleep(1)
        if any(n["id"] == _ID + "app_label" for n in visible_nodes(device)):
            return {"success": True}
    return {"success": False, "error": "dashboard app list did not load"}


def list_usage(device, params, context):
    limit = int(params.get("limit") or 20)
    rows = _collect_rows(device)[:limit]
    return {"success": True, "data": {"apps": [{k: v for k, v in r.items() if k != "limit_node"} for r in rows],
                                      "count": len(rows)}}


def _picker_inputs(device):
    nodes = visible_nodes(device)
    pick = sorted((n for n in nodes if n["id"] == "android:id/numberpicker_input"), key=lambda n: n["bounds"][0])
    return nodes, pick


def _value(node) -> int:
    m = re.match(r"(\d+)", node["text"])
    return int(m.group(1)) if m else 0


def _step(device, picker, direction: int):
    b = picker["bounds"]
    h = b[3] - b[1]
    y = b[3] + h * 0.7 if direction > 0 else b[1] - h * 0.7
    _tap_xy(device, (b[0] + b[2]) // 2, y)
    time.sleep(0.6)


def set_timer(device, params, context):
    app = str(params["app"])
    total = int(params["minutes"])
    if total < 5 or total > 23 * 60 + 55 or total % 5:
        return {"success": False, "error": "minutes must be a multiple of 5 between 5 and 1435"}
    want_h, want_m = divmod(total, 60)
    row = next((r for r in _collect_rows(device, app) if r["app"].lower() == app.lower()), None)
    if row is None or not row["timer_allowed"]:
        return {"success": False, "error": f"{app!r} not in the dashboard list or a timer is not allowed for it"}
    _tap(device, row["limit_node"])
    time.sleep(1.5)
    for idx, want in ((0, want_h), (1, want_m)):
        for _ in range(60):
            _, pick = _picker_inputs(device)
            if len(pick) < 2:
                return {"success": False, "error": "timer dialog pickers not found"}
            cur = _value(pick[idx])
            if cur == want:
                break
            _step(device, pick[idx], 1 if want > cur else -1)
        else:
            return {"success": False, "error": "could not reach the requested time"}
    ok = next((n for n in visible_nodes(device) if n["id"] == "android:id/button1"), None)
    if ok is None:
        return {"success": False, "error": "OK button missing"}
    _tap(device, ok)
    time.sleep(2)
    return {"success": True}


def delete_timer(device, params, context):
    app = str(params["app"])
    row = next((r for r in _collect_rows(device, app) if r["app"].lower() == app.lower()), None)
    if row is None:
        return {"success": False, "error": f"{app!r} not in the dashboard list"}
    if row["timer"] is None:
        return {"success": True, "data": {"already_clear": True}}
    _tap(device, row["limit_node"])
    time.sleep(1.5)
    btn = next((n for n in visible_nodes(device) if n["id"] == _ID + "delete_limit_button"), None)
    if btn is None:
        return {"success": False, "error": "'Delete timer' not offered"}
    _tap(device, btn)
    time.sleep(2)
    return {"success": True}


def _expect_minutes(desc: str) -> int | None:
    h = re.search(r"(\d+)\s*(?:hours?|hr)\b", desc)
    m = re.search(r"(\d+)\s*(?:minutes?|min)\b", desc)
    if not (h or m):
        return None
    return (int(h.group(1)) * 60 if h else 0) + (int(m.group(1)) if m else 0)


# ── End-state validators: (device, context) -> bool ──────────────────────────

def today_ok(device, context) -> bool:
    return bool((context.result.get("today") or {}).get("screen_time"))


def usage_ok(device, context) -> bool:
    apps = context.result.get("apps")
    return isinstance(apps, list) and all(a["app"] for a in apps)


def timer_matches(device, context) -> bool:
    app = str(context.params["app"]).lower()
    row = next((r for r in read_app_rows(visible_nodes(device)) if r["app"].lower() == app), None)
    if row is None:
        row = next((r for r in _collect_rows(device, app) if r["app"].lower() == app), None)
    got = _expect_minutes(row["limit_node"]["desc"]) if row and row["limit_node"] else None
    context.result["timer"] = {"app": context.params["app"], "minutes": got}
    return got == int(context.params["minutes"])


def timer_cleared(device, context) -> bool:
    app = str(context.params["app"]).lower()
    row = next((r for r in _collect_rows(device, app) if r["app"].lower() == app), None)
    return row is not None and row["timer"] is None
