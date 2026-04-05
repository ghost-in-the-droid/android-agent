---
title: "📖 Device Methods"
description: Full method signatures for all 47+ Device class methods across 8 categories.
---

Complete API reference for `gitd.bots.common.adb.Device`.

## Constructor

```python
from gitd.bots.common.adb import Device

dev = Device()                           # Auto-detect (single device only)
dev = Device("YOUR_DEVICE_SERIAL")          # Specific device by serial
```

The Device stores the serial and uses it for all subsequent `adb -s <serial>` commands.

## Core Input

### adb(*args, timeout=30)

Execute a raw ADB command and return stdout as string.

```python
output = dev.adb("shell", "wm", "size")
# "Physical size: 1080x2340"

dev.adb("push", "/local/video.mp4", "/sdcard/video.mp4")
```

### adb_show(*args)

Execute ADB with live output to stdout (useful for progress bars during `adb push`).

### tap(x, y, delay=0.6)

Single tap at screen coordinates. Waits `delay` seconds after tapping.

```python
dev.tap(540, 1200)
dev.tap(540, 1200, delay=0.3)  # shorter wait
```

### swipe(x1, y1, x2, y2, ms=500, delay=0.5)

Swipe from (x1,y1) to (x2,y2) over `ms` milliseconds.

```python
dev.swipe(540, 1800, 540, 600)            # swipe up, 500ms
dev.swipe(540, 1800, 540, 600, ms=300)    # faster swipe
```

### back(delay=1.0)

Press the BACK key event.

### press_enter(delay=0.5)

Press the ENTER key event.

### long_press(x, y, duration_ms=1000, delay=0.5)

Long press via swipe to the same point with the given duration.

```python
dev.long_press(540, 1200, duration_ms=2000)  # 2-second long press
```

### type_text(text)

Type ASCII text via `adb shell input text`. Does not support emoji or unicode characters.

```python
dev.type_text("hello world")
```

## Multi-touch and Gestures

### pinch_in(cx, cy, start_dist, end_dist, duration_ms)

Pinch-to-zoom in (two fingers moving inward).

### pinch_out(cx, cy, start_dist, end_dist, duration_ms)

Pinch-to-zoom out (two fingers moving outward).

Note: Due to ADB `input swipe` limitations, only one finger moves at a time.

## Unicode and Clipboard

### type_unicode(text)

Type emoji, CJK, and other unicode characters via ADBKeyboard IME broadcast.

Flow: enable ADBKeyboard -> set as default IME -> broadcast text -> restore Gboard -> disable ADBKeyboard.

```python
dev.type_unicode("Hello! Nice to see you")
```

Requires ADBKeyboard APK installed on the device.

### clipboard_get()

Get clipboard text content (requires Android API 29+).

```python
text = dev.clipboard_get()
```

### clipboard_set(text)

Set clipboard text content.

```python
dev.clipboard_set("text to paste")
# Then paste via: dev.adb("shell", "input", "keyevent", "279")
```

## Notifications and Settings

### open_notifications(delay=0.5)

Expand the notification shade.

### close_notifications(delay=0.3)

Collapse the notification shade.

### read_notifications()

Dump XML of the notification shade (call `open_notifications()` first).

```python
dev.open_notifications()
xml = dev.read_notifications()
for node in dev.nodes(xml):
    print(dev.node_text(node))
dev.close_notifications()
```

### clear_notifications(delay=0.5)

Open notifications and tap "Clear all".

### open_settings(setting)

Open a specific Android settings page.

```python
dev.open_settings("WIFI_SETTINGS")
dev.open_settings("BLUETOOTH_SETTINGS")
dev.open_settings("DISPLAY_SETTINGS")
dev.open_settings("LOCATION_SOURCE_SETTINGS")
```

## Stealth Mode

### stealth_tap(x, y, delay=0.6)

Tap with Gaussian coordinate jitter (sigma=8px).

### stealth_swipe(x1, y1, x2, y2, ms=None, delay=0.5)

Swipe with variable speed (300-700ms) and endpoint jitter (sigma=5px).

### stealth_type(text, delay_range=(0.05, 0.2))

Character-by-character typing with random inter-keystroke delays.

```python
dev.stealth_type("hello", delay_range=(0.1, 0.4))  # slower typing
```

## XML Dump and Parsing

### dump_xml()

Get the current UI hierarchy as XML string. Tries three sources in order:

1. Portal HTTP (~33ms) -- requires Droidrun Portal APK
2. Portal content provider (~1.2s)
3. uiautomator dump (~2.0s) -- always available

```python
xml = dev.dump_xml()
```

### dump_portal_json()

Get UI hierarchy as JSON via Droidrun Portal (alternative to XML).

### bounds_center(bounds_str)

Convert bounds string `[x1,y1][x2,y2]` to center `(cx, cy)`.

```python
cx, cy = dev.bounds_center("[0,100][200,300]")
# (100, 200)
```

### find_bounds(xml, text=None, resource_id=None, content_desc=None)

Find an element's bounds string by attribute. Returns the bounds string or None.

```python
bounds = dev.find_bounds(xml, text="OK")
bounds = dev.find_bounds(xml, resource_id="com.app:id/btn")
if bounds:
    dev.tap(*dev.bounds_center(bounds))
```

### tap_text(xml, text, fallback_xy=None)

Find element by text and tap its center. Falls back to `fallback_xy` if not found.

### wait_for(text, timeout=12)

Poll `dump_xml()` until the given text appears on screen, or timeout.

```python
xml = dev.wait_for("Profile", timeout=10)
```

### nodes(xml)

Extract all `<node>` strings from the XML hierarchy.

```python
for node in dev.nodes(xml):
    print(dev.node_text(node), dev.node_rid(node))
```

### node_text(node) / node_rid(node) / node_content_desc(node)

Extract text, resource-id, or content-desc attribute from a node string.

### node_bounds(node)

Parse bounds from node string, returns `(x1, y1, x2, y2)` tuple.

### node_center(bounds)

Get center point from bounds tuple: `(cx, cy)`.

### find_nodes(xml, rid=None, text=None)

Filter nodes by resource_id and/or text. Returns list of matching node strings.

### tap_node(node, delay=0.6)

Tap the center of a node.

## TikTok Navigation

### restart_tiktok(activity=None)

Force-stop TikTok, relaunch, dismiss overlays (including invisible draft overlay).

### go_to_profile()

Restart TikTok, tap Profile tab, wait for profile screen indicators.

### go_to_drafts_screen()

Navigate from profile to the Drafts grid. Returns None if 0 drafts exist.

### search_navigate(query, tab=None)

Open search, type query, press Enter, navigate to specified tab (with retries).

### screen_type(xml)

Classify the current screen. Returns one of: `home`, `search_input`, `search_results`, `users_tab`, `filters_panel`, `unknown`.

### dismiss_popups(xml)

Auto-dismiss known TikTok popups using the 3-tier system: specific patterns (10 known) -> generic dismiss words -> invisible overlay detection.

## Utility

### check_tiktok_version()

Return installed TikTok version, warn if it does not match the known version (44.3.3).

### get_app_version(package)

Return versionName for any installed package.

### update_app(package)

Open Play Store page for the app and tap Update.

## Related

- [ADB Device Feature](/features/adb-device/) -- overview and architecture
- [API: Skill Classes](/api/skill-classes/) -- Action/Workflow classes that use Device
