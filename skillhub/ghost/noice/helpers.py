"""Noice (ambient sound generator) skill helpers, no account.

Signature for python_action targets: (device, params, context) -> dict.
Validators: (device, context) -> bool.
Playback truth is the app's media session in `dumpsys media_session`
(description = preset name, state PLAYING / STOPPED).
"""
from __future__ import annotations

import re
import time

PKG = "com.github.ashutoshgngwr.noice"
_ID = PKG + ":id/"


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


def _sweep(device, context) -> bool:
    popups = context.extras.get("_skill_popup_detectors") or []
    if not popups:
        return False
    try:
        return bool(device.dismiss_popups(popups=popups, generic=False))
    except TypeError:
        return bool(device.dismiss_popups(popups=popups))


def _tap(device, node, delay=1.0):
    x1, y1, x2, y2 = node["bounds"]
    device.tap((x1 + x2) // 2, (y1 + y2) // 2, delay)


def session(device) -> dict | None:
    out = str(device.adb("shell", "dumpsys", "media_session"))
    for chunk in re.split(r"\n(?=    \S)", out):
        if f"package={PKG}" in chunk and "state=PlaybackState" in chunk:
            st = re.search(r"state=PlaybackState \{state=(\w+)\(", chunk)
            meta = re.search(r"metadata: size=\d+, description=([^,\n]*)", chunk)
            return {"state": st.group(1).lower() if st else "unknown",
                    "preset": meta.group(1).strip() if meta and meta.group(1).strip() != "null" else None}
    return None


def open_tab(device, params, context, tab: str):
    """Cold-start Noice, skip the intro once, select a bottom tab (library or presets)."""
    device.adb("shell", "am", "force-stop", PKG)
    device.adb("shell", "monkey", "-p", PKG, "-c", "android.intent.category.LAUNCHER", "1")
    for _ in range(20):
        if _sweep(device, context):
            continue
        nodes = visible_nodes(device)
        skip = next((n for n in nodes if n["id"] == _ID + "skip"), None)
        if skip:                                   # first-run AppIntro
            _tap(device, skip, 2)
            continue
        target = next((n for n in nodes if n["id"] == _ID + tab), None)
        if target:
            _tap(device, target, 1.5)
            if any(n["id"] == _ID + ("play_button" if tab == "presets" else "play") for n in visible_nodes(device)):
                return {"success": True}
        time.sleep(1)
    return {"success": False, "error": f"{tab} tab not reached"}


def open_presets(device, params, context):
    return open_tab(device, params, context, "presets")


def open_library(device, params, context):
    return open_tab(device, params, context, "library")


def _scroll_collect(device, read, limit=200) -> list:
    items: list = []
    last = None
    for _ in range(12):
        nodes = visible_nodes(device)
        page = [(n["id"], n["text"]) for n in nodes]
        if page == last:
            break
        last = page
        for item in read(nodes):
            if item not in items:
                items.append(item)
        if len(items) >= limit:
            break
        device.swipe(540, 1800, 540, 800, 400)
        time.sleep(1)
    for _ in range(4):
        device.swipe(540, 700, 540, 1900, 300)
    return items[:limit]


def _preset_rows(nodes):
    out = []
    for n in nodes:
        if n["id"] == _ID + "title" and n["text"]:
            name, _, author = n["text"].rpartition(" by @")
            out.append({"preset": n["text"], "name": name or n["text"], "author": "@" + author if name else None})
    return out


def list_presets(device, params, context):
    presets = _scroll_collect(device, _preset_rows)
    return {"success": True, "data": {"presets": presets, "count": len(presets)}}


def list_sounds(device, params, context):
    """Walk the library; a category header (all caps, no id) applies to the rows below it, across scrolls."""
    sounds: dict[str, str | None] = {}
    category = None
    last = None
    for _ in range(12):
        nodes = visible_nodes(device)
        page = [(n["id"], n["text"]) for n in nodes]
        if page == last:
            break
        last = page
        for n in nodes:
            if not n["id"] and n["text"].isupper() and n["bounds"][1] > 280:
                category = n["text"].title()
            elif n["id"] == _ID + "title" and n["text"] and n["text"] not in sounds:
                sounds[n["text"]] = category
        device.swipe(540, 1800, 540, 800, 400)
        time.sleep(1)
    listed = [{"sound": k, "category": v} for k, v in sounds.items()]
    return {"success": True, "data": {"sounds": listed, "count": len(listed)}}


def play_preset(device, params, context):
    """Tap the preset's play button, confirm the session plays it, wait `seconds`, press the player's Stop."""
    want = str(params["preset"]).strip().lower()
    seconds = max(1, min(int(params.get("seconds") or 3), 30))
    row = None
    for _ in range(8):
        nodes = visible_nodes(device)
        row = next((n for n in nodes if n["id"] == _ID + "title" and
                    (n["text"].lower() == want or n["text"].lower().split(" by @")[0] == want)), None)
        if row:
            break
        device.swipe(540, 1800, 540, 900, 400)
        time.sleep(1)
    if not row:
        return {"success": False, "error": f"no preset named {params['preset']!r}"}
    button = next((n for n in nodes if n["id"] == _ID + "play_button"
                   and abs((n["bounds"][1] + n["bounds"][3]) - (row["bounds"][1] + row["bounds"][3])) < 80), None)
    if not button:
        return {"success": False, "error": "play button for the preset not found"}
    _tap(device, button, 1.5)
    playing = None
    for _ in range(20):
        _sweep(device, context)
        s = session(device)
        if s and s["state"] == "playing" and s["preset"] == row["text"]:
            playing = s
            break
        time.sleep(1)
    if not playing:
        return {"success": False, "error": "preset did not start playing"}
    time.sleep(seconds)
    stop = next((n for n in visible_nodes(device) if n["id"] == _ID + "stop"), None)
    if stop:
        _tap(device, stop, 1)
    else:
        device.adb("shell", "input", "keyevent", "KEYCODE_MEDIA_STOP")
    context.result["played"] = row["text"]
    context.result["seconds"] = seconds
    return {"success": True}


def stop_playback(device, params, context):
    s = session(device)
    if s and s["state"] == "playing":
        device.adb("shell", "input", "keyevent", "KEYCODE_MEDIA_STOP")
    return {"success": True, "data": {"was_playing": bool(s and s["state"] == "playing"),
                                      "preset": s["preset"] if s else None}}


def _wait_stopped(device, timeout_s=10.0) -> bool:
    deadline = time.monotonic() + timeout_s   # Noice fades out for a few seconds before STOPPED
    while time.monotonic() < deadline:
        s = session(device)
        if s is None or s["state"] in ("stopped", "none", "paused"):
            return True
        time.sleep(1)
    return False


# ── End-state validators: (device, context) -> bool ──────────────────────────

def presets_listed(device, context) -> bool:
    presets = context.result.get("presets") or []
    return bool(presets) and all(p.get("preset") for p in presets)


def sounds_listed(device, context) -> bool:
    sounds = context.result.get("sounds") or []
    return bool(sounds) and all(s.get("sound") for s in sounds)


def played_then_stopped(device, context) -> bool:
    return bool(context.result.get("played")) and _wait_stopped(device)


def stopped(device, context) -> bool:
    return _wait_stopped(device)
