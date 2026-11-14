# calendar

Demo shows: `create_event (title=Dentist, date=2026-10-08, start_time=15:00)`

> Ghost in the Droid seed skill for Fossify Calendar (`org.fossify.calendar`), a local calendar that needs no account. Install it from F-Droid.

| Action | What it does | Params |
|---|---|---|
| `create_event` | Create an event in the local calendar | `title`, `date` (YYYY-MM-DD), `start_time` (HH:MM), `duration_min` (60), `location`, `description` |
| `list_events` | Upcoming events with ISO date, title, time | `days` (0 = all, 1 = today), `max_items` |
| `get_event` | All fields of one event, by exact title | `title` |

## Install

```bash
# the app, from the official F-Droid repo (verify the sha256 from the repo index)
curl -LO https://f-droid.org/repo/org.fossify.calendar_22.apk && adb install org.fossify.calendar_22.apk
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/calendar
```

## Use

```bash
ghost skill run ghost/calendar create_event --param "title=Team sync" --param date=2026-10-07 \
  --param start_time=10:00 --param duration_min=30 --param "location=Room 4" --device emulator-5554
ghost skill run ghost/calendar list_events --param days=7 --device emulator-5554
ghost skill run ghost/calendar get_event --param "title=Team sync" --device emulator-5554
```

From any MCP agent:

```python
run_skill(name="ghost/calendar", action="list_events", params={"days": 1})
# {"events": [{"date": "2026-10-05", "title": "Gym", "time": "11:00 PM - 11:45 PM"}], "count": 1}
```

## Tested on

Android 14 emulator (google_apis x86_64, 1080x2400, 420 dpi), Fossify Calendar 1.11.0, en-US, fresh install and reused state. Signed self-runs live in `runs/`.

## Notes

On first save the skill grants Fossify Calendar notification permission (it will not save events with reminders otherwise). It never deletes or edits existing events. License: MIT (the app itself is GPL-3.0).

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Signed self-runs (pass/total) | Dates |
|---|---|---|---|---|---|
| 1.11.0 | 14 | Google/sdk_gphone64_x86_64 (emulator, 1080x2400, 420 dpi, en-US) | 1.0.0 | 6/6 | 2026-10-05 |

Untested so far: physical devices, other OEM skins, other screen sizes, other locales.

### Recorded failures

None in the signed self-runs.

### Popups and first-run screens handled

- Notification permission (needed to save events with reminders)
- OS permission policy: {"allow_permissions": ["notifications"]}

### Other known failure modes

- Creating the same event twice makes two events; the action is not idempotent.
- Section headers carry no year; the skill assumes the next occurrence of that month.
