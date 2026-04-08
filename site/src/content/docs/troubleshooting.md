---
title: "⚠️ Troubleshooting"
description: Common issues and solutions for ADB connections, TikTok automation, the dashboard, scheduler, and database.
---

Solutions to common problems. If your issue is not listed here, open a GitHub issue.

## ADB Connection

### "no devices/emulators found"

1. **Check USB cable** -- must be data-capable, not charge-only
2. **Check phone settings** -- Settings > Developer Options > USB Debugging must be ON
3. **Restart ADB:**
   ```bash
   adb kill-server && adb start-server && adb devices
   ```
4. **Try a different USB port** -- avoid hubs for initial setup
5. **Linux udev rules:**
   ```bash
   sudo usermod -aG plugdev $USER
   # Log out and back in
   ```

### "unauthorized"

Phone is showing a USB debugging authorization prompt. Check the phone screen, tap **Allow**, and check **Always allow from this computer**.

### "multiple devices attached"

Set the DEVICE environment variable:

```bash
export DEVICE=your_serial_here
# Find serials with: adb devices
```

### "device offline"

```bash
adb kill-server && adb start-server
# If persistent, unplug and replug USB
# Some phones need USB mode set to "File transfer"
```

## UIAutomator / XML Dumps

### "uiautomator dump failed" or empty XML

UIAutomator fails when:

1. **Screen is locked** -- wake first: `adb shell input keyevent KEYCODE_WAKEUP`
2. **App uses custom rendering** (Flutter, games, WebViews) -- UIAutomator cannot see custom-drawn elements
3. **Another UIAutomator instance is running** -- only one at a time
4. **System under load** -- wait 2 seconds and retry

```bash
# Manual test
adb shell uiautomator dump /sdcard/tt.xml && adb exec-out cat /sdcard/tt.xml | head -c 500
```

### XML dump returns stale data

UIAutomator captures a snapshot at dump time. If the screen is animating, add a sleep:

```python
import time
time.sleep(1.5)
xml = dev.dump_xml()
```

### Samsung: XML parsing errors

Samsung phones use `<node ...>...</node>` instead of self-closing tags. The parser handles this automatically. If you see errors, update to the latest `adb.py`.

## TikTok Automation

### Resource IDs changed after app update

TikTok changes resource IDs with every update. Symptoms: `find_bounds()` returns None, `screen_type()` returns "unknown", navigation fails.

**Fix:**

```python
# Check version
print(dev.check_tiktok_version())
```

If it does not match the verified version (v44.3.3), re-discover resource IDs using the Skill Creator tab or XML inspection:

```python
xml = dev.dump_xml()
for n in dev.nodes(xml):
    if "search" in dev.node_text(n).lower():
        print(dev.node_rid(n), dev.node_text(n), dev.node_bounds(n))
```

### "Continue editing" / draft resume popup

This is an invisible overlay that UIAutomator cannot see. The system detects it by scanning screenshot pixels for TikTok's red Edit button.

**If detection fails:**
1. Manually tap "Save draft" on the phone
2. Call `restart_tiktok()` before starting workflows -- it handles this automatically

### Upload fails at hashtag step

TikTok's hashtag suggestion dropdown can interfere. Each hashtag is validated in the XML before proceeding. Try shorter, more popular hashtags.

### Non-ASCII characters stripped from text input

The system strips non-ASCII (emoji, umlauts, CJK) from typed text. This is a limitation of `adb shell input text`.

**Workarounds:**
- Use ASCII-only messages
- Use clipboard: `dev.clipboard_set(text)` then paste via keyevent 279
- Use `type_unicode()` (requires ADBKeyboard IME -- increases detection risk)

### "App not installed"

```bash
adb shell pm list packages | grep musically
# Should show: package:com.zhiliaoapp.musically
```

If missing, install TikTok from the Play Store or sideload the APK.

## Dashboard

### Dashboard won't load / blank page

1. Check server is running: `curl http://localhost:5055/api/phone/devices`
2. Check browser console (F12 > Console) for JavaScript errors
3. Hard refresh: Ctrl+Shift+R
4. Check port: `lsof -i :5055`

### WebRTC stream not starting

1. Verify Portal APK is installed and accessibility enabled
2. Check scrcpy works: `scrcpy --serial <serial>`
3. Use MJPEG fallback (Phone tab > MJPEG toggle)
4. Check firewall: WebRTC uses UDP for media

### WebRTC stream goes black in certain apps

Apps like TikTok, Instagram, and banking apps set `FLAG_SECURE` on their windows, which blocks MediaProjection (WebRTC) from capturing the screen. The stream shows a black frame while the rest of the phone UI works fine.

