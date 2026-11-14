"""python_action targets for the TikTok skill (v2 schema).

Each function has the signature:
    fn(device, params: dict, context: RunContext) -> ActionResult

- `device` is the Device wrapper (adb, dump_xml, tap, wait_for, etc.).
- `params` is the current action's params dict (interpolated {name} values resolved).
- `context` is the shared run context — pre_hooks can write to it, later steps read.

These helpers are safety-scoped to user's-own-account actions:
- scraping the LOGGED-IN handle (not other users)
- listing accounts on the DEVICE (not remote user enumeration)
- uploading the user's OWN video (not automating engagement with others' content)
"""
from __future__ import annotations

import hashlib
import re
import subprocess
import time
from pathlib import Path
from typing import Optional

from gitd.skills.base import ActionResult

TIKTOK_PKG = "com.zhiliaoapp.musically"

# Bottom-nav coordinates on 1080x2400 (empirically verified 2026-08-30 on ROG <serial> w/ TT 44.3.3).
# Adaptable: resolve via a11y content-desc first, coords are the fallback for the profile-header
# hit-area which has no stable id.
BOTTOM_NAV_Y = 2214
PROFILE_TAB_X = 972
INBOX_TAB_X = 756
HOME_TAB_X = 108

# Profile-header display-name center (opens account switcher). No stable id.
DISPLAY_NAME_TAP_X = 540
DISPLAY_NAME_TAP_Y = 440

# Handle regex — TikTok handles: letters, digits, `.`, `_`, 2-30 chars.
_HANDLE_RE = re.compile(r"@([a-zA-Z0-9_.][a-zA-Z0-9_.]{1,29})")


# ───────────────────────────────────────────────────────────────────────────
# Profile-header scrapers
# ───────────────────────────────────────────────────────────────────────────

def scrape_active_handle(device, params, context) -> ActionResult:
    """Read the currently-active TT handle from the profile header.

    Assumes we're already on the profile page (open_my_profile ran first via run_skill).
    Stores context.result['handle'] = 'your_handle' (no @ prefix).
    """
    xml = device.dump_xml()
    matches = _HANDLE_RE.findall(xml)
    if not matches:
        return ActionResult(success=False, error="No @handle found in profile header a11y tree")

    # Profile header handle is the FIRST @xxx in the dump — display-name comes before it
    # but the handle text node lives higher in read-order than any other @-mention.
    handle = matches[0]
    context.result["handle"] = handle
    return ActionResult(success=True, data={"handle": handle})


def scrape_profile_stats(device, params, context) -> ActionResult:
    """Scrape follower / following / likes + display-name from profile header.

    Layout (verified 2026-08-30):
      row 1: <avatar> <display_name ▼>  <Edit-button>
      row 2:            @<handle>
      row 3: <N Following> | <N Followers> | <N Likes>
      row 4: <Add bio | bio>
    """
    xml = device.dump_xml()

    # Handle
    handle_matches = _HANDLE_RE.findall(xml)
    handle = handle_matches[0] if handle_matches else None

    # Display name — the first text= sibling BEFORE the handle. Heuristic: it's the text
    # inside the clickable header that isn't "Edit" or a stat label.
    #   Empirically on 44.3.3 the display name appears as text="my god" style.
    #   We take the text node whose y-center is above the handle's y-center.
    handle_bounds = _find_text_bounds(xml, f"@{handle}") if handle else None
    display_name = None
    if handle_bounds:
        display_name = _find_display_name_above(xml, handle_bounds)

    # Stats — following / followers / likes counts sit as text nodes above the labels.
    # We look for text values that are pure numeric (possibly with K/M suffixes) near
    # the labels "Following", "Followers", "Likes".
    stats = _extract_stats(xml)
    stats["handle"] = handle
    stats["display_name"] = display_name

    # Drafts count if visible ("Drafts: 9")
    m = re.search(r'text="Drafts:\s*(\d+)"', xml)
    if m:
        stats["drafts"] = int(m.group(1))

    context.result["stats"] = stats
    return ActionResult(success=True, data={"stats": stats})


