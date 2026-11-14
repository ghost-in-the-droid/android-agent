"""YouTube mobile web (m.youtube.com in Chrome) skill helpers, no account.

The preinstalled YouTube app on a never-updated device is often too old for
YouTube's servers (search returns "problem with the server [400]") and cannot
update without a Play account, so this skill drives m.youtube.com in Chrome.

Signature for python_action targets: (device, params, context) -> dict.
Validators: (device, context) -> bool.
"""
from __future__ import annotations

import re
import time

CHROME = "com.android.chrome"
_SAFE = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_.~")
_META = re.compile(r" ((?:[\d.,]+\s?[KMB]?|No) views?\b.*|[\d.,]+\s?(?:thousand |million )?watching\b.*)$")
_SHORT = re.compile(r"^(.*), ([\d.,]+ (?:thousand |million |billion )?views?), (.+?), (.+?) - play Short$")
_VID = re.compile(r"watch\?v=([\w-]{11})")


def encode(value) -> str:
    out = []
    for ch in str(value):
        if ch in _SAFE:
            out.append(ch)
        elif ch == " ":
            out.append("+")
        else:
            out.extend(f"%{b:02X}" for b in ch.encode("utf-8"))
    return "".join(out)


def visible_nodes(device) -> list[dict]:
    """Flatten the current screen into on-screen nodes: text, desc, id, bounds (sorted top to bottom)."""
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


def open_url(device, url: str) -> None:
    # A fixed application_id makes Chrome reuse one tab instead of opening a new tab per call.
    device.adb("shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", f"'{url}'", "-p", CHROME,
               "--es", "com.android.browser.application_id", "ghost.youtube_web")


def url_bar(device) -> str:
    return next((n["text"] for n in visible_nodes(device) if n["id"] == CHROME + ":id/url_bar"), "")


