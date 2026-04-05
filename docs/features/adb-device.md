# ADB Device Class — Feature Summary

## What It Does

Core abstraction for all Android device interaction. The `Device` class wraps ADB commands into a clean Python API with 47+ methods covering taps, swipes, text input, multi-touch gestures, stealth mode, notifications, clipboard, screen capture, XML parsing, popup dismissal, and TikTok-specific navigation. Every bot script, skill action, and automation workflow in the system uses this class as its interface to the physical device.

## Current State

**47+ methods across 8 categories, verified on multiple Android devices.**

### Core Input (8 methods)
| Method | Description |
|--------|-------------|
| `adb(*args, timeout=30)` | Execute raw ADB command, return stdout |
| `adb_show(*args)` | Execute ADB with live output (for push progress bars) |
| `tap(x, y, delay=0.6)` | Single tap at coordinates |
| `swipe(x1, y1, x2, y2, ms=500, delay=0.5)` | Swipe gesture with duration |
| `back(delay=1.0)` | Press BACK key event |
| `press_enter(delay=0.5)` | Press ENTER key event |
| `long_press(x, y, duration_ms=1000, delay=0.5)` | Long press (swipe to same point) |
| `type_text(text)` | Type ASCII text via `adb shell input text` |

### Multi-touch & Gestures (2 methods)
| Method | Description |
|--------|-------------|
| `pinch_in(cx, cy, start_dist, end_dist, duration_ms)` | Pinch-to-zoom in (two fingers inward) |
| `pinch_out(cx, cy, start_dist, end_dist, duration_ms)` | Pinch-to-zoom out (two fingers outward) |

### Unicode & Clipboard (3 methods)
| Method | Description |
|--------|-------------|
| `type_unicode(text)` | Type emoji/CJK via ADBKeyboard IME broadcast (enable → set → broadcast → restore Gboard) |
| `clipboard_get()` | Get clipboard text (`cmd clipboard get-text`, API 29+) |
| `clipboard_set(text)` | Set clipboard text |

### Notifications & Settings (5 methods)
| Method | Description |
|--------|-------------|
| `open_notifications(delay=0.5)` | Expand notification shade |
| `close_notifications(delay=0.3)` | Collapse notification shade |
| `read_notifications()` | Dump XML of notification shade |
| `clear_notifications(delay=0.5)` | Open notifications + tap "Clear all" |
| `open_settings(setting)` | Open specific settings page (WIFI_SETTINGS, BLUETOOTH_SETTINGS, etc.) |

### Stealth Mode (3 methods)
| Method | Description |
|--------|-------------|
| `stealth_tap(x, y)` | Tap with Gaussian jitter +/-8px sigma |
| `stealth_swipe(x1, y1, x2, y2)` | Swipe with variable speed (300-700ms) + jitter |
| `stealth_type(text, delay_range)` | Char-by-char with 50-200ms random delays |

### XML Dump & Parsing (12+ methods)
| Method | Description |
|--------|-------------|
| `dump_xml()` | Get UI tree: Portal HTTP (33ms) → Portal content provider (1.2s) → uiautomator (2s) |
| `dump_portal_json()` | Get UI tree as JSON via Droidrun Portal |
| `bounds_center(bounds_str)` | Convert `[x1,y1][x2,y2]` → `(cx, cy)` |
| `find_bounds(xml, text/rid/desc)` | Find element bounds string by attribute |
| `tap_text(xml, text, fallback_xy)` | Find element by text → tap its center |
| `wait_for(text, timeout=12)` | Poll `dump_xml()` until text appears |
| `nodes(xml)` | Extract all `<node>` strings from XML |
| `node_text(node)` / `node_rid(node)` / `node_content_desc(node)` | Field extractors |
| `node_bounds(node)` → `(x1, y1, x2, y2)` | Parse bounds from node string |
| `node_center(bounds)` → `(cx, cy)` | Center from bounds tuple |
| `find_nodes(xml, rid, text)` | Filter nodes by RID and/or text |
| `tap_node(node, delay)` | Tap center of a node |

### TikTok Navigation (6 methods)
| Method | Description |
|--------|-------------|
| `restart_tiktok(activity)` | Force-stop → relaunch → dismiss overlays → dismiss draft overlay |
| `go_to_profile()` | Restart TikTok → Profile tab → wait for profile indicators |
| `go_to_drafts_screen()` | Profile → Drafts banner → Drafts grid (returns None if 0 drafts) |
| `search_navigate(query, tab)` | Open search → type → submit → navigate to tab (handles retries) |
| `screen_type(xml)` | Classify: home, search_input, search_results, users_tab, filters_panel, unknown |
| `dismiss_popups(xml)` | Auto-dismiss 10+ known TikTok popup patterns (3-tier: specific → generic → invisible) |