def _find_text_bounds(xml: str, target: str) -> Optional[dict]:
    """Return {x1,y1,x2,y2} for the first text= node matching `target` exactly."""
    pat = re.compile(rf'text="{re.escape(target)}"[^>]*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"')
    m = pat.search(xml)
    if not m:
        return None
    return {"x1": int(m.group(1)), "y1": int(m.group(2)), "x2": int(m.group(3)), "y2": int(m.group(4))}


def _find_display_name_above(xml: str, handle_bounds: dict) -> Optional[str]:
    """Find the text= that is directly above the handle bounds (display name).

    Display name node is clickable AND positioned just above the handle.
    Note: XML attribute order varies — clickable may come BEFORE text. Iterate all
    nodes rather than requiring a fixed attribute order.
    """
    handle_y = handle_bounds["y1"]
    candidates = []
    # Find all <node ...> with a text= and check clickable + bounds
    for m in re.finditer(r'<node[^>]*/>', xml):
        node = m.group(0)
        if 'clickable="true"' not in node:
            continue
        tm = re.search(r'text="([^"]{2,50})"', node)
        if not tm:
            continue
        text = tm.group(1)
        if text in {"Edit", "Add bio", "TikTok Studio", "Following", "Followers", "Likes"}:
            continue
        if text.startswith("@") or text.startswith("+ "):
            continue
        bm = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', node)
        if not bm:
            continue
        y2 = int(bm.group(4))
        # y2 must be at or above the handle (with tolerance for overlap)
        if y2 < handle_y + 20 and y2 > handle_y - 200:
            candidates.append((abs(handle_y - y2), text))
    if not candidates:
        return None
    candidates.sort()
    return candidates[0][1]


