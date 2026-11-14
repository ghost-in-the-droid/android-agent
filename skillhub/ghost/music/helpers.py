"""Fossify Music Player skill helpers: on-device audio library, no account.

Signature for python_action targets: (device, params, context) -> dict.
Validators: (device, context) -> bool.
Playback state is read from `dumpsys media_session` (the app's media3 session),
which is exact and works with the screen in any state.
"""
from __future__ import annotations

import re
import time

PKG = "org.fossify.musicplayer"
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


def _unescape(text: str) -> str:
    return text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")


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
    """The app's media session: state, title, artist, album, position_ms."""
    out = str(device.adb("shell", "dumpsys", "media_session"))
    block = None
    for chunk in re.split(r"\n(?=    \S)", out):
        if f"package={PKG}" in chunk and "state=PlaybackState" in chunk:
            block = chunk
            break
    if block is None:
        return None
    st = re.search(r"state=PlaybackState \{state=(\w+)\(\d+\), position=(-?\d+)", block)
    meta = re.search(r"metadata: size=\d+, description=(.*)", block)
    parts = [p.strip() for p in meta.group(1).split(",")] if meta else []
    return {"state": st.group(1).lower() if st else "unknown", "position_ms": int(st.group(2)) if st else 0,
            "title": parts[0] if parts else None, "artist": parts[1] if len(parts) > 1 else None,
            "album": parts[2] if len(parts) > 2 else None}


def open_tracks(device, params, context):
    """Launch the player (granting audio access) and select the Tracks tab."""
    device.adb("shell", "monkey", "-p", PKG, "-c", "android.intent.category.LAUNCHER", "1")
    for _ in range(20):
        if _sweep(device, context):
            continue
        nodes = visible_nodes(device)
        if any(n["id"] == _ID + "activity_track_title" for n in nodes):   # full-screen player is open
            device.adb("shell", "input", "keyevent", "KEYCODE_BACK")
            time.sleep(1)
            continue
        tab = next((n for n in nodes if n["id"] == _ID + "tab_item_label" and n["text"] == "Tracks"), None)
        if tab:
            _tap(device, tab, 1.5)
            if any(n["id"] in (_ID + "track_title", _ID + "track_frame") for n in visible_nodes(device)):
                return {"success": True}
        time.sleep(1)
    return {"success": False, "error": "Tracks tab not reached (no audio files, or permission denied)"}


def read_tracks(device, limit=200) -> list[dict]:
    tracks: list[dict] = []
    last = None
    for _ in range(10):
        nodes = visible_nodes(device)
        page = [(n["id"], n["text"]) for n in nodes]
        if page == last:
            break
        last = page
        titles = [n for n in nodes if n["id"] == _ID + "track_title"]
        for t in titles:
            row = [n for n in nodes if abs(n["bounds"][1] - t["bounds"][1]) < 120 and n is not t]
            info = next((_unescape(n["text"]) for n in row if n["id"] == _ID + "track_info"), "")
            dur = next((n["text"] for n in row if n["id"] == _ID + "track_duration"), "")
            artist, _, album = info.partition(" • ")
            entry = {"title": t["text"], "artist": artist, "album": album, "duration": dur}
            if entry not in tracks:
                tracks.append(entry)
        if len(tracks) >= limit:
            break
        device.swipe(540, 1900, 540, 700, 400)
        time.sleep(1)
    return tracks[:limit]


def list_tracks(device, params, context):
    tracks = read_tracks(device, int(params.get("max_items") or 200))
    return {"success": True, "data": {"tracks": tracks, "count": len(tracks)}}


def play_track(device, params, context):
    """Tap the track by exact title, let it play `seconds`, then pause with the media key."""
    title = str(params["title"])
    seconds = max(1, min(int(params.get("seconds") or 3), 30))
    target = None
    for _ in range(10):
        target = next((n for n in visible_nodes(device) if n["id"] == _ID + "track_title" and n["text"] == title), None)
        if target:
            break
        device.swipe(540, 1900, 540, 900, 400)
        time.sleep(1)
    if not target:
        return {"success": False, "error": f"no track titled {title!r}"}
    _tap(device, target, 1.5)
    started = None
    for _ in range(15):
        _sweep(device, context)        # notification permission is asked on first playback
        s = session(device)
        if s and s["state"] == "playing" and s["title"] == title:
            started = s
            break
        time.sleep(1)
    if not started:
        return {"success": False, "error": "playback did not start"}
    time.sleep(seconds)
    device.adb("shell", "input", "keyevent", "KEYCODE_MEDIA_PAUSE")
    time.sleep(1.5)
    return {"success": True, "data": {"played": title, "seconds": seconds, "session": session(device)}}


def get_now_playing(device, params, context):
    s = session(device)
    if not s:
        return {"success": True, "data": {"now_playing": None, "state": "none"}}
    return {"success": True, "data": {"now_playing": s, "state": s["state"]}}


def pause(device, params, context):
    device.adb("shell", "input", "keyevent", "KEYCODE_MEDIA_PAUSE")
    time.sleep(1.5)
    return {"success": True, "data": {"session": session(device)}}


# ── End-state validators: (device, context) -> bool ──────────────────────────

def tracks_listed(device, context) -> bool:
    tracks = context.result.get("tracks")
    return isinstance(tracks, list) and all(t.get("title") for t in tracks)


def played_and_paused(device, context) -> bool:
    s = session(device)
    return bool(s and s["title"] == context.params["title"] and s["state"] == "paused" and s["position_ms"] > 0)


def now_playing_read(device, context) -> bool:
    return "state" in context.result


def not_playing(device, context) -> bool:
    s = session(device)
    return s is None or s["state"] != "playing"
