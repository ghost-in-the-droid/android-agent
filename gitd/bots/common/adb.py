#!/usr/bin/env python3
"""
adb_core.py — Shared ADB + XML primitives for Android automation.

Single Device class providing tap, swipe, type, screenshot, XML dump,
and other low-level ADB operations used by skills and bot scripts.
"""
import hashlib, html, json, re, subprocess, time


def _stable_port(serial: str, base: int = 18000) -> int:
    """Deterministic port from serial (stable across Python processes)."""
    return base + int(hashlib.md5(serial.encode()).hexdigest()[:3], 16) % 1000
from pathlib import Path

TIKTOK_PKG           = "com.zhiliaoapp.musically"
TIKTOK_MAIN_ACTIVITY = f"{TIKTOK_PKG}/com.ss.android.ugc.aweme.main.MainActivity"
TIKTOK_SPLASH        = f"{TIKTOK_PKG}/com.ss.android.ugc.aweme.splash.SplashActivity"

# Shared resource IDs — verified TikTok v44.3.3, 2026-03-21
KNOWN_TIKTOK_VERSION = "44.3.3"
RID_PROFILE_TAB  = f"{TIKTOK_PKG}:id/n19"   # bottom nav Profile icon (was myp)
RID_SEARCH_ICON  = f"{TIKTOK_PKG}:id/j4d"   # magnifying glass on home (was j29)
RID_SEARCH_BOX   = f"{TIKTOK_PKG}:id/gti"   # search text input field (was gry)
RID_SUGGESTION   = f"{TIKTOK_PKG}:id/zg6"   # suggestion row in search (was z_i)
RID_USERNAME_ROW = f"{TIKTOK_PKG}:id/zef"   # username in Users tab (was z8q)
RID_FILTER_CHIP  = f"{TIKTOK_PKG}:id/ecp"   # filter chips — TODO verify after update

# Known popups to dismiss (specific patterns checked first)
_KNOWN_POPUPS = [
    {"detect": "Continue editing",                "button": "Save draft",  "label": "Draft resume overlay"},
    {"detect": "connect with people",              "button": "Don\u2019t allow", "label": "Contacts access popup"},
    {"detect": "access to your Facebook",          "button": "Don't allow",  "label": "Facebook friends access popup"},
    {"detect": "Make TikTok Shop more relevant", "button": "Select",      "label": "TikTok Shop relevance"},
    {"detect": "shared collections",                "button": "Not now",     "label": "Shared collections popup"},
    {"detect": "Turn on notifications",            "button": "Not now",     "label": "Turn on notifications popup"},
    {"detect": "security checkup",                 "button": "Close",       "label": "Security checkup popup"},
    {"detect": "Not now",                         "button": "Not now",     "label": "Not now dialog"},
    {"detect": 'content-desc="Close"',            "button": "Close",       "label": "Close dialog"},
    {"detect": "Skip",                            "button": "Skip",        "label": "Skip dialog"},
]
# Generic dismiss words (fallback if no specific popup matched)
# 'discard' handles the "Discard draft?" dialog that appears when Back is pressed in creation screen
_DISMISS_WORDS = {'not now', 'skip', 'cancel', 'dismiss', 'later', 'discard'}
_DISMISS_EXACT = {'cancel', 'dismiss', 'discard', 'save draft', "don\u2019t allow", "don't allow"}


