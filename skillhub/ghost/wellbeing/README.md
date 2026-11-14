# wellbeing

Demo shows: `get_screen_time_today (no params)`

> Ghost in the Droid seed skill for Digital Wellbeing (`com.google.android.apps.wellbeing`). Preinstalled, no account.

| Action | What it does | Params |
|---|---|---|
| `get_screen_time_today` | Screen time, unlocks, notifications today | none |
| `list_app_usage` | Per-app usage today, with timers | `limit` (default 20) |
| `set_app_timer` | Daily app timer, multiple of 5 minutes | `app`, `minutes` |
| `remove_app_timer` | Delete an app's daily timer | `app` |

## Install

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/wellbeing
```

## Use

```bash
ghost skill run ghost/wellbeing get_screen_time_today --device emulator-5554
ghost skill run ghost/wellbeing set_app_timer --param app=Clock --param minutes=45 --device emulator-5554
ghost skill run ghost/wellbeing remove_app_timer --param app=Clock --device emulator-5554
```

From any MCP agent:

```python
run_skill(name="ghost/wellbeing", action="list_app_usage", params={"limit": 3})
# {"apps": [{"app": "Settings", "used": "11 minutes", "timer": null, "timer_allowed": false}, ...]}
```

## Tested on

Android 14 emulator (google_apis x86_64, 1080x2400, 420 dpi), Digital Wellbeing 1.6, en-US. Signed self-runs live in `runs/`.

## Notes

An expired timer pauses the app until midnight; `remove_app_timer` undoes `set_app_timer`. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Signed self-runs (pass/total) | Dates |
|---|---|---|---|---|---|
| 1.6.521068621 | 14 | Google/sdk_gphone64_x86_64 (emulator, 1080x2400, 420 dpi, en-US) | 1.0.0 | 8/8 | 2026-10-05 |

Untested so far: physical devices, other OEM skins, other screen sizes, other locales.

### Recorded failures

None in the signed self-runs.

### Popups and first-run screens handled

- Notification permission prompt

### Other known failure modes

- Apps that were not used today are not listed and cannot get a timer from the Dashboard.
- Pixel builds with Bedtime and Focus mode set up show more cards on the overview; the ids above are unchanged.
