---
title: "📲 ADB Device Control"
description: The core Device class with 47+ methods across 8 categories — taps, swipes, stealth, XML parsing, notifications, and TikTok navigation.
---

The `Device` class is the core abstraction for all Android device interaction. Every bot script, skill action, and automation workflow uses it as the interface to the physical phone.

## Quick Start

```python
from gitd.bots.common.adb import Device

dev = Device()                           # Auto-detect single device
dev = Device("YOUR_DEVICE_SERIAL")          # Specific device by serial

dev.tap(540, 1200)                       # Tap coordinates
xml = dev.dump_xml()                     # Get UI hierarchy
nodes = dev.find_nodes(xml, text="OK")   # Find elements
dev.tap_node(nodes[0])                   # Tap an element
```

## Method Reference (47+ methods)

### Core Input (8 methods)

| Method | Signature | Description |
|--------|-----------|-------------|
| `adb` | `(*args, timeout=30)` | Execute raw ADB command, return stdout |
| `adb_show` | `(*args)` | Execute ADB with live output (for push progress bars) |
| `tap` | `(x, y, delay=0.6)` | Single tap at coordinates |
| `swipe` | `(x1, y1, x2, y2, ms=500, delay=0.5)` | Swipe gesture with duration |
| `back` | `(delay=1.0)` | Press BACK key event |
| `press_enter` | `(delay=0.5)` | Press ENTER key event |
| `long_press` | `(x, y, duration_ms=1000, delay=0.5)` | Long press via swipe-to-same-point |
| `type_text` | `(text)` | Type ASCII text via `adb shell input text` |

### Multi-touch and Gestures (2 methods)

| Method | Signature | Description |
|--------|-----------|-------------|
| `pinch_in` | `(cx, cy, start_dist, end_dist, duration_ms)` | Pinch-to-zoom in (two fingers inward) |
| `pinch_out` | `(cx, cy, start_dist, end_dist, duration_ms)` | Pinch-to-zoom out (two fingers outward) |

Note: Due to ADB `input swipe` limitations, these move one finger at a time. True multi-touch requires `sendevent`.

### Unicode and Clipboard (3 methods)

| Method | Signature | Description |
|--------|-----------|-------------|
| `type_unicode` | `(text)` | Type emoji/CJK via ADBKeyboard IME broadcast |
| `clipboard_get` | `()` | Get clipboard text (API 29+) |
| `clipboard_set` | `(text)` | Set clipboard text |

`type_unicode` follows this flow: enable ADBKeyboard -> set as IME -> broadcast text -> restore Gboard -> disable ADBKeyboard.

### Notifications and Settings (5 methods)

| Method | Signature | Description |
|--------|-----------|-------------|
| `open_notifications` | `(delay=0.5)` | Expand notification shade |
| `close_notifications` | `(delay=0.3)` | Collapse notification shade |
| `read_notifications` | `()` | Dump XML of notification shade |
| `clear_notifications` | `(delay=0.5)` | Open + tap "Clear all" |
| `open_settings` | `(setting)` | Open specific settings page |

Settings options: `WIFI_SETTINGS`, `BLUETOOTH_SETTINGS`, `DISPLAY_SETTINGS`, `LOCATION_SOURCE_SETTINGS`, and more.

### Stealth Mode (3 methods)

| Method | Signature | Description |
|--------|-----------|-------------|
| `stealth_tap` | `(x, y, delay=0.6)` | Tap with Gaussian jitter (sigma=8px) |
| `stealth_swipe` | `(x1, y1, x2, y2, ms=None, delay=0.5)` | Swipe with variable speed (300-700ms) + jitter |
| `stealth_type` | `(text, delay_range=(0.05, 0.2))` | Char-by-char with random delays |

### XML Dump and Parsing (12+ methods)

