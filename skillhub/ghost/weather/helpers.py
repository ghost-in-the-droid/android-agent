"""Breezy Weather skill helpers. python_action: (device, params, context) -> dict;
validators: (device, context) -> bool. Only on-screen nodes are read.

Locations are added by name search only (Open-Meteo / GeoNames); the skill never
uses "Add current location" or GPS. Taps in the top band (where heads-up
notifications appear) go through `guarded_tap`."""
from __future__ import annotations

import html
import re
import shlex
import time

_ID = "org.breezyweather:id/"
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
            out.append({"text": html.unescape(a.get("text", "")), "desc": html.unescape(a.get("content-desc", "")),
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


def _wait(device, pred, timeout=20.0, step=1.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        nodes = visible_nodes(device)
        if pred(nodes):
            return nodes
        time.sleep(step)
    return None


def _is_add(n) -> bool:
    """'Add a new location' is a FAB description with saved locations, button text when empty."""
    return "Add a new location" in (n["desc"], n["text"])


def read_locations(nodes) -> list[dict]:
    out = []
    for t in (n for n in nodes if n["id"] == _ID + "title1"):
        sub = next((n["text"] for n in nodes if n["id"] == _ID + "title2" and 0 <= n["bounds"][1] - t["bounds"][3] <= 10), "")
        out.append({"name": t["text"], "condition": sub, "node": t})
    return out


def country_of(row):
    """The search provider displays country first, followed by region/county."""
    return row.get("region", "").split(",", 1)[0].strip()


def select_location(rows, params):
    """Never guess among same-name locations or fall back after a failed filter."""
    country = str(params.get("country") or "").strip().casefold()
    region = str(params.get("region") or "").strip().casefold()
    legacy = str(params.get("match") or "").strip().casefold()
    candidates = list({(r["name"], r["region"]): r for r in rows}.values())
    matches = [r for r in candidates
               if (not country or country_of(r).casefold() == country)
               and (not region or region in r["region"].casefold())
               and (not legacy or legacy in (r["name"] + " " + r["region"]).casefold())]
    if len(matches) != 1:
        reason = "Ambiguous location" if len(matches) > 1 else "No matching location"
        return None, reason + "; specify country and region. No location was saved."
    return matches[0], None


def search_rows(nodes):
    """Pair adjacent name/region lines without assuming a toolbar pixel height."""
    texts = [n for n in nodes if n["text"] and "Open-Meteo" not in n["text"]]
    texts.sort(key=lambda n: (n["bounds"][1], n["bounds"][0]))
    rows = []
    for n, nxt in zip(texts, texts[1:]):
        if (0 <= nxt["bounds"][1] - n["bounds"][3] <= 10
                and abs(nxt["bounds"][0] - n["bounds"][0]) <= 5):
            rows.append({"name": n["text"], "region": nxt["text"], "node": n})
    return rows


# ── python_action targets ───────────────────────────────────────────────────

def open_location_list(device, params, context):
    """Fresh launch; from the weather view tap 'Location list' to reach Locations."""
    device.adb("shell", "am", "force-stop", "org.breezyweather")
    device.adb("shell", "monkey", "-p", "org.breezyweather", "-c", "android.intent.category.LAUNCHER", "1")
    nodes = _wait(device, lambda ns: any(n["desc"] == "Location list" or _is_add(n) for n in ns), 30)
    if nodes is None:
        return {"success": False, "error": "Breezy Weather did not open"}
    btn = next((n for n in nodes if n["desc"] == "Location list"), None)
    if btn is not None:
        if not guarded_tap(device, btn):
            return {"success": False, "error": "heads-up notification over the toolbar; not tapping"}
        if _wait(device, lambda ns: any(_is_add(n) for n in ns), 15) is None:
            return {"success": False, "error": "location list did not open"}
    return {"success": True}


def add_location(device, params, context):
    nodes = visible_nodes(device)
    add = next((n for n in nodes if _is_add(n)), None)
    if add is None:
        return {"success": False, "error": "'Add a new location' not on screen"}
    guarded_tap(device, add)
    if _wait(device, lambda ns: any("Search for a location" in n["text"] for n in ns), 15) is None:
        return {"success": False, "error": "search screen did not open"}
    time.sleep(0.8)
    device.adb("shell", "input", "text", shlex.quote(str(params["query"]).replace(" ", "%s")))
    device.adb("shell", "input", "keyevent", "KEYCODE_ENTER")
    q = str(params["query"]).lower()
    nodes = _wait(device, lambda ns: sum(1 for n in ns if n["text"] and q.split()[0] in n["text"].lower()) >= 2, 25)
    if nodes is None:
        return {"success": False, "error": f"no search results for {params['query']!r}"}
    # Result rows: name line, then a region line ("Germany, State of Berlin, ...") just below.
    rows = search_rows(nodes)
    hit, error = select_location(rows, params)
    if hit is None:
        return {"success": False, "error": error,
                "data": {"candidates": [{"name": r["name"], "region": r["region"]} for r in rows]}}
    if not guarded_tap(device, hit["node"]):
        return {"success": False, "error": "heads-up notification over the result; not tapping"}
    # A "Weather sources" sheet confirms the default free sources.
    nodes = _wait(device, lambda ns: any(n["text"] == "Weather sources" for n in ns)
                  or any(_is_add(n) for n in ns), 25)
    if nodes and any(n["text"] == "Weather sources" for n in nodes):
        save = next((n for n in nodes if n["text"] == "Save"), None)
        if save is None:
            return {"success": False, "error": "Save missing on the sources sheet"}
        guarded_tap(device, save)
    context.result["picked"] = {"name": hit["name"], "region": hit["region"], "country": country_of(hit)}
    if _wait(device, lambda ns: any(n["id"] == _ID + "title1" for n in ns), 30) is None:
        return {"success": False, "error": "location list did not come back"}
    return {"success": True}


def list_locations(device, params, context):
    locs = [{k: v for k, v in l.items() if k != "node"} for l in read_locations(visible_nodes(device))]
    return {"success": True, "data": {"locations": locs, "count": len(locs)}}


def open_location(device, params, context):
    want = str(params["location"]).lower()
    locs = read_locations(visible_nodes(device))
    hit = next((l for l in locs if l["name"].lower() == want), None) or \
        next((l for l in locs if want in l["name"].lower()), None)
    if hit is None:
        return {"success": False, "error": f"no saved location matching {params['location']!r}; add it first"}
    if not guarded_tap(device, hit["node"]):
        return {"success": False, "error": "heads-up notification over the row; not tapping"}
    if _wait(device, lambda ns: any(n["id"] == _ID + "container_main_header_temperature_value" for n in ns), 30) is None:
        return {"success": False, "error": "weather view did not load"}
    return {"success": True}


def read_current(device, params, context):
    nodes = visible_nodes(device)
    get = lambda s, k="text": next((n[k] for n in nodes if n["id"] == _ID + s), "")
    title = next((n["text"] for n in nodes if n["bounds"][1] < 290 and n["text"] and not n["id"]), "")
    data = {"location": title,
            "condition": get("container_main_header_weather_condition_description"),
            "temperature": get("container_main_header_temperature_value"),
            "unit": get("container_main_header_temperature_unit"),
            "feels_like": get("container_main_header_feels_like"),
            "range": get("container_main_header_temperature_range"),
            "updated": get("refreshTimeText", "desc")}
    return {"success": bool(data["temperature"]), "data": {"weather": data}, "error": "temperature not on screen"}


_DAY = re.compile(r"Conditions, ([^,]+), ([^,]+), Daytime: ([^,]+), ([^,]+)")
_NIGHT = re.compile(r"Nighttime: ([^,]+), ([^,]+)")
_PRECIP = re.compile(r"Precipitation probability: (\d+)%")


def read_daily(device, params, context):
    days = []
    for n in visible_nodes(device):
        if n["id"] != _ID + "item_trend_daily":
            continue
        m = _DAY.match(n["desc"])
        if m:
            night = _NIGHT.search(n["desc"])
            precip = [int(p) for p in _PRECIP.findall(n["desc"])]
            days.append({"day": m.group(1), "date": m.group(2), "day_temp": m.group(3), "day_condition": m.group(4),
                         "precip_probability": max(precip) if precip else None,
                         "night_temp": night.group(1) if night else "", "night_condition": night.group(2) if night else ""})
    return {"success": bool(days), "data": {"daily": days}, "error": "daily forecast not on screen"}


# ── End-state validators: (device, context) -> bool ──────────────────────────

def location_listed(device, context) -> bool:
    picked = context.result.get("picked") or {}
    if not picked.get("name") or not picked.get("country"):
        return False
    # Check country against the actual selected result's region, not only its city name.
    if picked["country"].casefold() != country_of(picked).casefold():
        return False
    hit, _ = select_location([picked], context.params)
    return hit is not None and any(l["name"] == picked["name"] for l in read_locations(visible_nodes(device)))


def locations_ok(device, context) -> bool:
    return isinstance(context.result.get("locations"), list) and any(_is_add(n) for n in visible_nodes(device))


def weather_ok(device, context) -> bool:
    w = context.result.get("weather") or {}
    return bool(re.fullmatch(r"-?\d+", w.get("temperature", ""))) and bool(w.get("condition"))


def daily_ok(device, context) -> bool:
    d = context.result.get("daily") or []
    return len(d) >= 3 and all(x["day_temp"] for x in d)