### Utility (4 methods)
| Method | Description |
|--------|-------------|
| `check_tiktok_version()` | Return installed version, warn if != `KNOWN_TIKTOK_VERSION` (44.3.3) |
| `get_app_version(package)` | Return versionName for any installed package |
| `update_app(package)` | Open Play Store → tap Update |
| `_dismiss_draft_overlay()` | Pixel-scan screencap for invisible draft overlay (red Edit button detection) |

## Architecture

```
Bot scripts / Skill actions / MacroRecorder
        │
        │  d = Device('YOUR_DEVICE_SERIAL')
        │  d.tap(540, 1200)
        ▼
Device class (adb.py)
        │
        ├── ADB commands: subprocess.run(['adb', '-s', serial, ...])
        ├── Portal HTTP: localhost:<port>/state (via adb forward)
        ├── Portal JSON → XML conversion (_portal_node_to_xml)
        └── uiautomator fallback: dump → /sdcard/tt.xml → exec-out cat
```

**XML dump priority chain:**
1. Portal HTTP (`/state` endpoint, ~33ms) — fastest, requires Portal APK
2. Portal content provider (`content://com.droidrun.portal/state_full`, ~1.2s) — no port forward needed
3. uiautomator (`uiautomator dump`, ~2s) — always works but slowest

**Port allocation:** `_stable_port(serial, base=18000)` — MD5 of serial for deterministic per-device port.

## Files

| File | Purpose |
|------|---------|
| `gitd/bots/common/adb.py` | `Device` class (47+ methods, ~700 lines) |
| `gitd/bots/common/elements.py` | `ElementResolver` — version-resilient element finding |
| `gitd/bots/common/discover_rids.py` | Semi-auto tool for extracting RIDs after TikTok updates |
| `gitd/bots/common/rid_maps/` | Version-specific RID maps (e.g., `tiktok_44.3.3.json`) |

## Element Resolution System

Separate from Device class, `elements.py` provides version-resilient element finding with a fallback chain:

```
content_desc → text → resource_id → absolute coords
```

RID maps are stored per app version in `bots/common/rid_maps/tiktok_44.3.3.json`. When TikTok updates, `discover_rids.py` helps extract new RIDs by dumping XML and comparing against known patterns.

## Key Constants (adb.py top-level)

| Constant | Value | Purpose |
|----------|-------|---------|
| `TIKTOK_PKG` | `com.zhiliaoapp.musically` | TikTok package name |
| `TIKTOK_MAIN_ACTIVITY` | `...musically/...MainActivity` | Main activity for launch |
| `KNOWN_TIKTOK_VERSION` | `44.3.3` | Expected version (warn on mismatch) |
| `RID_PROFILE_TAB` | `...musically:id/n19` | Bottom nav Profile icon |
| `RID_SEARCH_ICON` | `...musically:id/j4d` | Home screen search magnifier |
| `RID_SEARCH_BOX` | `...musically:id/gti` | Search text input field |
| `RID_USERNAME_ROW` | `...musically:id/zef` | Username in Users tab results |

## Popup Dismissal (3-tier system)

1. **Specific patterns** (`_KNOWN_POPUPS`, 10 entries): match by detect string → tap specific button
2. **Generic fallback** (`_DISMISS_WORDS`): scan clickable nodes for dismiss-like text (not now, skip, cancel, etc.), skip nodes wider than 600px (content areas)
3. **Invisible overlay**: detect "Learn more" pattern → press Back

## Known Issues & TODOs

- [ ] `type_text` only handles ASCII — use `type_unicode` for emoji/CJK (requires ADBKeyboard APK)
- [ ] `pinch_in`/`pinch_out` only move one finger (ADB `input swipe` limitation) — need `sendevent` for true multi-touch
- [ ] Portal HTTP fails silently on first call if port forward not set up — `_ensure_portal_forward` handles retry
- [ ] RIDs change with every TikTok update — need automated RID diffing
- [ ] `dismiss_popups` can false-positive on "Not now" text in regular content
- [ ] `_dismiss_draft_overlay` pixel scanning is device-resolution dependent (hardcoded thresholds)
- [ ] No built-in screen recording (separate `screenrecord` command needed)
- [ ] `wait_for` has no exponential backoff — fixed interval polling