def reject_consent(device) -> bool:
    """YouTube's EU cookie wall ('Before you continue to YouTube'): scroll to the reject button and tap it."""
    for _ in range(6):
        nodes = visible_nodes(device)
        button = next((n for n in nodes if n["text"] in ("Reject all", "Reject the use of cookies and other data for the purposes described")), None)
        if button:
            x1, y1, x2, y2 = button["bounds"]
            device.tap((x1 + x2) // 2, (y1 + y2) // 2)
            time.sleep(3)
            return True
        if not any("Before you continue" in n["text"] or "Reject all" in n["text"] for n in nodes):
            return False
        device.swipe(540, 1900, 540, 600, 300)
        time.sleep(1)
    return False


def _load(device, url: str, ready, timeout_s: float = 45.0):
    """Open url in Chrome; reject the cookie wall when it shows; poll ready() until truthy.

    Google's consent endpoint sometimes hangs or answers 502 after 'Reject all';
    when the page is still on consent.youtube.com 12 s after the reject, reload
    the target URL (the choice is usually stored by then, or the wall comes back
    and is rejected again).
    """
    open_url(device, url)
    time.sleep(3)
    deadline = time.monotonic() + timeout_s
    rejected_at = None
    while time.monotonic() < deadline:
        if reject_consent(device):     # the wall can overlay a page that already looks rendered
            rejected_at = time.monotonic()
            continue
        value = ready()
        if value:
            return value
        on_consent = url_bar(device).startswith("consent.")
        errored = on_consent and any("an error" in n["text"] for n in visible_nodes(device))
        if errored or (on_consent and rejected_at and time.monotonic() - rejected_at > 12):
            open_url(device, url)
            rejected_at = None
            time.sleep(3)
            continue
        time.sleep(1)
    return None


def parse_entries(nodes, channel: str | None = None) -> list[dict]:
    """Video rows render as '<title> by <channel> <meta>' text nodes; ids come from nearby 'watch?v=' descs."""
    entries = []
    current = channel
    prev_bottom = 0
    for i, n in enumerate(nodes):
        if n["text"].startswith("Go to channel "):
            current = n["text"][len("Go to channel "):]
            continue
        short = _SHORT.match(n["text"]) if not n["desc"] else None
        if short:
            entries.append({"title": short.group(1), "channel": short.group(3), "meta": f"{short.group(2)}, {short.group(4)}",
                            "video_id": None, "kind": "short"})
            continue
        if not n["text"] or n["desc"] or not _META.search(n["text"]):
            continue
        text = n["text"]
        if current and f" by {current} " in text:
            title, rest = text.split(f" by {current} ", 1)
            who = current
        else:
            m = re.match(r"^(.*) by (.+?)" + _META.pattern, text)
            if not m:
                continue
            title, who, rest = m.group(1), m.group(2), m.group(3)
        # The thumbnail (desc 'watch?v=<id>...') sits above the row; never look past the previous row.
        top, bottom = max(prev_bottom, n["bounds"][1] - 700), n["bounds"][3] + 60
        cands = [(abs(o["bounds"][1] - n["bounds"][1]), m.group(1)) for o in nodes
                 if top <= o["bounds"][1] <= bottom for m in [_VID.search(o["desc"])] if m]
        vid = min(cands)[1] if cands else None
        prev_bottom = n["bounds"][3]
        entries.append({"title": title.strip(), "channel": who, "meta": rest.strip(), "video_id": vid,
                        "kind": "live" if "watching" in rest else "video"})
        current = channel
    return entries


def _collect(device, limit: int, channel: str | None = None, shorts: bool = True) -> list[dict]:
    seen: dict[str, dict] = {}
    last = None
    for _ in range(10):
        nodes = visible_nodes(device)
        page = [(n["text"], n["desc"]) for n in nodes]
        if page == last:            # scrolling no longer moves: end of the list
            break
        last = page
        for e in parse_entries(nodes, channel):
            if e["kind"] == "short" and not shorts:
                continue
            key = e["title"] + "|" + e["channel"]
            if key not in seen or (not seen[key]["video_id"] and e["video_id"]):
                seen[key] = e
        if len(seen) >= limit:
            break
        device.swipe(540, 1900, 540, 800, 400)
        time.sleep(1.5)
    return list(seen.values())[:limit]


def search_videos(device, params, context):
    query = str(params["query"])
    limit = int(params.get("max_results") or 10)
    url = "https://m.youtube.com/results?search_query=" + encode(query)
    ok = _load(device, url, lambda: "results?search_query=" + encode(query) in url_bar(device)
               and any(n["desc"] == "About these results" or n["text"] == "Search filters" for n in visible_nodes(device)))
    if not ok:
        return {"success": False, "error": "no search results rendered"}
    videos = _collect(device, limit, shorts=bool(params.get("include_shorts")))
    return {"success": True, "data": {"query": query, "videos": videos, "count": len(videos)}}


def get_video_info(device, params, context):
    vid = str(params["video_id"]).strip()
    if not re.fullmatch(r"[\w-]{11}", vid):
        return {"success": False, "error": "video_id must be the 11-character YouTube id"}

    def header():
        if vid not in url_bar(device):
            return None
        nodes = visible_nodes(device)
        player = next((n for n in nodes if n["id"] == "movie_player"), None)
        chan = next((n for n in nodes if n["desc"].endswith("Go to channel.")), None)
        if not player or not chan:
            return None
        lines = [n["text"] for n in nodes if player["bounds"][3] - 5 <= n["bounds"][1] < chan["bounds"][1]
                 and n["text"] and not n["desc"] and n["text"] not in ("Show more", "more")]
        return (lines, chan) if lines else None

    found = _load(device, "https://m.youtube.com/watch?v=" + vid, header)
    device.adb("shell", "input", "keyevent", "KEYCODE_MEDIA_PAUSE")   # keep the software-GL emulator idle
    if not found:
        return {"success": False, "error": "watch page did not render"}
    lines, chan = found
    name, _, subs = chan["desc"].removesuffix(". Go to channel.").partition(", ")
    if " @" in lines[0]:          # compact header: '<title> @handle 562 likes 449 watching now more'
        title, _, tail = lines[0].partition(" @")
        handle = "@" + tail.split(" ", 1)[0]
        stats = tail.split(" ", 1)[1].removesuffix(" more") if " " in tail else ""
    else:                         # expanded header: title, 'Uploaded by x.', likes, views, age as separate nodes
        title, handle = lines[0], None
        stats = " ".join(x for x in lines[1:] if not x.startswith("Uploaded by"))
    return {"success": True, "data": {"video": {"video_id": vid, "title": title.strip(), "channel": name,
                                                "handle": handle, "subscribers": subs, "stats": stats}}}


def list_channel_videos(device, params, context):
    handle = "@" + str(params["handle"]).lstrip("@")
    limit = int(params.get("max_results") or 10)

    def header():
        nodes = visible_nodes(device)
        if not any(n["text"].lower() == handle.lower() for n in nodes):
            return None
        idx = next(i for i, n in enumerate(nodes) if n["text"].lower() == handle.lower())
        name = nodes[idx - 1]["text"].split(",")[0] if idx else ""
        subs = next((n["text"] for n in nodes if n["text"].endswith("subscribers")), "")
        count = next((n["text"] for n in nodes if re.match(r"^[\d.,]+\s?[KM]? videos?$", n["text"])), "")
        return {"handle": handle, "name": name, "subscribers": subs, "videos_total": count}

    channel = _load(device, f"https://m.youtube.com/{handle}/videos", header)
    if not channel:
        return {"success": False, "error": f"channel page for {handle} did not render"}
    channel["videos"] = _collect(device, limit, channel["name"])
    return {"success": True, "data": {"channel": channel}}


# ── End-state validators: (device, context) -> bool ──────────────────────────

def videos_found(device, context) -> bool:
    videos = context.result.get("videos") or []
    return bool(videos) and all(v.get("title") and v.get("channel") for v in videos)


def video_info_ok(device, context) -> bool:
    video = context.result.get("video") or {}
    return bool(video.get("title") and video.get("channel")) and video["video_id"] in url_bar(device)


def channel_listed(device, context) -> bool:
    channel = context.result.get("channel") or {}
    return bool(channel.get("name") and channel.get("videos"))