class Device:
    """Encapsulates ADB + XML primitives for one connected Android device."""

    def __init__(self, serial: str):
        self.serial = serial

    # ── ADB primitives ────────────────────────────────────────────────────────

    def adb(self, *args, timeout=30) -> str:
        r = subprocess.run(
            ["adb", "-s", self.serial, *args],
            capture_output=True, text=True, timeout=timeout,
        )
        return r.stdout.strip()

    def adb_show(self, *args):
        """adb with live output (e.g. for push progress)."""
        subprocess.run(["adb", "-s", self.serial, *args])

    def tap(self, x, y, delay=0.6):
        self.adb("shell", "input", "tap", str(int(x)), str(int(y)))
        time.sleep(delay)

    def swipe(self, x1, y1, x2, y2, ms=500, delay=0.5):
        self.adb("shell", "input", "swipe",
                 str(int(x1)), str(int(y1)), str(int(x2)), str(int(y2)), str(ms))
        time.sleep(delay)

    def back(self, delay=1.0):
        self.adb("shell", "input", "keyevent", "KEYCODE_BACK")
        time.sleep(delay)

    def press_enter(self, delay=0.5):
        self.adb("shell", "input", "keyevent", "KEYCODE_ENTER")
        time.sleep(delay)

    def long_press(self, x, y, duration_ms=1000, delay=0.5):
        """Long press at (x, y) for duration_ms milliseconds."""
        self.adb("shell", "input", "swipe",
                 str(int(x)), str(int(y)), str(int(x)), str(int(y)), str(duration_ms))
        time.sleep(delay)

    def clipboard_get(self) -> str:
        """Get clipboard text (requires API 29+)."""
        return self.adb("shell", "cmd", "clipboard", "get-text") or ''

    def clipboard_set(self, text: str):
        """Set clipboard text."""
        self.adb("shell", "cmd", "clipboard", "set-text", text)

    # ── Multi-touch / pinch ────────────────────────────────────────────────

    def pinch_in(self, cx, cy, start_dist=300, end_dist=50, duration_ms=500, delay=0.5):
        """Pinch-to-zoom in (two fingers moving inward)."""
        steps = max(10, duration_ms // 20)
        self.adb("shell", "input", "swipe",
                 str(cx - start_dist), str(cy), str(cx - end_dist), str(cy), str(duration_ms))
        time.sleep(delay)

    def pinch_out(self, cx, cy, start_dist=50, end_dist=300, duration_ms=500, delay=0.5):
        """Pinch-to-zoom out (two fingers moving outward)."""
        self.adb("shell", "input", "swipe",
                 str(cx - start_dist), str(cy), str(cx - end_dist), str(cy), str(duration_ms))
        time.sleep(delay)

    # ── Unicode text input (ADBKeyboard) ───────────────────────────────────

    def type_unicode(self, text: str, delay=0.3):
        """Type text including emoji/unicode via ADBKeyboard broadcast.

        Requires ADBKeyboard APK installed on device.
        Flow: enable IME → set IME → broadcast text → restore Gboard.
        """
        adb_ime = "com.android.adbkeyboard/.AdbIME"
        gboard = "com.google.android.inputmethod.latin/com.android.inputmethod.latin.LatinIME"

        # Enable and switch to ADBKeyboard
        self.adb("shell", "ime", "enable", adb_ime)
        self.adb("shell", "ime", "set", adb_ime)
        time.sleep(0.2)

        # Broadcast text (handles emoji, CJK, accented chars)
        escaped = text.replace('"', '\\"')
        self.adb("shell", "am", "broadcast",
                 "-a", "ADB_INPUT_TEXT", "--es", "msg", f'"{escaped}"')
        time.sleep(delay)

        # Restore original IME immediately (stealth: minimize time on ADBKeyboard)
        self.adb("shell", "ime", "set", gboard)
        self.adb("shell", "ime", "disable", adb_ime)

    # ── Notifications ──────────────────────────────────────────────────────

    def open_notifications(self, delay=0.5):
        """Swipe down from status bar to open notification shade."""
        self.adb("shell", "cmd", "statusbar", "expand-notifications")
        time.sleep(delay)

    def close_notifications(self, delay=0.3):
        """Close notification shade."""
        self.adb("shell", "cmd", "statusbar", "collapse")
        time.sleep(delay)

    def read_notifications(self) -> str:
        """Dump XML of notification shade. Call open_notifications() first."""
        return self.dump_xml()

    def clear_notifications(self, delay=0.5):
        """Open notifications and tap 'Clear all'."""
        self.open_notifications(delay=0.5)
        xml = self.dump_xml()
        if not self.tap_text(xml, "Clear all"):
            self.tap_text(xml, "CLEAR ALL")
        time.sleep(delay)

    # ── System settings shortcuts ──────────────────────────────────────────

    def open_settings(self, setting: str = "SETTINGS", delay=0.5):
        """Open a system settings page. Common values: WIFI_SETTINGS, BLUETOOTH_SETTINGS,
        DISPLAY_SETTINGS, SOUND_SETTINGS, LOCATION_SOURCE_SETTINGS, SETTINGS."""
        action = f"android.settings.{setting}" if "." not in setting else setting
        self.adb("shell", "am", "start", "-a", action)
        time.sleep(delay)

    # ── Stealth mode ───────────────────────────────────────────────────────

    def stealth_tap(self, x, y, delay=0.6):
        """Tap with Gaussian jitter on coordinates (±5-15px) to appear human."""
        import random
        jx = x + random.gauss(0, 8)
        jy = y + random.gauss(0, 8)
        self.tap(int(jx), int(jy), delay=delay)

    def stealth_swipe(self, x1, y1, x2, y2, ms=None, delay=0.5):
        """Swipe with variable speed and slight curve to appear human."""
        import random
        ms = ms or random.randint(300, 700)
        # Add slight curve (offset midpoint)
        mid_offset_x = random.randint(-20, 20)
        mid_offset_y = random.randint(-20, 20)
        # Just use standard swipe with variable duration (curved paths need sendevent)
        jx1 = x1 + random.gauss(0, 5)
        jy1 = y1 + random.gauss(0, 5)
        jx2 = x2 + random.gauss(0, 5)
        jy2 = y2 + random.gauss(0, 5)
        self.swipe(int(jx1), int(jy1), int(jx2), int(jy2), ms=ms, delay=delay)

    def stealth_type(self, text: str, delay_range=(0.05, 0.2)):
        """Type text character-by-character with random delays to appear human."""
        import random
        for char in text:
            self.adb("shell", "input", "text", char)
            time.sleep(random.uniform(*delay_range))

    # ── XML dump (Droidrun Portal → uiautomator fallback) ──────────────────

    # Per-device portal HTTP port (set up via adb forward)
    _portal_ports: dict = {}  # serial → local_port
    _portal_failed: set = set()  # serials where portal is unavailable

    def _ensure_portal_forward(self, force=False) -> int | None:
        """Ensure ADB port forward for Portal HTTP. Returns local port or None."""
        if force:
            Device._portal_failed.discard(self.serial)
            Device._portal_ports.pop(self.serial, None)
        if self.serial in Device._portal_failed:
            return None
        if self.serial in Device._portal_ports:
            return Device._portal_ports[self.serial]
        local_port = _stable_port(self.serial, 18000)
        try:
            subprocess.run(
                ["adb", "-s", self.serial, "forward", f"tcp:{local_port}", "tcp:8080"],
                capture_output=True, timeout=3, check=True,
            )
            Device._portal_ports[self.serial] = local_port
            return local_port
        except Exception:
            # Don't permanently blacklist — allow retry next call
            return None

    def dump_portal_json(self) -> dict | list | None:
        """Fast UI state via Droidrun Portal HTTP (33ms) or content provider (1.2s)."""
        import urllib.request
        # Try HTTP first (37x faster than content provider)
        port = self._ensure_portal_forward()
        if port:
            try:
                req = urllib.request.urlopen(f'http://localhost:{port}/state', timeout=2)
                data = json.loads(req.read())
                if data.get('status') == 'success':
                    tree = json.loads(data['result']).get('a11y_tree')
                    if tree:
                        return tree
            except Exception:
                pass
        # Fallback: content provider (slower but no port forward needed)
        for authority in ("com.ghostinthedroid.portal", "com.droidrun.portal"):
            try:
                r = subprocess.run(
                    ["adb", "-s", self.serial, "shell",
                     "content", "query", "--uri", f"content://{authority}/state_full"],
                    capture_output=True, text=True, timeout=5,
                )
                if 'result=' in r.stdout and '"status":"success"' in r.stdout:
                    raw = r.stdout.split('result=', 1)[1]
                    data = json.loads(raw)
                    return data.get('result', {}).get('a11y_tree', {})
            except Exception:
                pass
        return None

    def _portal_node_to_xml(self, node: dict, depth: int = 0) -> str:
        """Convert Portal JSON node → uiautomator-compatible XML."""
        # Handle both formats: boundsInScreen (content provider) and bounds string (HTTP)
        bounds_raw = node.get('boundsInScreen') or node.get('bounds', '')
        if isinstance(bounds_raw, dict):
            b = f"[{bounds_raw.get('left',0)},{bounds_raw.get('top',0)}][{bounds_raw.get('right',0)},{bounds_raw.get('bottom',0)}]"
        elif isinstance(bounds_raw, str) and ',' in bounds_raw:
            parts = [int(x) for x in bounds_raw.replace(' ', '').split(',')]
            b = f"[{parts[0]},{parts[1]}][{parts[2]},{parts[3]}]" if len(parts) == 4 else bounds_raw
        else:
            b = "[0,0][0,0]"
        text = html.escape(str(node.get('text', '') or ''))
        # Strip class name prefix that Portal puts in text field
        cls = node.get('className', '')
        if text == cls.split('.')[-1]:
            text = ''  # Portal puts className as text for containers
        desc = html.escape(str(node.get('contentDescription', '') or ''))
        rid = html.escape(str(node.get('resourceId', '') or ''))
        clickable = str(node.get('isClickable', False)).lower()
        children = node.get('children', [])
        child_xml = ''.join(self._portal_node_to_xml(c, depth + 1) for c in children)
        return (f'<node index="{depth}" text="{text}" resource-id="{rid}" '
                f'class="{cls}" content-desc="{desc}" clickable="{clickable}" '
                f'bounds="{b}">{child_xml}</node>')

    def dump_xml(self) -> str:
        """Get UI tree. Tries Droidrun Portal (fast) first, falls back to uiautomator."""
        tree = self.dump_portal_json()
        if tree:
            nodes = tree if isinstance(tree, list) else [tree]
            inner = ''.join(self._portal_node_to_xml(n) for n in nodes)
            return f'<?xml version="1.0" encoding="UTF-8"?><hierarchy rotation="0">{inner}</hierarchy>'
        # Fallback: classic uiautomator dump
        self.adb("shell", "uiautomator", "dump", "/sdcard/tt.xml")
        r = subprocess.run(
            ["adb", "-s", self.serial, "exec-out", "cat", "/sdcard/tt.xml"],
            capture_output=True, text=True,
        )
        return r.stdout

    # ── XML parsing ───────────────────────────────────────────────────────────

    def bounds_center(self, bounds_str: str) -> tuple[int, int]:
        """'[x1,y1][x2,y2]' → (cx, cy)"""
        n = list(map(int, re.findall(r'\d+', bounds_str)))
        return (n[0] + n[2]) // 2, (n[1] + n[3]) // 2

    def find_bounds(self, xml: str, *, text=None, content_desc=None, resource_id=None) -> str | None:
        """Return bounds string of first node matching the given attribute."""
        if text:          key, val = "text",         text
        elif content_desc: key, val = "content-desc", content_desc
        elif resource_id:  key, val = "resource-id",  resource_id
        else:              return None
        m = re.search(rf'<node[^>]*{key}="{re.escape(val)}"[^>]*>', xml)
        if m:
            bm = re.search(r'bounds="([^"]+)"', m.group())
            return bm.group(1) if bm else None
        return None

    def tap_text(self, xml: str, text: str, fallback_xy=None, delay=0.8) -> bool:
        b = self.find_bounds(xml, text=text)
        if b:
            self.tap(*self.bounds_center(b), delay)
            return True
        if fallback_xy:
            self.tap(*fallback_xy, delay)
            return True
        raise RuntimeError(f"Could not find '{text}' on screen")

    def wait_for(self, text: str, timeout=12, interval=1.0) -> str:
        """Poll dump_xml until text appears. Returns xml."""
        for i in range(int(timeout / interval) + 1):
            xml = self.dump_xml()
            if text in xml:
                return xml
            print(f"    [{i}s] waiting for '{text}'...")
            time.sleep(interval)
        raise TimeoutError(f"Timed out ({timeout}s) waiting for: {text!r}")

    def nodes(self, xml: str) -> list[str]:
        return re.findall(r'<node[^>]+/?>', xml)

    def node_text(self, node: str) -> str:
        m = re.search(r'\btext="([^"]*)"', node)
        return html.unescape(m.group(1).strip()) if m else ''

    def node_content_desc(self, node: str) -> str:
        m = re.search(r'content-desc="([^"]*)"', node)
        return html.unescape(m.group(1).strip()) if m else ''

    def node_rid(self, node: str) -> str:
        m = re.search(r'resource-id="([^"]*)"', node)
        return m.group(1) if m else ''

    def node_bounds(self, node: str) -> tuple | None:
        """Returns (x1, y1, x2, y2) or None."""
        m = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', node)
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))) if m else None

    def node_center(self, b: tuple) -> tuple[int, int]:
        return (b[0] + b[2]) // 2, (b[1] + b[3]) // 2

    def find_nodes(self, xml: str, rid: str | None = None, text: str | None = None) -> list[str]:
        """Filter nodes by rid and/or text (checks both text and content-desc)."""
        out = []
        for node in self.nodes(xml):
            if rid  and self.node_rid(node) != rid: continue
            if text and text.lower() not in (
                self.node_text(node) + self.node_content_desc(node)
            ).lower(): continue
            out.append(node)
        return out

    def tap_node(self, node: str, delay=0.8) -> bool:
        b = self.node_bounds(node)
        if b:
            self.tap(*self.node_center(b), delay)
            return True
        return False

    # ── TikTok app helpers ────────────────────────────────────────────────────

    def restart_tiktok(self, activity=TIKTOK_MAIN_ACTIVITY):
        # Wake screen if asleep
        self.adb("shell", "input", "keyevent", "KEYCODE_WAKEUP")
        time.sleep(0.3)
        # Go home first so force-stop doesn't surface a random background app
        self.adb("shell", "input", "keyevent", "KEYCODE_HOME")
        time.sleep(0.5)
        self.adb("shell", "am", "force-stop", TIKTOK_PKG)
        time.sleep(1)
        self.adb("shell", "am", "start", "-n", activity)
        time.sleep(3)
        # TikTok sometimes restores a previous creation session — back out until home
        for _ in range(8):
            xml = self.dump_xml()
            if self.screen_type(xml) == 'home':
                break
            if self.dismiss_popups(xml):
                continue
            self.back(1.5)
        # Dismiss "Continue editing this post?" overlay (invisible to uiautomator).
        # Detect via screencap: red "Edit" button in top 15% of screen.
        self._dismiss_draft_overlay()

    def _dismiss_draft_overlay(self):
        """Detect and dismiss 'Continue editing this post?' overlay.

        This overlay is invisible to uiautomator. We detect it by taking a
        screencap and scanning for TikTok's red/pink 'Edit' button
        (R>220, G<100, B<120) in the top 15% of screen. Requires a wide
        horizontal band of red (>=150px) to avoid false positives from
        red hearts/icons on the feed. If found, tap 'Save draft' on the
        left side at the same height.
        """
        try:
            raw = subprocess.run(
                ["adb", "-s", self.serial, "exec-out", "screencap"],
                capture_output=True, timeout=5,
            ).stdout
            if len(raw) < 16:
                return
            import struct
            w = struct.unpack_from('<I', raw, 0)[0]
            h = struct.unpack_from('<I', raw, 4)[0]
            hdr = 12  # width(4) + height(4) + format(4)
            scan_max_y = h // 7  # top ~15%
            # Scan rows for a wide red band (the Edit button is ~380px wide)
            best_row_y, best_row_xmin, best_row_xmax = 0, 0, 0
            for y in range(scan_max_y // 3, scan_max_y, 5):
                row_xs = []
                for x in range(w // 3, w - 10, 10):
                    off = hdr + (y * w + x) * 4
                    if off + 3 >= len(raw):
                        continue
                    r, g, b = raw[off], raw[off + 1], raw[off + 2]
                    if r > 220 and g < 100 and b < 120:
                        row_xs.append(x)
                if len(row_xs) >= 8:  # at least 8 samples × 10px step = ~80px wide
                    span = max(row_xs) - min(row_xs)
                    if span > best_row_xmax - best_row_xmin:
                        best_row_y = y
                        best_row_xmin = min(row_xs)
                        best_row_xmax = max(row_xs)
            # Require button to be at least 150px wide
            if best_row_xmax - best_row_xmin >= 150:
                tap_x = w // 4
                tap_y = best_row_y
                print(f"[popup] Draft resume overlay detected — tapping Save draft @ ({tap_x},{tap_y})")
                self.tap(tap_x, tap_y, delay=1.0)
        except Exception:
            pass

    def go_to_profile(self) -> str:
        """Restart TikTok, tap Profile tab, wait for profile to load. Returns XML."""
        self.restart_tiktok()
        xml = self.dump_xml()
        b = self.find_bounds(xml, resource_id=RID_PROFILE_TAB)
        self.tap(*self.bounds_center(b) if b else (972, 2214), delay=2.5)
        # Wait for profile indicators
        PROFILE_INDICATORS = ('"r6p"', 'desc="Videos"', 'desc="Posts"', ':id/r4r')
        for _ in range(10):
            xml = self.dump_xml()
            if any(ind in xml for ind in PROFILE_INDICATORS):
                return xml
            self.dismiss_popups(xml)
            time.sleep(1)
        return self.dump_xml()

    def go_to_drafts_screen(self) -> str | None:
        """Restart TikTok → Profile → tap Drafts banner → Drafts grid.

        Returns XML of the Drafts screen, or None if account has 0 drafts.
        Leaves TikTok open on the Drafts screen (or force-stops if 0 drafts).
        """
        xml = self.go_to_profile()
        PROFILE_INDICATORS = ('"r6p"', 'desc="Videos"', 'desc="Posts"')

        # Wait for Drafts banner (rid=yfk) — early-exit if profile loaded but no banner
        b = None
        for attempt in range(10):
            xml = self.dump_xml()
            b = self.find_bounds(xml, resource_id=f"{TIKTOK_PKG}:id/yfk")
            if b or 'Drafts:' in xml:
                break
            if any(ind in xml for ind in PROFILE_INDICATORS):
                self.adb("shell", "am", "force-stop", TIKTOK_PKG)
                return None   # profile loaded but no banner → 0 drafts
            self.dismiss_popups(xml)
            time.sleep(1)
        else:
            self.adb("shell", "am", "force-stop", TIKTOK_PKG)
            return None

        self.tap(*self.bounds_center(b), delay=2.5)

        # Wait for Drafts grid
        for _ in range(8):
            xml = self.dump_xml()
            if f"{TIKTOK_PKG}:id/ea3" in xml or "drafts" in xml.lower():
                return xml
            time.sleep(1)
        return self.dump_xml()  # return whatever we have

    def dismiss_popups(self, xml: str | None = None, popups: list[dict] | None = None) -> bool:
        """Dismiss known popups. Pass skill-specific popups or uses global defaults.
        Returns True if something was dismissed."""
        if xml is None:
            xml = self.dump_xml()
        # 1. Specific known popups first (skill-specific override global)
        popup_list = popups if popups is not None else _KNOWN_POPUPS
        for popup in popup_list:
            if popup["detect"] not in xml:
                continue
            print(f"[popup] {popup.get('label', popup['detect'])}")
            # method: "back" means press Back instead of tapping a button
            if popup.get("method") == "back":
                self.back(delay=1.0)
                return True
            btn = popup["button"]
            matches = []
            for m in re.finditer(
                rf'(?:text|content-desc)="{re.escape(btn)}"[^>]*bounds="([^"]+)"', xml
            ):
                nums = list(map(int, re.findall(r'\d+', m.group(1))))
                matches.append((nums[1], m.group(1)))
            if matches:
                matches.sort(key=lambda x: x[0])
                self.tap(*self.bounds_center(matches[0][1]), delay=1.0)
                return True
        # 2. Generic fallback — clickable buttons with dismiss-like text
        #    Filter out large nodes (video captions etc.) — popup buttons are small.
        for node in self.nodes(xml):
            if 'clickable="true"' not in node:
                continue
            label = (self.node_text(node) + ' ' + self.node_content_desc(node)).lower().strip()
            b = self.node_bounds(node)
            if not b or b[3] < 200:
                continue
            # Skip nodes wider than 600px — those are content areas, not popup buttons
            node_width = b[2] - b[0]
            if node_width > 600:
                continue
            words = set(label.split())
            if label in _DISMISS_EXACT or words & _DISMISS_WORDS:
                cx, cy = self.node_center(b)
                print(f"[popup] dismissing '{label[:30]}' @ ({cx},{cy})")
                self.tap(cx, cy, delay=1.0)
                return True
        # 3. Invisible overlay fallback — some TikTok popups (Family Pairing, promos)
        #    are rendered overlays invisible to uiautomator. Dismiss with Back.
        if 'Learn more' in xml and 'content-desc=" Learn more"' in xml:
            print("[popup] invisible overlay (Learn more visible) — pressing Back")
            self.back(delay=1.0)
            return True
        return False

    def search_navigate(self, query: str, tab: str | None = None) -> str:
        """Open search, type query, submit, optionally navigate to a named tab.

        Works from any screen state (home, search_results, etc.).
        query   — search term; '#' → KEYCODE_POUND, ' ' → %s; '@' stripped automatically
        tab     — e.g. 'Users', 'Top', 'Videos' — tap that tab after results load
        Returns fresh XML after navigation.
        """
        xml = self.dump_xml()
        st = self.screen_type(xml)

        # ── Open search ────────────────────────────────────────────────────────
        if st == 'home':
            nodes = self.find_nodes(xml, rid=RID_SEARCH_ICON)
            self.tap_node(nodes[0], delay=1.0) if nodes else self.tap(1011, 129, delay=1.0)
        elif st in ('search_results', 'users_tab'):
            nodes = self.find_nodes(xml, rid=RID_SEARCH_BOX)
            self.tap_node(nodes[0], delay=1.0) if nodes else self.tap(540, 65, delay=1.0)
        # else already at search_input — proceed directly

        # Wait until search input is ready before typing (retry tap if needed)
        for attempt in range(3):
            for _ in range(6):
                xml = self.dump_xml()
                if self.screen_type(xml) == 'search_input':
                    break
                self.dismiss_popups(xml)
                time.sleep(1.0)
            else:
                # Didn't reach search_input — tap icon again and retry
                xml = self.dump_xml()
                cur = self.screen_type(xml)
                if cur == 'home':
                    nodes = self.find_nodes(xml, rid=RID_SEARCH_ICON)
                    self.tap_node(nodes[0], delay=1.5) if nodes else self.tap(1011, 129, delay=1.5)
                elif cur in ('search_results', 'users_tab'):
                    nodes = self.find_nodes(xml, rid=RID_SEARCH_BOX)
                    self.tap_node(nodes[0], delay=1.2) if nodes else self.tap(540, 65, delay=1.2)
                continue
            break  # reached search_input

        # ── Type query ─────────────────────────────────────────────────────────
        clean = query.lstrip('@')
        self.adb('shell', 'input', 'keyevent', 'KEYCODE_MOVE_END')
        for _ in range(80):
            self.adb('shell', 'input', 'keyevent', 'KEYCODE_DEL')
        for ch in clean:
            if ch == '#':
                self.adb('shell', 'input', 'keyevent', 'KEYCODE_POUND')
            elif ch == ' ':
                self.adb('shell', 'input', 'text', '%s')
            else:
                self.adb('shell', 'input', 'text', ch)
            time.sleep(0.2)
        # Tap "Search" button instead of ENTER (ENTER selects autocomplete)
        xml = self.dump_xml()
        search_btn = [n for n in self.nodes(xml)
                      if self.node_text(n) == 'Search'
                      and 'clickable="true"' in n
                      and (b := self.node_bounds(n)) and b[1] < 200]
        if search_btn:
            self.tap_node(search_btn[0], delay=2.5)
        else:
            self.press_enter(delay=2.5)

        # ── Wait for results ───────────────────────────────────────────────────
        xml = self.dump_xml()
        for attempt in range(7):
            st = self.screen_type(xml)
            if st in ('search_results', 'users_tab'):
                break
            if self.dismiss_popups(xml):
                xml = self.dump_xml()
                continue
            if st == 'search_input':
                sugg = [n for n in self.find_nodes(xml, rid=RID_SUGGESTION)
                        if clean.lower().lstrip('#') in self.node_text(n).lower()]
                if sugg:
                    self.tap_node(sugg[0], delay=2.0)
                else:
                    # Tap the "Search" button (top-right) instead of ENTER
                    # (ENTER selects autocomplete suggestions instead of submitting)
                    search_btn = [n for n in self.nodes(xml)
                                  if self.node_text(n) == 'Search'
                                  and 'clickable="true"' in n
                                  and (b := self.node_bounds(n)) and b[1] < 200]
                    if search_btn:
                        self.tap_node(search_btn[0], delay=2.5)
                    else:
                        self.adb('shell', 'input', 'keyevent', 'KEYCODE_ENTER')
                        time.sleep(2.0)
            else:
                time.sleep(1.5)
            xml = self.dump_xml()
        else:
            raise RuntimeError(f'Could not reach search results for "{query}" after 7 attempts')

        # ── Navigate to tab ────────────────────────────────────────────────────
        if tab:
            for node in self.nodes(xml):
                if self.node_text(node) != tab:
                    continue
                b = self.node_bounds(node)
                if b and b[3] < 350:
                    self.tap(*self.node_center(b), delay=2.0)
                    xml = self.dump_xml()
                    break

        return xml

    def screen_type(self, xml: str) -> str:
        """Classify current TikTok screen.

        Returns: home | search_input | search_results | users_tab | filters_panel | unknown
        """
        if self.find_nodes(xml, rid=RID_USERNAME_ROW):
            return 'users_tab'
        if self.find_nodes(xml, rid=RID_FILTER_CHIP):
            return 'filters_panel'
        if any(
            (b := self.node_bounds(n)) and b[3] < 350
            for n in self.find_nodes(xml, text='Users')
        ):
            return 'search_results'
        if self.find_nodes(xml, rid=RID_SEARCH_BOX):
            return 'search_input'
        if self.find_nodes(xml, rid=RID_SEARCH_ICON):
            return 'home'
        return 'unknown'


    def check_tiktok_version(self) -> str:
        """Return installed TikTok version. Warn if it differs from KNOWN_TIKTOK_VERSION."""
        out = self.adb("shell", "dumpsys", "package", TIKTOK_PKG, timeout=10)
        m = re.search(r'versionName=(\S+)', out)
        ver = m.group(1) if m else "unknown"
        if ver != KNOWN_TIKTOK_VERSION:
            print(f"[WARN] TikTok version {ver} != expected {KNOWN_TIKTOK_VERSION} — RIDs may be stale!")
        return ver

    def get_app_version(self, package: str) -> str:
        """Return versionName for any installed package."""
        out = self.adb("shell", "dumpsys", "package", package, timeout=10)
        m = re.search(r'versionName=(\S+)', out)
        return m.group(1) if m else "unknown"

    def update_app(self, package: str, timeout: int = 300, log=print) -> str:
        """Update an app via Play Store. Returns new version string.

        Flow: force-stop app → open Play Store page → tap Update → poll for completion.
        Raises RuntimeError if update button not found or times out.
        """
        old_ver = self.get_app_version(package)
        log(f"[update] {package} current version: {old_ver}")

        # Force-stop the app so it doesn't interfere
        self.adb("shell", "am", "force-stop", package)
        time.sleep(1)

        # Open Play Store page for this app
        self.adb("shell", "am", "start", "-a", "android.intent.action.VIEW",
                 "-d", f"market://details?id={package}")
        time.sleep(4)

        # Find and tap "Update" button
        xml = self.dump_xml()
        update_node = None
        for node in self.nodes(xml):
            if self.node_text(node) == 'Update':
                update_node = node
                break
        if not update_node:
            # Check if already up to date
            for node in self.nodes(xml):
                if self.node_text(node) == 'Open':
                    log(f"[update] Already up to date: {old_ver}")
                    return old_ver
            raise RuntimeError(f"Update button not found for {package}")

        b = self.node_bounds(update_node)
        if b:
            cx, cy = self.node_center(b)
            log(f"[update] Tapping Update @ ({cx},{cy})")
            self.tap(cx, cy, delay=2.0)
        else:
            raise RuntimeError("Update button has no bounds")

        # Poll until "Open" appears (update complete) or timeout
        poll_interval = 5
        elapsed = 0
        while elapsed < timeout:
            time.sleep(poll_interval)
            elapsed += poll_interval
            xml = self.dump_xml()
            for node in self.nodes(xml):
                txt = self.node_text(node)
                if txt == 'Open':
                    new_ver = self.get_app_version(package)
                    log(f"[update] Done! {old_ver} → {new_ver} ({elapsed}s)")
                    return new_ver
            log(f"[update] Downloading... ({elapsed}s)")

        raise RuntimeError(f"Update timed out after {timeout}s")


def get_device(serial: str | None = None) -> Device:
    """Return a Device instance. Auto-detects if only one phone connected."""
    import os
    serial = serial or os.environ.get("DEVICE")
    if serial:
        return Device(serial)
    connected = list_connected()
    if len(connected) == 1:
        return Device(connected[0])
    raise RuntimeError(f"Multiple devices connected — specify serial. Found: {connected}")


def list_connected() -> list[str]:
    out = subprocess.run(["adb", "devices"], capture_output=True, text=True).stdout
    return [
        line.split()[0]
        for line in out.splitlines()[1:]
        if line.strip() and line.split()[-1] == "device"
    ]
