"""Google Maps skill helpers: fire encoded VIEW intents, read place cards, result lists, route summaries.

Signature for python_action targets: (device, params, context) -> dict.
Validators: (device, context) -> bool.
Maps renders with Compose, so most nodes have no resource id; readers key on
content-desc prefixes ("Directions to ...") and on text shapes ("4.7 stars (190)").
"""
from __future__ import annotations

import re
import time

from gitd.skills.engine.dispatch import skill_dismiss_popups

PKG = "com.google.android.apps.maps"
_SAFE = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_.~,")
_RATING = re.compile(r"^(\d(?:\.\d)?) stars? \(([\d,.]+)\)$")
_DURATION = re.compile(r"^\d+\s*(?:min|hr|h|d)\b")


def encode(value) -> str:
    """Percent-encode for a URI query value (space -> +); no urllib so the skill stays network-free."""
    out = []
    for ch in str(value):
        if ch in _SAFE:
            out.append(ch)
        elif ch == " ":
            out.append("+")
        else:
            out.extend(f"%{b:02X}" for b in ch.encode("utf-8"))
    return "".join(out)


def view(device, uri: str) -> None:
    device.adb("shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", f"'{uri}'", "-p", PKG)


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
        return out
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"text": a.get("text", ""), "desc": a.get("content-desc", ""),
                        "id": a.get("resource-id", ""), "bounds": tuple(nums)})
    return out


def _details(lines: list[str]) -> dict:
    out = {"rating": None, "reviews": None, "lines": []}
    for line in lines:
        m = _RATING.match(line)
        if m and out["rating"] is None:
            out["rating"], out["reviews"] = float(m.group(1)), int(m.group(2).replace(",", "").replace(".", ""))
        elif line.strip(" ·") and not line.startswith("Ad ·"):
            out["lines"].append(line)
    return out


def read_place_card(device) -> dict | None:
    """Place card: name node (text == desc) above the 'Directions to ...' button, detail lines between."""
    nodes = visible_nodes(device)
    button = next((n for n in nodes if n["desc"].startswith("Directions to ") and not n["text"]), None)
    if button is None:
        return None
    top = button["bounds"][1]
    above = [n for n in nodes if n["bounds"][3] <= top + 5 and n["text"] and n["bounds"][1] > 300]
    name_node = next((n for n in sorted(above, key=lambda n: n["bounds"][1]) if n["text"] == n["desc"]), None)
    if name_node is None:
        return None
    lines = [n["text"] for n in sorted(above, key=lambda n: n["bounds"][1]) if n["bounds"][1] > name_node["bounds"][1]]
    d = _details(lines)
    return {"name": name_node["text"], "rating": d["rating"], "reviews": d["reviews"], "details": d["lines"]}


def read_result_list(device) -> list[dict]:
    """Search result list: each result has an id=title node; detail lines follow until the next title."""
    nodes = sorted(visible_nodes(device), key=lambda n: (n["bounds"][1], n["bounds"][0]))
    titles = [n for n in nodes if n["id"] == "title" and n["text"]]
    results = []
    for i, t in enumerate(titles):
        end = titles[i + 1]["bounds"][1] if i + 1 < len(titles) else 2400
        lines = [n["text"] for n in nodes if t["bounds"][3] - 5 <= n["bounds"][1] < end
                 and n["text"] and not n["desc"] and n is not t and n["bounds"][0] < 200]
        d = _details(lines[:4])
        results.append({"name": t["text"], "rating": d["rating"], "reviews": d["reviews"], "details": d["lines"][:3]})
    return results


def _wait(fn, timeout_s=15.0, device=None, context=None):
    """Poll fn until truthy; between polls run the skill's popup detectors (first-run upsell can appear late)."""
    deadline = time.monotonic() + timeout_s
    popups = (context.extras.get("_skill_popup_detectors") if context is not None else None) or []
    while True:
        value = fn()
        if value or time.monotonic() > deadline:
            return value
        if device is not None and popups:
            skill_dismiss_popups(device, context)  # declared popups only, no generic Cancel/Skip taps
        time.sleep(0.8)


def _signature(device) -> tuple:
    return tuple(sorted((n["text"], n["desc"]) for n in visible_nodes(device)))


def _omnibox_shows(device, query: str) -> bool:
    return any(n["id"].endswith("search_omnibox_text_box") and n["desc"].strip().lower() == query.strip().lower()
               for n in visible_nodes(device))


def _fire(device, uri: str) -> tuple:
    """Fire a VIEW intent; return the pre-intent screen signature so readers can wait for a fresh screen."""
    before = _signature(device)
    view(device, uri)
    time.sleep(2)
    return before


def _place_or_first(device):
    return read_place_card(device) or (read_result_list(device) or [None])[0]


def search_place(device, params, context):
    query = str(params["query"])
    _fire(device, "geo:0,0?q=" + encode(query))
    place = _wait(lambda: _omnibox_shows(device, query) and _place_or_first(device), 15, device, context)
    if not place:
        return {"success": False, "error": "no place card or result list"}
    return {"success": True, "data": {"place": place}}