| Method | Signature | Description |
|--------|-----------|-------------|
| `dump_xml` | `()` | Get UI tree (Portal HTTP -> Portal provider -> uiautomator) |
| `dump_portal_json` | `()` | Get UI tree as JSON via Droidrun Portal |
| `bounds_center` | `(bounds_str)` | Convert `[x1,y1][x2,y2]` to `(cx, cy)` |
| `find_bounds` | `(xml, text/rid/desc)` | Find element bounds string by attribute |
| `tap_text` | `(xml, text, fallback_xy)` | Find by text, tap its center |
| `wait_for` | `(text, timeout=12)` | Poll dump_xml() until text appears |
| `nodes` | `(xml)` | Extract all `<node>` strings from XML |
| `node_text` | `(node)` | Get `text` attribute from node string |
| `node_rid` | `(node)` | Get `resource-id` attribute |
| `node_content_desc` | `(node)` | Get `content-desc` attribute |
| `node_bounds` | `(node)` | Parse bounds to `(x1, y1, x2, y2)` tuple |
| `node_center` | `(bounds)` | Center from bounds tuple |
| `find_nodes` | `(xml, rid, text)` | Filter nodes by RID and/or text |
| `tap_node` | `(node, delay)` | Tap center of a node |

### XML Dump Priority Chain

The `dump_xml()` method tries three sources in order of speed:

| Source | Speed | Requires |
|--------|-------|----------|
| Portal HTTP (`/state` endpoint) | ~33ms | Droidrun Portal APK + port forward |
| Portal content provider | ~1.2s | Droidrun Portal APK |
| uiautomator dump | ~2.0s | Always available |

### TikTok Navigation (6 methods)

| Method | Signature | Description |
|--------|-----------|-------------|
| `restart_tiktok` | `(activity)` | Force-stop, relaunch, dismiss overlays and drafts |
| `go_to_profile` | `()` | Restart TikTok, tap Profile tab, wait for indicators |
| `go_to_drafts_screen` | `()` | Profile -> Drafts banner -> Drafts grid |
| `search_navigate` | `(query, tab)` | Open search, type, submit, navigate to tab |
| `screen_type` | `(xml)` | Classify screen: home, search_input, search_results, etc. |
| `dismiss_popups` | `(xml)` | Auto-dismiss 10+ known popup patterns (3-tier system) |

### Utility (4 methods)

| Method | Signature | Description |
|--------|-----------|-------------|
| `check_tiktok_version` | `()` | Return version, warn if != 44.3.3 |
| `get_app_version` | `(package)` | Return versionName for any package |
| `update_app` | `(package)` | Open Play Store, tap Update |
| `_dismiss_draft_overlay` | `()` | Pixel-scan for invisible draft overlay |

## Popup Dismissal (3-Tier System)

1. **Specific patterns** -- 10 known popups with exact detect string -> tap button mappings
2. **Generic fallback** -- scan clickable nodes for dismiss-like text (not now, skip, cancel, etc.), skip nodes wider than 600px
3. **Invisible overlay** -- detect "Learn more" pattern -> press Back

## Key Constants

| Constant | Value | Purpose |
|----------|-------|---------|
| `TIKTOK_PKG` | `com.zhiliaoapp.musically` | TikTok package name |
| `KNOWN_TIKTOK_VERSION` | `44.3.3` | Expected version |
| `RID_PROFILE_TAB` | `...musically:id/n19` | Profile icon RID |
| `RID_SEARCH_ICON` | `...musically:id/j4d` | Search magnifier RID |

## Files

| File | Purpose |
|------|---------|
| `gitd/bots/common/adb.py` | Device class (~700 lines) |
| `gitd/bots/common/elements.py` | ElementResolver (version-resilient finding) |
| `gitd/bots/common/discover_rids.py` | Semi-auto RID extraction tool |
| `gitd/bots/common/rid_maps/` | Version-specific RID maps |

## Related

- [Stealth Mode](/features/stealth-mode/) -- detailed stealth method documentation
- [Skill System](/features/skill-system/) -- how actions use the Device class
- [API: Device Methods](/api/device-methods/) -- full method signatures
