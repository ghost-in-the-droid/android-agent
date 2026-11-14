"""Chrome skill helpers: page info, Google consent wall, find-in-page count.

Signature for python_action targets: (device, params, context) -> dict.
Validators: (device, context) -> bool.
"""
from __future__ import annotations

import re
import time
import shlex
from gitd.bots.common.adb import input_text_arg

_ID = "com.android.chrome:id/"


def visible_nodes(device) -> list[dict]:
    """Flatten the current screen into on-screen nodes: text, desc, id, cls, bounds."""
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
                            "id": n.get("resourceId") or "", "cls": n.get("className") or "", "bounds": box})
            stack.extend(reversed(n.get("children") or []))
        return out
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"text": a.get("text", ""), "desc": a.get("content-desc", ""),
                        "id": a.get("resource-id", ""), "cls": a.get("class", ""), "bounds": tuple(nums)})
    return out


def incognito_markers(nodes):
    """Chrome-owned resources, rather than webpage text claiming Incognito."""
    markers = {"location_bar_incognito_badge", "new_tab_incognito_title", "new_tab_incognito_icon"}
    return [n["id"] for n in nodes if n["id"] in {_ID + name for name in markers}]


def wait_for_incognito(device, params, context):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        evidence = incognito_markers(visible_nodes(device))
        if evidence:
            return {"success": True, "data": {"incognito": True, "mode_evidence": evidence}}
        time.sleep(.25)
    return {"success": False, "error": "Chrome did not expose a verified Incognito indicator"}


def page_info(device) -> dict:
    nodes = visible_nodes(device)
    url = next((n["text"] for n in nodes if n["id"] == _ID + "url_bar"), "")
    title = next((n["text"] for n in nodes if n["cls"] == "android.webkit.WebView" and n["text"]), "")
    incognito = bool(incognito_markers(nodes))
    if not incognito and url and title:
        incognito = private_tab_grid_evidence(device, nodes, url)
    return {"url": url, "title": title, "incognito": incognito}