def list_places(device, params, context):
    query = str(params["query"])
    _fire(device, "geo:0,0?q=" + encode(query))
    limit = int(params.get("max_results") or 5)
    first = _wait(lambda: _omnibox_shows(device, query) and (read_result_list(device) or read_place_card(device)),
                  15, device, context)
    if isinstance(first, dict):     # a single exact match opens a card instead of a list
        return {"success": True, "data": {"places": [first], "count": 1}}
    seen: dict[str, dict] = {}
    for _ in range(6):
        for r in read_result_list(device):
            seen.setdefault(r["name"], r)
        if len(seen) >= limit:
            break
        device.swipe(540, 2000, 540, 900, 400)
        time.sleep(1.5)
    places = list(seen.values())[:limit]
    return {"success": bool(places), "error": "no results", "data": {"places": places, "count": len(places)}}


def show_location(device, params, context):
    lat, lng = float(params["lat"]), float(params["lng"])
    before = _fire(device, f"geo:{lat},{lng}?q={lat},{lng}")
    place = _wait(lambda: _signature(device) != before and read_place_card(device), 15, device, context)
    if not place:
        return {"success": False, "error": "no place card for coordinates"}
    return {"success": True, "data": {"place": place, "lat": lat, "lng": lng}}


def read_transit(nodes) -> dict | None:
    """Transit lists trip cards (id directions_trip_card); the first card is the recommended trip."""
    card = next((n for n in nodes if n["id"].endswith("directions_trip_card")), None)
    if card is None:
        return None
    x1, y1, x2, y2 = card["bounds"]
    inside = [n for n in nodes if y1 <= n["bounds"][1] < y2 and n is not card]
    duration = next((n["text"] for n in inside if _DURATION.match(n["text"]) and n["desc"].endswith("minutes")
                     or _DURATION.match(n["text"]) and "hour" in n["desc"]), None)
    legs = next((n["desc"].replace("\u200b", "") for n in inside if ", then " in n["desc"] or n["desc"].startswith("\u200b")), None)
    times = next((n["text"].replace("\u202f", " ") for n in inside if "–" in n["text"]), None)
    fare = next((n["text"] for n in inside if re.search(r"[€$£¥₹]|\b[A-Z]{3}\s?\d", n["text"])), None)
    return {"mode": "transit", "duration": duration, "distance": None, "via": legs, "times": times, "fare": fare,
            "summary": ", ".join(x for x in (legs, duration, times) if x)}


def read_route(device) -> dict | None:
    nodes = visible_nodes(device)
    if any(n["desc"] == "transit directions" for n in nodes):
        return read_transit(nodes)
    summary = next((n for n in nodes if "Activate to open step list" in n["desc"]
                    or re.match(r"^(driving|walking|bicycling|cycling|transit)\.", n["desc"])), None)
    if summary is None:
        return None
    inside = [n for n in nodes if summary["bounds"][1] <= n["bounds"][1] < summary["bounds"][3] and n["text"]]
    duration = next((n["text"] for n in inside if _DURATION.match(n["text"])), None)
    distance = next((n["text"].strip("()").replace("\xa0", " ") for n in inside if re.match(r"^\([\d.,]+\s", n["text"])), None)
    via = next((n["text"] for n in inside if n["text"].startswith("via ")), None)
    return {"mode": summary["desc"].split(".")[0], "duration": duration, "distance": distance, "via": via,
            "summary": summary["desc"].replace("\xa0", " ").replace(". Activate to open step list", "")}


def get_directions(device, params, context):
    mode = params.get("mode") or "driving"
    uri = ("https://www.google.com/maps/dir/?api=1&origin=" + encode(params["origin"]) + "&destination="
           + encode(params["destination"]) + "&travelmode=" + mode)
    _fire(device, uri)
    want = {"bicycling": ("bicycling", "cycling")}.get(mode, (mode,))
    ends = (str(params["origin"]).split()[0].lower(), str(params["destination"]).split()[0].lower())

    def fresh_route():
        route = read_route(device)
        texts = " ".join(n["text"].lower() for n in visible_nodes(device) if n["bounds"][1] < 400)
        return route if route and route["mode"] in want and all(e in texts for e in ends) else None

    route = _wait(fresh_route, 25, device, context)
    if not route or not route["duration"]:
        return {"success": False, "error": "no route summary"}
    return {"success": True, "data": {"route": route}}


# ── End-state validators: (device, context) -> bool ──────────────────────────

def place_found(device, context) -> bool:
    place = context.result.get("place") or {}
    return bool(place.get("name"))


def places_listed(device, context) -> bool:
    places = context.result.get("places") or []
    return bool(places) and all(p.get("name") for p in places)


def route_shown(device, context) -> bool:
    route = read_route(device)
    want = context.params.get("mode") or "driving"
    alias = {"bicycling": ("bicycling", "cycling")}.get(want, (want,))
    return bool(route and route["duration"] and route["mode"] in alias)