This is enforced at the OS level and **varies by Android version** — newer versions (Android 14+) are stricter. The same app may stream fine on Android 12 but go black on Android 16.

**Workaround:** Use the toggle button (&#x21C4;) in the stream header to switch to MJPEG. MJPEG uses `adb screencap` which is not affected by FLAG_SECURE. The dashboard auto-detects black frames and shows a warning banner with a one-click switch.

### MJPEG stream intermittent / not loading on Android 14+

On some devices running Android 14–16, `adb exec-out screencap` can be unreliable — frames occasionally come back empty or the MJPEG stream freezes. This is a known issue with newer Samsung firmware and screencap permission changes.

**Things to try:**

1. **Lower the FPS** — switch to 2–3 fps instead of 5 (reduces pressure on the screencap pipeline)
2. **Toggle the stream off and on** — clears stale ADB shell sessions
3. **Restart ADB on that device:**
   ```bash
   adb -s <serial> reconnect
   ```
4. **Check developer options** — on Samsung (One UI 6+), ensure "USB debugging (Security settings)" is enabled under Developer Options (separate from regular USB debugging)
5. **Use WebRTC when possible** — it is more reliable for non-FLAG_SECURE apps since it uses a continuous MediaProjection capture rather than repeated screencap calls

### Portal not available / stream fails on all modes

The Portal app's HTTP server only runs when:

1. **The Accessibility Service is enabled** — Settings > Accessibility > Portal. Android can silently disable this after updates or battery optimization.
2. **The device screen is awake** — some devices (notably ASUS) suspend Portal's HTTP server when the display is off.

The dashboard has a **Fix** button that appears automatically when Portal issues are detected. It re-enables the accessibility service, wakes the screen, and restarts Portal. You can also fix manually:

```bash
# Re-enable accessibility service
adb -s <serial> shell settings put secure enabled_accessibility_services \
  com.droidrun.portal/.service.DroidrunAccessibilityService
adb -s <serial> shell settings put secure accessibility_enabled 1

# Wake screen
adb -s <serial> shell input keyevent KEYCODE_WAKEUP
```

### Tables not loading / slow

Large datasets cause slow initial loads. The dashboard uses virtual scrolling. If completely broken, check browser console.

## Scheduler

### Jobs stuck in "running" state

If a subprocess crashed without cleanup:

1. Check process: `ps aux | grep python3`
2. Kill orphans: `kill <pid>`
3. The scheduler auto-detects dead processes on its next tick (30 seconds)
4. Or kill via API: `curl -X POST http://localhost:5055/api/scheduler/queue/<id>/kill`

### Jobs not starting on schedule

1. Verify schedule exists and is enabled (Scheduler tab)
2. Check `interval_minutes` is correct
3. Scheduler ticks every 30 seconds -- jobs may start up to 30 seconds late
4. One job per phone: if a long job is running, the next one queues

### Preemption not working

Preemption requires:
1. New job has higher priority than running job
2. Running job has been active for at least 90 seconds (grace period)
3. Running job type is not `post` or `publish_draft` (protected)

## Database

### "database is locked"

SQLite locks under concurrent writes. The system uses WAL mode to minimize this.

1. Ensure only one server instance is running
2. Close any SQLite browsers (DB Browser, etc.)
3. Restart the server

### Schema migration errors

Migrations auto-apply on startup. If one fails:

1. Back up: `cp data/gitd.db data/gitd.db.bak`
2. Check the error -- "column already exists" errors are harmless (idempotent)
3. Restart the server

### Restore from backup

```bash
# Stop server first
cp data/gitd.db.bak data/gitd.db
python3 run.py
```

## Performance

### Automation is slow (>1s per action)

Each ADB command spawns a subprocess. Normal latency:

| Operation | Time |
|-----------|------|
| `adb shell input tap` | 100-200ms |
| `uiautomator dump` + read | 300-500ms |
| Full step (dump + find + tap + wait) | 1-2 seconds |

To speed up:
- Reduce post-action delays if your phone is fast
- Use `find_bounds()` with resource_id instead of text
- Reuse the last `dump_xml()` when possible

### Server using too much memory

Large datasets load into the browser. Use filters to reduce visible data. Close inactive tabs.

## Still Stuck?

1. **Check logs:** `/tmp/tiktok_*.log` and `/tmp/sched_job_*.log`
2. **Dump screen state:** `dev.dump_xml()` and inspect the XML
3. **Take a screenshot:** `adb exec-out screencap -p > screen.png`
4. **Open an issue** with: error message, device info, app version, and steps to reproduce