def private_tab_grid_evidence(device, initial, expected_url):
    """Current Chrome hides its private badge on loaded pages. Inspect its
    native current-model tab grid, then return to the same page; never switch models.
    """
    button = next((n for n in initial if n['id'] == _ID + 'tab_switcher_button'), None)
    if button is None or not chrome_foreground(device):
        return False
    x1,y1,x2,y2 = button['bounds']
    device.tap((x1+x2)//2, (y1+y2)//2)
    grid_seen = False
    private = False
    deadline = time.monotonic() + 8
    try:
        while time.monotonic() < deadline:
            current = visible_nodes(device)
            if any(n['id'] == _ID + 'tab_switcher_view_holder' for n in current):
                grid_seen = True
                private = any(n['id'] == _ID + 'search_box_text'
                              and n['text'] == 'Search your Incognito tabs' for n in current)
                break
            time.sleep(.25)
    finally:
        if grid_seen:
            if not chrome_foreground(device):
                raise ValueError('Chrome lost focus while inspecting its native tab model')
            device.back()
    if not grid_seen:
        raise ValueError('Native Chrome tab-model evidence was unavailable')
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        current = visible_nodes(device)
        if any(n['id'] == _ID + 'url_bar' and n['text'] == expected_url for n in current):
            return private
        time.sleep(.25)
    raise ValueError('Chrome did not return to the same page after native mode readback')


def read_page_info(device, params, context):
    """Wait briefly for the page title, then return url (as shown, scheme elided), title, incognito."""
    info = page_info(device)
    for _ in range(10):
        if info["title"]:
            break
        time.sleep(0.5)
        info = page_info(device)
    return {"success": bool(info["url"]), "error": "no url bar on screen", "data": info}


def focus_address_bar(device, params, context):
    """Tap whichever address field is really on screen: the New Tab Page search box or the toolbar url_bar.

    On the New Tab Page the toolbar url_bar is in the tree with inverted bounds,
    so a plain tap_element on its id lands on empty space.
    """
    for _ in range(10):
        nodes = visible_nodes(device)
        field = next((n for n in nodes if n["id"] in (_ID + "search_box_text", _ID + "url_bar")), None)
        if field:
            if not chrome_foreground(device):
                return {"success": False, "error": "Chrome lost focus before address-field tap"}
            x1, y1, x2, y2 = field["bounds"]
            device.tap((x1 + x2) // 2, (y1 + y2) // 2)
            time.sleep(1)
            return {"success": True}
        time.sleep(0.5)
    return {"success": False, "error": "no address field on screen"}


_CONSENT_IDS = {"W0wltc", "L2AGLb", "xe7COe"}   # Reject all / Accept all / wall heading (language independent)


def consent_wall_present(device) -> bool:
    return bool(re.search(r'resource-id="(%s)"' % "|".join(_CONSENT_IDS), device.dump_xml()))


def reject_google_consent(device, params, context):
    """If Google's cookie wall shows up (it can take a few seconds), scroll to 'Reject all' (id W0wltc) and tap it."""
    for _ in range(8):
        if consent_wall_present(device):
            break
        time.sleep(0.75)
    else:
        return {"success": True, "data": {"consent": "none"}}
    for _ in range(6):
        button = next((n for n in visible_nodes(device) if n["id"] == "W0wltc"), None)
        if button:
            x1, y1, x2, y2 = button["bounds"]
            device.tap((x1 + x2) // 2, (y1 + y2) // 2)
            time.sleep(2.5)
            return {"success": True, "data": {"consent": "rejected"}}
        device.swipe(540, 1800, 540, 500, 300)
        time.sleep(0.8)
    return {"success": False, "error": "consent wall present but Reject all not found"}


def read_find_count(device, params, context):
    """Poll the find bar until its 'i/N' status is stable for two reads, return N."""
    last = None
    for _ in range(12):
        status = next((n["text"] for n in visible_nodes(device) if n["id"] == _ID + "find_status"), "")
        if re.match(r"\d+/\d+$", status) and status == last:
            break
        last = status
        time.sleep(0.5)
    m = re.match(r"(\d+)/(\d+)$", last or "")
    if not m:
        return {"success": False, "error": f"find status not readable: {last!r}"}
    return {"success": True, "data": {"matches": int(m.group(2)), "find_status": last}}


# ── End-state validators: (device, context) -> bool ──────────────────────────

def url_matches(device, context) -> bool:
    want = str(context.params["url"]).split("://", 1)[-1].removeprefix("www.").rstrip("/").lower()
    host = want.split("/", 1)[0]
    info = page_info(device)
    context.result.update(info)
    shown = info["url"].lower().removeprefix("www.")
    return bool(shown) and re.split(r"[/\?#]", shown, maxsplit=1)[0] == host and (not context.params.get("incognito") or info["incognito"])


def search_done(device, context) -> bool:
    info = page_info(device)
    context.result.update(info)
    query = str(context.params["query"]).lower()
    if consent_wall_present(device):
        return False
    return query in info["title"].lower() or query.split()[0] in info["url"].lower()


def incognito_open(device, context) -> bool:
    info = page_info(device)
    context.result.update(info)
    return info["incognito"]


def page_info_ok(device, context) -> bool:
    return bool(context.result.get("url"))


def find_count_ok(device, context) -> bool:
    return isinstance(context.result.get("matches"), int)


def chrome_foreground(device):
    raw = device.adb("shell", "dumpsys", "window")
    focus = next((line for line in raw.splitlines() if "mCurrentFocus=" in line), "")
    return "com.android.chrome/" in focus


def resume_chrome(device, params, context):
    # Preserve an already visible tab model, including Incognito. Launch only when backgrounded.
    if not chrome_foreground(device):
        device.adb("shell", "monkey", "-p", "com.android.chrome", "1")
    return {"success": True}


def open_private_tab(device, params, context):
    # The exported launcher enters private mode without exposing a normal/account tab first.
    device.adb("shell", "am", "start", "-W", "-n",
               "com.android.chrome/org.chromium.chrome.browser.incognito.IncognitoTabLauncher")
    return wait_for_incognito(device, params, context)


def open_url(device, params, context):
    url = str(params["url"])
    if len(url) > 2048 or not url.isascii() or any(ord(c) <= 32 for c in url):
        return {"success": False, "error": "Use a printable ASCII HTTP(S) URL without whitespace"}
    if url[:8] != "https://" and url[:7] != "http://":
        return {"success": False, "error": "Only HTTP(S) URLs are supported"}
    private = bool(params.get("incognito", False))
    if private:
        result = open_private_tab(device, params, context)
        if not result.get("success"):
            return result
        result = focus_address_bar(device, params, context)
        if not result.get("success"):
            return result
        if not chrome_foreground(device):
            return {"success": False, "error": "Chrome lost focus before URL input"}
        field = next((n for n in visible_nodes(device) if n["id"] == _ID + "url_bar"), None)
        if field is None:
            return {"success": False, "error": "Focused URL field is missing"}
        length = min(len(field["text"]), 2048)
        device.adb("shell", "input", "keyevent", "KEYCODE_MOVE_END", *(["KEYCODE_DEL"] * max(1, length)))
        device.adb("shell", "input", "text", input_text_arg(url))
        device.press_enter()
    else:
        device.adb("shell", shlex.join(["am", "start", "-W", "-a", "android.intent.action.VIEW", "-d", url, "-p", "com.android.chrome"]))
    deadline = time.monotonic() + 25
    host = url.split("://", 1)[1].split("/", 1)[0].lower().removeprefix("www.")
    while time.monotonic() < deadline:
        info = page_info(device)
        shown = info["url"].lower().removeprefix("www.")
        if re.split(r"[/\?#]", shown, maxsplit=1)[0] == host and info["title"] and (not private or info["incognito"]):
            return {"success": True, "data": info}
        time.sleep(.3)
    return {"success": False, "error": "Requested URL/private mode did not read back"}