def _extract_stats(xml: str) -> dict:
    """Extract following/followers/likes count triples from the a11y tree."""
    # Find each label's y-position; the count is the numeric text node above it.
    stats = {"following": None, "followers": None, "likes": None}
    label_positions = {}
    for label in ("Following", "Followers", "Likes"):
        b = _find_text_bounds(xml, label)
        if b:
            label_positions[label.lower()] = b

    for label, b in label_positions.items():
        # Number text node has y-center ABOVE the label's y-center, x-centers aligned.
        # Some TT versions overlap the number's bottom with the label's top, so use
        # y-center comparison (not strict bottom-below-top).
        l_yc = (b["y1"] + b["y2"]) // 2
        l_xc = (b["x1"] + b["x2"]) // 2
        for m in re.finditer(r'text="([0-9]+(?:\.[0-9])?[KM]?)"[^>]*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml):
            num = m.group(1)
            n_y1 = int(m.group(3))
            n_y2 = int(m.group(5))
            n_x1 = int(m.group(2))
            n_x2 = int(m.group(4))
            n_xc = (n_x1 + n_x2) // 2
            n_yc = (n_y1 + n_y2) // 2
            # Number's y-center is above label's y-center by 20-120px; x-centers within 80px
            if l_yc - 120 < n_yc < l_yc - 10 and abs(n_xc - l_xc) < 80:
                stats[label] = _parse_count(num)
                break
    return stats


def _parse_count(s: str) -> int:
    """'1.2K' → 1200, '3M' → 3_000_000, '62' → 62."""
    s = s.strip()
    m = re.match(r"^([0-9.]+)([KM]?)$", s)
    if not m:
        return int(s.replace(",", "")) if s.replace(",", "").isdigit() else 0
    val = float(m.group(1))
    unit = m.group(2)
    if unit == "K":
        return int(val * 1_000)
    if unit == "M":
        return int(val * 1_000_000)
    return int(val)


# ───────────────────────────────────────────────────────────────────────────
# Inbox badge
# ───────────────────────────────────────────────────────────────────────────

def scrape_inbox_badge(device, params, context) -> ActionResult:
    """Read the unread-count badge overlaying the bottom-nav Inbox icon.

    The badge is either:
      - an image with content-desc like "Inbox, 4 unread"
      - a small red TextView near the Inbox icon with the number

    Both parsers tried; whichever finds it wins. Returns 0 if no badge.
    """
    xml = device.dump_xml()

    # Approach 1: content-desc on Inbox tab includes count
    m = re.search(r'content-desc="Inbox[^"]*?(\d+)\s+(?:unread|new)', xml, re.IGNORECASE)
    if m:
        count = int(m.group(1))
        context.result["unread_count"] = count
        return ActionResult(success=True, data={"unread_count": count})

    # Approach 2: numeric TextView near the Inbox tab bounds (x=648-864, y=2154-2274)
    for m in re.finditer(r'text="(\d+)"[^>]*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml):
        num = int(m.group(1))
        x1, y1 = int(m.group(2)), int(m.group(3))
        x2, y2 = int(m.group(4)), int(m.group(5))
        # Badge sits at roughly the top-right of the Inbox tab area
        if 640 < x1 < 900 and 2100 < y1 < 2220 and 1 <= num <= 99:
            context.result["unread_count"] = num
            return ActionResult(success=True, data={"unread_count": num})

    # No badge → 0 unread
    context.result["unread_count"] = 0
    return ActionResult(success=True, data={"unread_count": 0})


# ───────────────────────────────────────────────────────────────────────────
# Account switcher
# ───────────────────────────────────────────────────────────────────────────

def tap_display_name_for_switcher(device, params, context) -> ActionResult:
    """Tap the profile-header display-name area to open the account-switcher drawer.

    No stable id — using empirical coords (540, 440) on 1080x2400. Falls back to
    tapping the first clickable text= that isn't Edit/Add-bio/stats.
    """
    xml = device.dump_xml()
    # Try to locate display name node dynamically (survives future UI shifts)
    for m in re.finditer(
        r'text="([^"]{2,50})"[^>]*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"[^>]*?clickable="true"', xml
    ):
        text = m.group(1)
        y1 = int(m.group(3))
        y2 = int(m.group(5))
        # Display-name row is typically at y ∈ [400, 470]
        if 380 < y1 < 480 and text not in {"Edit", "Add bio", "Following", "Followers", "Likes", "TikTok Studio"}:
            cx = (int(m.group(2)) + int(m.group(4))) // 2
            cy = (y1 + y2) // 2
            device.tap(cx, cy)
            time.sleep(1.5)
            return ActionResult(success=True, data={"tapped": text, "x": cx, "y": cy})

    # Fallback: empirical coords
    device.tap(DISPLAY_NAME_TAP_X, DISPLAY_NAME_TAP_Y)
    time.sleep(1.5)
    return ActionResult(success=True, data={"tapped": "<empirical-coords>", "x": DISPLAY_NAME_TAP_X, "y": DISPLAY_NAME_TAP_Y})


def scrape_switcher_accounts(device, params, context) -> ActionResult:
    """Scrape all logged-in TT handles from the open account-switcher drawer.

    Precondition: drawer must be open (text="Switch account" visible).
    Returns context.result['accounts'] = [{handle, is_active, bounds}, ...].
    """
    xml = device.dump_xml()
    if "Switch account" not in xml:
        return ActionResult(
            success=False,
            error="Switch account drawer not visible — did tap_display_name_for_switcher fire?"
        )

    # Handle rows: text=<handle> without @ prefix (drawer strips @), one per logged-in acc.
    # Selected acc has selected="true".
    accounts = []
    seen = set()
    # Accept any text 2-30 chars (some accounts show display-name-style with spaces).
    # Structural filter (y-range, drawer context, dedup) does the heavy lifting.
    for m in re.finditer(
        r'<node[^>]*text="([a-zA-Z0-9_. ]{2,30})"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"[^>]*/>',
        xml,
    ):
        text = m.group(1).strip()
        # Filter UI chrome
        if text in {"Switch account", "Add account", "Switch", "account"} or text.startswith("Add "):
            continue
        y1 = int(m.group(3))
        if not (900 < y1 < 2100):
            continue
        key = (text, y1 // 50)
        if key in seen:
            continue
        seen.add(key)
        node = m.group(0)
        is_active = 'selected="true"' in node
        bounds = {
            "x1": int(m.group(2)), "y1": y1,
            "x2": int(m.group(4)), "y2": int(m.group(5)),
        }
        accounts.append({"handle": text, "is_active": is_active, "bounds": bounds})

    # Sort by y (visual order)
    accounts.sort(key=lambda a: a["bounds"]["y1"])
    context.result["accounts"] = accounts
    return ActionResult(success=True, data={"accounts": accounts, "count": len(accounts)})


def tap_account_by_handle(device, params, context) -> ActionResult:
    """Tap the switcher row for the target `handle` param (opens the account)."""
    target = params.get("handle", "").lstrip("@").strip()
    if not target:
        return ActionResult(success=False, error="handle param required")

    # Re-scrape to get fresh bounds (drawer state may have shifted)
    res = scrape_switcher_accounts(device, params, context)
    if not res.success:
        return res

    accounts = context.result.get("accounts", [])
    match = next((a for a in accounts if a["handle"] == target), None)
    if not match:
        available = ", ".join(a["handle"] for a in accounts)
        return ActionResult(
            success=False,
            error=f"Handle @{target} not logged in on this device. Available: {available}",
        )

    if match["is_active"]:
        # Already active — no-op success. Close the drawer.
        device.back() if hasattr(device, "back") else device.adb("shell", "input", "keyevent", "KEYCODE_BACK")
        time.sleep(1)
        return ActionResult(success=True, data={"already_active": True, "handle": target})

    b = match["bounds"]
    # Tap row center — use screen-midpoint x (540) rather than text-node bounds
    # (text bounds are narrower than the clickable row area).
    cx = 540
    cy = (b["y1"] + b["y2"]) // 2
    device.tap(cx, cy)
    time.sleep(3)
    return ActionResult(success=True, data={"switched_to": target, "x": cx, "y": cy})


# ───────────────────────────────────────────────────────────────────────────
# Upload flow helpers
# ───────────────────────────────────────────────────────────────────────────

def prepare_video_with_tts(device, params, context) -> ActionResult:
    """Pre-hook: if inject_tts, generate TTS audio + overlay on video.

    Modifies params['video_path'] in place to point at the prepared file.
    No-op if inject_tts is False.
    """
    if not params.get("inject_tts"):
        return ActionResult(success=True, data={"skipped": True})

    try:
        from gitd.tools.tts import generate_tts, inject_audio_to_video
    except ImportError:
        return ActionResult(
            success=False,
            error="gitd.tools.tts not available — required for inject_tts=true",
        )

    video_path = Path(params["video_path"])
    caption = params.get("caption", "")
    if not caption:
        return ActionResult(success=False, error="caption empty — cannot generate TTS")

    tts_wav = generate_tts(caption)
    prepared = inject_audio_to_video(video_path, tts_wav)
    params["video_path"] = str(prepared)
    return ActionResult(success=True, data={"prepared_path": str(prepared)})


def push_and_scan_video(device, params, context) -> ActionResult:
    """Push local video to /sdcard, trigger media scan, capture content-URI media_id.

    - If video_path is on-device (starts with /sdcard, /storage), skip push.
    - Populates context.media_id for the launch_intent step.
    """
    vp = params["video_path"]
    if vp.startswith(("/sdcard/", "/storage/")):
        # On-device path — no push needed
        on_device_path = vp
    else:
        src = Path(vp)
        if not src.exists():
            return ActionResult(success=False, error=f"Video not found locally: {src}")
        on_device_path = "/sdcard/DCIM/upload.mp4"
        device.adb("push", str(src), on_device_path)

    # Media scan
    device.adb("shell", "am", "broadcast", "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE",
               "-d", f"file://{on_device_path}")
    time.sleep(2)

    # MediaStore normalizes /sdcard/ to /storage/emulated/0/ in _data column.
    # Query all + local grep instead of --where (Device.adb argv-quoting mismatches shell).
    basename = on_device_path.rsplit("/", 1)[-1]
    out = device.adb("shell", "content", "query", "--uri", "content://media/external/video/media")
    # Find the row whose _display_name matches; extract _id from same row
    for line in out.split("\n"):
        if f"_display_name={basename}" in line:
            m = re.search(r"_id=(\d+)", line)
            if m:
                context.media_id = m.group(1)
                return ActionResult(success=True, data={"media_id": context.media_id, "path": on_device_path})
    return ActionResult(
        success=False,
        error=f"Media scan did not register {basename} (searched {len(out.splitlines())} rows)",
    )


def append_hashtags_to_description(device, params, context) -> ActionResult:
    """After Next → metadata screen: tap description field, append '#tag1 #tag2 ...'."""
    tags = params.get("hashtags") or []
    if not tags:
        return ActionResult(success=True, data={"skipped": True})

    # Description field is beneath the caption preview at top of the metadata screen.
    # Tap the # Hashtags chip to focus + move cursor into description.
    import re
    xml = device.dump_xml()
    m = re.search(r'text="#?\s*Hashtags"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml)
    if not m:
        # Fallback: tap on Add description area near top of screen
        return ActionResult(success=False, error="Hashtags chip not found on metadata screen")
    cx = (int(m.group(1)) + int(m.group(3))) // 2
    cy = (int(m.group(2)) + int(m.group(4))) // 2
    device.tap(cx, cy)
    time.sleep(0.5)
    # Tapping the "# Hashtags" chip already inserted a "#", so the first tag goes bare.
    # Trailing space ends the last hashtag so TikTok closes its suggestion panel; one
    # BACK afterwards (in skill.yaml) then only hides the keyboard.
    hashtag_str = " ".join(f"#{t.lstrip('#')}" for t in tags)[1:] + " "
    # adb shell input text uses %s for spaces; quote-safe path uses input_text_arg
    from gitd.bots.common.adb import input_text_arg
    device.adb("shell", "input", "text", input_text_arg(hashtag_str))
    time.sleep(0.5)
    return ActionResult(success=True, data={"appended": hashtag_str})


def toggle_brand_disclosure(device, params, context) -> ActionResult:
    """Ad-authorization → tap the 'Brand' toggle switch.

    The switch id varies across TT versions — try id, then text fallback.
    Retried by the outer skill.yaml retry: wrapper.
    """
    xml = device.dump_xml()
    if "Brand" not in xml:
        return ActionResult(success=False, error="Brand toggle not found on ad-auth screen")
    device.tap_text("Brand")
    time.sleep(1)
    # Verify toggle changed state — re-dump and check aria-selected/switch-checked
    return ActionResult(success=True)


def tap_action_mode_button(device, params, context) -> ActionResult:
    """Tap 'Post' or 'Drafts' at the bottom of the metadata screen.

    The metadata page autoplays the cover preview, so uiautomator dumps fail or stall
    often. Try one dump and tap by bounds; otherwise blind-tap the calibrated bottom-bar
    coords (1080x2400: Drafts left, Post right). Screenshot before a blind tap for calibration.
    """
    import re
    mode = params.get("action_mode", "draft")
    labels = ("Post",) if mode == "post" else ("Drafts", "Draft")
    blind = (800, 2186) if mode == "post" else (279, 2186)   # measured on ROG 1080x2400, TT 44.3.3
    try:
        xml = device.dump_xml() or ""
    except Exception:
        xml = ""
    for label in labels:
        m = re.search(r'text="%s"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"' % label, xml)
        if m:
            cx = (int(m.group(1)) + int(m.group(3))) // 2
            cy = (int(m.group(2)) + int(m.group(4))) // 2
            device.tap(cx, cy)
            time.sleep(4)
            return ActionResult(success=True, data={"mode": mode, "via": "dump", "xy": [cx, cy]})
    try:
        device.adb("shell", "screencap", "-p", "/sdcard/ghost_pre_mode_tap.png")
    except Exception:
        pass
    device.tap(*blind)
    time.sleep(4)
    return ActionResult(success=True, data={"mode": mode, "via": "blind", "xy": list(blind)})


