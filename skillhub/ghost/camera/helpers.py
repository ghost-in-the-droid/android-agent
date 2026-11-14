"""AOSP Camera (com.android.camera2) skill helpers.

Signature for python_action targets: (device, params, context) -> dict.
Validators: (device, context) -> bool.
Captures are verified through MediaStore (content query), not the UI: a new
row with date_added at or after the action's start time must appear.
"""
from __future__ import annotations

import re
import time

from gitd.skills.engine.dispatch import skill_dismiss_popups

PKG = "com.android.camera2"
_ID = PKG + ":id/"
_STORES = {"photo": "content://media/external/images/media", "video": "content://media/external/video/media"}


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


def _node(device, rid: str):
    return next((n for n in visible_nodes(device) if n["id"] == _ID + rid), None)


def _tap(device, node, delay=1.0) -> None:
    x1, y1, x2, y2 = node["bounds"]
    device.tap((x1 + x2) // 2, (y1 + y2) // 2, delay)


def _device_now(device) -> int:
    return int(str(device.adb("shell", "date", "+%s")).strip())


def newest_media(device, kind: str) -> dict | None:
    out = str(device.adb("shell", "content", "query", "--uri", _STORES[kind], "--projection", "_data:date_added:_size",
                         "--sort", "'date_added DESC'"))
    m = re.search(r"_data=(\S+), date_added=(\d+), _size=(\d+)", out)
    return {"path": m.group(1), "date_added": int(m.group(2)), "size": int(m.group(3))} if m else None


def _location_tag_checked(device) -> bool:
    tree = device.dump_portal_json() if hasattr(device, "dump_portal_json") else None
    stack = [tree] if isinstance(tree, dict) else list(tree or [])
    while stack:
        n = stack.pop()
        if n.get("resourceId") == _ID + "check_box":
            return bool(n.get("isChecked"))
        stack.extend(n.get("children") or [])
    return True


def mark_start(device, params, context):
    """Remember the device clock so the validator only accepts media created by this run."""
    context.extras["capture_start"] = _device_now(device) - 1
    return {"success": True}


def ready_camera(device, params, context):
    """Wait for the viewfinder (shutter button); select the requested lens and countdown via the Options row."""
    popups = context.extras.get("_skill_popup_detectors") or []
    for _ in range(20):
        if _node(device, "shutter_button"):
            break
        if popups and skill_dismiss_popups(device, context):    # permission dialogs during first run; no generic taps
            time.sleep(1)
            continue
        box, nxt = _node(device, "check_box"), _node(device, "confirm_button")
        if nxt:                       # first run: "Remember photo locations?" -> untick, NEXT
            if box and _location_tag_checked(device):
                _tap(device, box)
            _tap(device, nxt, 2)
            continue
        time.sleep(1)
    else:
        return {"success": False, "error": "camera viewfinder not shown"}
    camera = params.get("camera") or "back"
    timer = int(params.get("timer_s") or 0)
    toggle = _node(device, "mode_options_toggle")
    if toggle and not _node(device, "camera_toggle_button"):
        _tap(device, toggle)
    for _ in range(3):
        lens = _node(device, "camera_toggle_button")
        if lens is None or lens["desc"].lower().startswith(camera):
            break
        _tap(device, lens, 2.5)       # switching lenses restarts the preview
    want = "off" if timer == 0 else f"{timer} second"
    for _ in range(3):
        countdown = _node(device, "countdown_toggle_button")
        if countdown is None or want in countdown["desc"].lower():
            break
        _tap(device, countdown)
    lens = _node(device, "camera_toggle_button")
    context.result["camera"] = camera if lens is None else lens["desc"].split()[0].lower()
    context.result["timer_s"] = timer
    return {"success": True}


def _wait_new(device, kind: str, since: int, timeout_s: float) -> dict | None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        media = newest_media(device, kind)
        if media and media["date_added"] >= since and media["size"] > 0:
            return media
        time.sleep(1)
    return None


def shoot_photo(device, params, context):
    shutter = _node(device, "shutter_button")
    if shutter is None:
        return {"success": False, "error": "no shutter button"}
    _tap(device, shutter)
    media = _wait_new(device, "photo", context.extras["capture_start"], 15 + int(params.get("timer_s") or 0))
    if not media:
        return {"success": False, "error": "no new photo in MediaStore"}
    return {"success": True, "data": {"photo": media}}


def record_clip(device, params, context):
    seconds = max(1, min(int(params.get("seconds") or 3), 60))
    shutter = _node(device, "shutter_button")
    if shutter is None:
        return {"success": False, "error": "no shutter button"}
    _tap(device, shutter, 0.2)
    time.sleep(seconds)
    _tap(device, shutter, 0.5)
    media = _wait_new(device, "video", context.extras["capture_start"], 20)
    if not media:
        return {"success": False, "error": "no new video in MediaStore"}
    media["seconds"] = seconds
    return {"success": True, "data": {"video": media}}


def last_capture(device, params, context):
    photo, video = newest_media(device, "photo"), newest_media(device, "video")
    newest = max((m for m in (photo, video) if m), key=lambda m: m["date_added"], default=None)
    return {"success": True, "data": {"last_photo": photo, "last_video": video,
                                      "last_capture": newest}}


# ── End-state validators: (device, context) -> bool ──────────────────────────

def new_photo_saved(device, context) -> bool:
    media = newest_media(device, "photo")
    return bool(media and media["date_added"] >= context.extras.get("capture_start", 1 << 62) and media["size"] > 0)


def new_video_saved(device, context) -> bool:
    media = newest_media(device, "video")
    return bool(media and media["date_added"] >= context.extras.get("capture_start", 1 << 62) and media["size"] > 0)


def front_camera_used(device, context) -> bool:
    return context.result.get("camera") == "front" and new_photo_saved(device, context)


def capture_read(device, context) -> bool:
    return "last_capture" in context.result
