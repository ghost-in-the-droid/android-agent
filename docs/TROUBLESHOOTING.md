# Troubleshooting

---

## Server Won't Start

**Check `.env` exists:**
```bash
cp .env.example .env   # if missing
```

**Check dependencies:**
```bash
pip install -e ".[all]"
```

**Port conflict:**
```bash
lsof -i :5055
# Kill the conflicting process or change port in run.py
```

**Import errors:**
```bash
python3 -c "from gitd.app import app; print('OK')"
# Shows the exact import error if something is missing
```

---

## API Returns 500

Check the terminal where `python3 run.py` is running -- FastAPI logs the full traceback there.

**SQLite WAL lock:**
Only one server instance can write at a time. Ensure no other `run.py` process or SQLite browser (DB Browser, etc.) has the file open.

```bash
# Find other processes using the DB
fuser data/gitd.db
```

**Database schema drift:**
```bash
alembic upgrade head    # apply pending migrations
```

---

## Frontend Can't Reach API

The Vite dev server proxies `/api/*` to the backend. If API calls fail:

1. Verify backend is running: `curl http://localhost:5055/api/health`
2. Check `frontend/vite.config.ts` -- the proxy target should be `http://localhost:5055`
3. If running backend on a different port, update the proxy target

---

## ADB Connection Issues

**"no devices/emulators found":**
```bash
adb kill-server && adb start-server && adb devices
```
- Check USB cable is data-capable (not charge-only)
- Try a different USB port
- On Linux: `sudo usermod -aG plugdev $USER` (then logout/login)

**"unauthorized":**
Check the phone screen for the USB debugging prompt and tap **Allow**.

**"device offline":**
Unplug and replug USB. Set USB mode to "File transfer" (not "Charging only").

---

## WebRTC Not Connecting

1. Portal app must be installed and running on the device
2. Check ADB reverse is set up: the server does this automatically via `/api/phone/webrtc-signal`
3. Fallback to MJPEG streaming (Phone Agent tab > MJPEG button)
4. Check that no firewall is blocking UDP ports (WebRTC uses UDP for media)

---

## Skill Install Fails

```bash
# Check network access to the registry
curl -s https://raw.githubusercontent.com/ghost-in-the-droid/skills/main/registry.json | head -20

# Verify skill CLI works
android-agent skill list
```

If installing from a GitHub URL, ensure the repo is public and contains a valid `skill.yaml`.

---

## Tests Fail

**API smoke tests (`tests/api/`):**
These don't need a phone. If they fail:
```bash
pip install -e ".[test]" httpx
pytest tests/api/test_smoke.py -v --tb=long
```

**Device tests (`tests/test_0*.py`):**
These require a connected phone. The root `tests/conftest.py` creates a `Device` fixture:
```bash
# Must specify a device
DEVICE=<serial> python3 -m pytest tests/test_00_baseline.py -v
```

If you only want API tests (no device), run `tests/api/` explicitly.

---

## TikTok Resource IDs Changed

TikTok changes resource IDs with app updates. Symptoms: `find_bounds()` returns None, `screen_type()` returns "unknown".

1. Check version: `adb shell dumpsys package com.zhiliaoapp.musically | grep versionName`
2. Use the **Skill Creator** tab to inspect elements visually
3. Or dump XML and search manually:
   ```bash
   adb shell uiautomator dump /sdcard/tt.xml && adb exec-out cat /sdcard/tt.xml
   ```

---

## Jobs Stuck in "running"

If a bot subprocess crashes without cleanup:
1. The scheduler daemon auto-detects dead processes on its next 30-second tick
2. If persistent, restart the server: kill `run.py` and start again
3. Check for orphaned processes: `ps aux | grep python3`

---

## Still Stuck?

1. Check logs in the terminal running `python3 run.py`
2. Check bot logs: `/tmp/tiktok_*.log`, `/tmp/sched_job_*.log`
3. Take a screenshot: `adb exec-out screencap -p > screen.png`
4. Open a GitHub issue with: error message, device info, app version, steps to reproduce
