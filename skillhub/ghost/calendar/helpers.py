"""Fossify Calendar skill helpers: local (never synced) calendar, no account.

Signature for python_action targets: (device, params, context) -> dict.
Validators: (device, context) -> bool.
"""
from __future__ import annotations

import datetime as dt
import re
import time

PKG = "org.fossify.calendar"
_ID = PKG + ":id/"
_MONTHS = ["JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE", "JULY", "AUGUST",
           "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER"]


def visible_nodes(device) -> list[dict]:
    """Flatten the current screen into on-screen nodes: text, desc, id, bounds (top to bottom)."""
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
    else:
        for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
            a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
            nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
            if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
                out.append({"text": a.get("text", ""), "desc": a.get("content-desc", ""),
                            "id": a.get("resource-id", ""), "bounds": tuple(nums)})
    return sorted(out, key=lambda n: (n["bounds"][1], n["bounds"][0]))


def _find(nodes, rid=None, text=None):
    """rid matches the app's own id or the framework dialog id (android:id/button1)."""
    ids = (None,) if rid is None else (_ID + rid, "android:id/" + rid)
    return next((n for n in nodes if (rid is None or n["id"] in ids) and (text is None or n["text"] == text)), None)


def _tap(device, node, delay=1.0):
    x1, y1, x2, y2 = node["bounds"]
    device.tap((x1 + x2) // 2, (y1 + y2) // 2, delay)


def _sweep(device, context) -> bool:
    """Run only this skill's popup detectors (no generic Cancel/Skip fallback)."""
    popups = context.extras.get("_skill_popup_detectors") or []
    if not popups:
        return False
    try:
        return bool(device.dismiss_popups(popups=popups, generic=False))
    except TypeError:
        return bool(device.dismiss_popups(popups=popups))


def _quote(value) -> str:
    return "'" + str(value).replace("'", "'\\''") + "'"


def _top_activity(device) -> str:
    out = str(device.adb("shell", "dumpsys", "activity", "activities"))
    m = re.search(r"topResumedActivity=\S+ \S+ (\S+)", out)
    return m.group(1) if m else ""


def _today(device) -> dt.date:
    return dt.date.fromisoformat(str(device.adb("shell", "date", "+%F")).strip())


# ── navigation ───────────────────────────────────────────────────────────────

def open_event_list(device, params, context):
    """Cold-start Calendar (drops any half-typed search) and switch to the 'Simple event list' view."""
    device.adb("shell", "am", "force-stop", PKG)
    device.adb("shell", "monkey", "-p", PKG, "-c", "android.intent.category.LAUNCHER", "1")
    for _ in range(20):
        nodes = visible_nodes(device)
        if _sweep(device, context):
            continue
        if _find(nodes, "calendar_fab") and (_find(nodes, "event_section_title") or _find(nodes, "calendar_empty_list_placeholder")):
            return {"success": True}
        change = _find(nodes, "change_view")
        if change:
            _tap(device, change, 1.5)
            item = _find(visible_nodes(device), text="Simple event list")
            if item:
                _tap(device, item, 2)
                continue
        time.sleep(1)
    nodes = visible_nodes(device)
    return {"success": bool(_find(nodes, "calendar_fab")), "error": "event list view not reached"}


def read_event_list(device, max_items: int = 50) -> list[dict]:
    """Walk the simple list (scrolling), turning section headers into ISO dates."""
    today = _today(device)
    events: list[dict] = []
    seen = set()
    month, day, last = None, None, None
    for _ in range(8):
        nodes = visible_nodes(device)
        page = [(n["id"], n["text"]) for n in nodes]
        if page == last:
            break
        last = page
        for n in nodes:
            if n["id"] == _ID + "event_section_title":
                if n["text"].upper() in _MONTHS:
                    month = _MONTHS.index(n["text"].upper()) + 1
                elif re.match(r"^\d{1,2} ", n["text"]):
                    day = int(n["text"].split()[0])
            elif n["id"] == _ID + "event_item_title" and month and day:
                year = today.year + (1 if month < today.month else 0)
                time_node = next((o for o in nodes if o["id"] == _ID + "event_item_time"
                                  and 0 <= o["bounds"][1] - n["bounds"][3] < 30), None)
                key = (year, month, day, n["text"], time_node["text"] if time_node else "")
                if key not in seen:
                    seen.add(key)
                    events.append({"date": dt.date(year, month, day).isoformat(), "title": n["text"],
                                   "time": key[4] or "All-day"})
        if len(events) >= max_items:
            break
        device.swipe(540, 1900, 540, 700, 400)
        time.sleep(1)
    return events[:max_items]


# ── actions ──────────────────────────────────────────────────────────────────

def create_event(device, params, context):
    """Open the editor through the public INSERT intent (prefilled), then press Save."""
    start = dt.datetime.strptime(f"{params['date']} {params['start_time']}", "%Y-%m-%d %H:%M")
    epoch = int(str(device.adb("shell", "date", "-d", _quote(start.strftime("%Y-%m-%d %H:%M")), "+%s")).strip())
    end = epoch + int(params.get("duration_min") or 60) * 60
    device.adb("shell", "am", "force-stop", PKG)   # INSERT extras are only read by a fresh editor
    cmd = ["shell", "am", "start", "-a", "android.intent.action.INSERT", "-d", "content://com.android.calendar/events",
           "-p", PKG, "--es", "title", _quote(params["title"]), "--el", "beginTime", str(epoch * 1000),
           "--el", "endTime", str(end * 1000)]
    for key, extra in (("location", "eventLocation"), ("description", "description")):
        if params.get(key):
            cmd += ["--es", extra, _quote(params[key])]
    device.adb(*cmd)
    saved = False
    for _ in range(25):
        nodes = visible_nodes(device)
        if _sweep(device, context):
            continue
        ok = _find(nodes, "button1")
        if ok and ok["text"] in ("OK", "Grant Permission"):     # reminder disclaimer / notification explainer
            _tap(device, ok, 1.5)
            continue
        save = _find(nodes, "save")
        title = _find(nodes, "event_title")
        if save and title and title["text"] == params["title"] and not saved:
            _tap(device, save, 1.5)
            saved = True
            continue
        if saved and not save and not ok and "EventActivity" not in _top_activity(device) \
                and "permissioncontroller" not in _top_activity(device):
            context.extras["event_epoch"] = epoch
            return {"success": True, "data": {"event": {"title": params["title"], "date": params["date"],
                                                        "start_time": params["start_time"],
                                                        "duration_min": int(params.get("duration_min") or 60)}}}
        time.sleep(1)
    return {"success": False, "error": "event editor did not close after Save"}


def list_events(device, params, context):
    events = read_event_list(device, int(params.get("max_items") or 50))
    days = params.get("days")
    if days:
        last = _today(device) + dt.timedelta(days=int(days) - 1)
        events = [e for e in events if e["date"] <= last.isoformat()]
    return {"success": True, "data": {"events": events, "count": len(events)}}


def get_event(device, params, context):
    """Search by title, open the first hit, read the editor fields, leave without saving."""
    nodes = visible_nodes(device)
    search = _find(nodes, "top_toolbar_search")
    if not search:
        return {"success": False, "error": "search box not found"}
    _tap(device, search)
    device.adb("shell", "input", "text", _quote(str(params["title"]).replace(" ", "%s")))
    time.sleep(2)
    hit = None
    for _ in range(8):
        hit = _find(visible_nodes(device), "event_item_title", params["title"])
        if hit:
            break
        time.sleep(1)
    if not hit:
        return {"success": False, "error": f"no event titled {params['title']!r}"}
    _tap(device, hit, 2)
    fields = {}
    for _ in range(8):
        nodes = visible_nodes(device)
        if _find(nodes, "event_title"):
            for key, rid in (("title", "event_title"), ("location", "event_location"), ("description", "event_description"),
                             ("start_date", "event_start_date"), ("start_time", "event_start_time"),
                             ("end_date", "event_end_date"), ("end_time", "event_end_time"),
                             ("reminder", "event_reminder_1"), ("repetition", "event_repetition"),
                             ("calendar", "event_calendar_title")):
                node = _find(nodes, rid)
                fields[key] = node["text"] if node else None
            for key, placeholder in (("location", "Location"), ("description", "Description")):
                if fields.get(key) == placeholder:
                    fields[key] = ""
            break
        time.sleep(1)
    device.adb("shell", "input", "keyevent", "KEYCODE_BACK")   # unchanged event: closes without a discard prompt
    time.sleep(1)
    if not fields:
        return {"success": False, "error": "event editor did not open"}
    return {"success": True, "data": {"event": fields}}


# ── End-state validators: (device, context) -> bool ──────────────────────────

def event_listed(device, context) -> bool:
    open_event_list(device, {}, context)
    events = read_event_list(device, 100)
    p = context.params
    return any(e["title"] == p["title"] and e["date"] == p["date"] for e in events)


def events_read(device, context) -> bool:
    return isinstance(context.result.get("events"), list)


def event_read(device, context) -> bool:
    event = context.result.get("event") or {}
    return event.get("title") == context.params["title"] and bool(event.get("start_date"))
