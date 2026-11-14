"""F-Droid client helpers. F-Droid 2.x is Jetpack Compose: no resource ids, so
everything keys on visible text and on-screen geometry.

python_action signature: (device, params, context) -> dict
validator signature:     (device, context) -> bool
"""
from __future__ import annotations

import html
import re
import time

TOP, BOTTOM_NAV = 300, 2240   # list area between the toolbar and the bottom navigation


def visible_nodes(device) -> list[dict]:
    """Flatten the current screen into on-screen nodes: text, desc, id, bounds, checked."""
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
                            "id": n.get("resourceId") or "", "bounds": box,
                            "checked": bool(n.get("isChecked")), "cls": n.get("className") or ""})
            stack.extend(reversed(n.get("children") or []))
        out.sort(key=lambda n: (n["bounds"][1], n["bounds"][0]))
        return out
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"text": html.unescape(a.get("text", "")), "desc": html.unescape(a.get("content-desc", "")),
                        "id": a.get("resource-id", ""), "bounds": tuple(nums),
                        "checked": a.get("checked") == "true", "cls": a.get("class", "")})
    return out



def _text_nodes(nodes):
    return [n for n in nodes if n["text"]]


def _tap(device, node):
    l, t, r, b = node["bounds"]
    device.tap((l + r) // 2, (t + b) // 2, 0.4)


def list_items(nodes, min_left=180) -> list[dict]:
    """App rows render as a title line directly above a summary/version line, both indented
    past the icon. Pair every text whose bottom touches the next text's top."""
    texts = [n for n in _text_nodes(nodes) if n["bounds"][0] >= min_left and TOP < n["bounds"][1] < BOTTOM_NAV]
    texts.sort(key=lambda n: (n["bounds"][1], n["bounds"][0]))
    items, i = [], 0
    while i < len(texts) - 1:
        a, b = texts[i], texts[i + 1]
        if abs(b["bounds"][1] - a["bounds"][3]) <= 4 and a["bounds"][0] == b["bounds"][0]:
            items.append({"name": a["text"], "detail": b["text"]})
            i += 2
        else:
            i += 1
    return items


def _collect(device, pages: int, limit: int) -> list[dict]:
    seen: dict[str, dict] = {}
    for _ in range(pages):
        before = len(seen)
        for it in list_items(visible_nodes(device)):
            seen.setdefault(it["name"], it)
        if len(seen) >= limit or (len(seen) == before and before):
            break
        device.swipe(540, 1900, 540, 900, 400)
        time.sleep(1.0)
    return list(seen.values())[:limit]


def query_field(nodes):
    return next((n for n in nodes if n.get("cls") == "android.widget.EditText"), None)


def query_matches(nodes, query):
    field = query_field(nodes)
    return field is not None and field["text"].strip().casefold() == str(query).strip().casefold()


def wait_for_catalogue(device, params, context):
    """Let a clean install finish importing its index before issuing a search.

    Searches issued during the initial import can retain their empty result
    until the query changes. Waiting on that empty Search screen is insufficient.
    """
    discover = next((n for n in visible_nodes(device) if n["text"] == "Discover"), None)
    if discover is None:
        return {"success": False, "error": "Discover tab not visible"}
    _tap(device, discover)
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        nodes = visible_nodes(device)
        body = [n["text"] for n in nodes if n["text"] and TOP < n["bounds"][1] < 2000]
        loading = any(re.search(r"fetching.*repositor|updating.*repositor|loading.*app", text, re.I) for text in body)
        if body and not loading:
            if any(re.search(r"failed|no repositories|no apps available", text, re.I) for text in body):
                return {"success": False, "error": "F-Droid catalogue unavailable; check repository update"}
            return {"success": True}
        time.sleep(.5)
    return {"success": False, "error": "Initial F-Droid catalogue import did not finish within 120s"}


def open_search_tab(device, params, context):
    """Wait for the bottom navigation after the initial catalogue recomposes."""
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        node = next((n for n in visible_nodes(device)
                     if "Search" in (n["text"], n["desc"])
                     and n["bounds"][1] > BOTTOM_NAV - 400), None)
        if node is not None:
            _tap(device, node)
            return {"success": True}
        time.sleep(.5)
    return {"success": False, "error": "Search navigation did not become ready"}


def relevant_results(rows, query):
    tokens = re.findall(r"\w{2,}", str(query).casefold())
    return bool(rows) and any(any(token in (r["name"] + " " + r["detail"]).casefold()
                                 for token in tokens) for r in rows)


def enter_query(device, params, context):
    """Focus the actual editable node, replace its contents, then verify the input."""
    from gitd.bots.common.adb import input_text_arg
    query = str(params["query"]).strip()
    if not query:
        return {"success": False, "error": "Search query must not be empty"}
    field = query_field(visible_nodes(device))
    if field is None:
        return {"success": False, "error": "Search field not visible"}
    _tap(device, field)
    # A bounded single ADB invocation clears existing text, including an old query.
    length = len(field["text"])
    if length > 300:
        return {"success": False, "error": "Existing query unexpectedly long; not appending"}
    device.adb("shell", "input", "keyevent", "KEYCODE_MOVE_END", *(["KEYCODE_DEL"] * max(1, length)))
    device.adb("shell", "input", "text", input_text_arg(query))
    deadline = time.monotonic() + 2
    while not query_matches(visible_nodes(device), query):
        if time.monotonic() >= deadline:
            return {"success": False, "error": "Search field does not match requested query; not returning stale results"}
        time.sleep(.1)
    device.adb("shell", "input", "keyevent", "KEYCODE_ENTER")
    return {"success": True}


def wait_for_results(device, params, context):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        nodes = visible_nodes(device)
        if query_matches(nodes, params["query"]) and relevant_results(list_items(nodes), params["query"]):
            return {"success": True}
        if any(n["text"] in ("No apps found", "No results") for n in nodes):
            return {"success": False, "error": "No apps found for requested query"}
        time.sleep(.5)
    return {"success": False, "error": "No matching results for requested query before timeout"}


def search_results(device, params, context):
    limit = int(params.get("limit") or 10)
    nodes = visible_nodes(device)
    if not query_matches(nodes, params["query"]):
        return {"success": False, "error": "Search field no longer matches requested query"}
    rows = [it for it in _collect(device, 3, limit + 5)]
    if not relevant_results(rows, params["query"]):
        return {"success": False, "error": "No visible result matches requested query"}
    results = [{"name": r["name"], "summary": r["detail"]} for r in rows][:limit]
    return {"success": True, "data": {"query": params["query"], "results": results, "count": len(results)}}


def app_page(device, params, context):
    nodes = _text_nodes(visible_nodes(device))
    by = next((i for i, n in enumerate(nodes) if n["text"].startswith("by ")), None)
    upd = next((n["text"] for n in nodes if n["text"].startswith("Last updated")), "")
    if by is None or not upd:
        return {"success": False, "error": "app page landmarks (author, Last updated) not found"}
    name = nodes[by - 1]["text"] if by else ""
    upd_i = next(i for i, n in enumerate(nodes) if n["text"] == upd)
    summary = nodes[upd_i + 1]["text"] if upd_i + 1 < len(nodes) else ""
    all_nodes = visible_nodes(device)
    installed = any(n["desc"] == "Installed" for n in all_nodes) or any(n["text"] == "Open" for n in all_nodes)
    size = upd[upd.rfind("(") + 1:-1] if upd.endswith(")") else ""
    return {"success": True, "data": {"package": params["package"], "name": name, "author": nodes[by]["text"][3:],
                                      "last_updated": upd.split(":", 1)[1].split("(")[0].strip(), "size": size,
                                      "summary": summary, "installed": installed}}


def installed_apps(device, params, context):
    nodes = visible_nodes(device)
    up_to_date = any(n["text"] == "All your apps are up to date" for n in nodes)
    apps = [{"name": r["name"], "version": r["detail"]} for r in _collect(device, 6, 200)]
    return {"success": True, "data": {"apps": apps, "count": len(apps), "all_up_to_date": up_to_date}}


def open_category(device, params, context):
    want = str(params["category"]).strip().lower()
    for _ in range(8):
        chip = next((n for n in visible_nodes(device) if n["text"].lower() == want and TOP < n["bounds"][1] < BOTTOM_NAV), None)
        if chip:
            _tap(device, chip)
            time.sleep(2.0)
            return {"success": True}
        device.swipe(540, 1800, 540, 900, 400)
        time.sleep(0.8)
    return {"success": False, "error": f"category {params['category']!r} not found"}


def category_apps(device, params, context):
    limit = int(params.get("limit") or 10)
    rows = _collect(device, 4, limit)
    return {"success": True, "data": {"category": params["category"],
                                      "apps": [{"name": r["name"], "summary": r["detail"]} for r in rows],
                                      "count": len(rows)}}


# ── End-state validators: (device, context) -> bool ──────────────────────────

def has_results(device, context) -> bool:
    rows = [{"name": r["name"], "detail": r["summary"]} for r in context.result.get("results", [])]
    return (query_matches(visible_nodes(device), context.params["query"])
            and context.result.get("query") == context.params["query"]
            and relevant_results(rows, context.params["query"]))


def page_matches(device, context) -> bool:
    return bool(context.result.get("name")) and bool(context.result.get("author"))


def installed_listed(device, context) -> bool:
    return any(a["name"] == "F-Droid" for a in context.result.get("apps", []))


def category_listed(device, context) -> bool:
    title = str(context.params["category"]).lower()
    on_title = any(n["text"].lower() == title and n["bounds"][1] < TOP for n in visible_nodes(device))
    return on_title and bool(context.result.get("apps"))
