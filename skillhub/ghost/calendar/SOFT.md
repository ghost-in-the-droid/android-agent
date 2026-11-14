# calendar - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on, and how success is recognised, so an agent can adapt it to another calendar app.

**Package**: `org.fossify.calendar` (Fossify Calendar 1.11.0 from f-droid.org, sha256 verified against the repo index)
**Verified**: 2026-10-05 on a headless emulator pool, Android 14 google_apis x86_64, 1080x2400 @ 420 dpi, en-US, device time zone CEST, no account.
**Skill class**: HARD. No login, no checkpoints.

## Why this app

Google Calendar needs a Google account. Fossify Calendar keeps a "Local calendar" ("Offline (never synced)") and works on a fresh device.

## Landmarks

- Main screen toolbar: `id/top_toolbar_search`, `id/change_view` (menu: Daily, Weekly, Monthly, ..., `Simple event list`), `id/settings`, FAB `id/calendar_fab` (`New Event`).
- Simple event list: `id/event_section_title` headers (`OCTOBER`, then `6 Tuesday`), rows with `id/event_item_title` and `id/event_item_time` (`03:00 PM - 04:00 PM`). The view choice is remembered by the app.
- Editor (`EventActivity`): `id/event_title`, `id/event_location`, `id/event_description` (placeholders `Location`, `Description` when empty), `id/event_start_date`, `id/event_start_time`, `id/event_end_date`, `id/event_end_time`, `id/event_reminder_1`, `id/event_repetition`, `id/event_calendar_title`, `id/save`.
- Dialog buttons use the framework id `android:id/button1`.

## Actions

### `create_event(title, date, start_time, duration_min, location, description)`

1. Convert date and time to epoch on the device (`date -d`), so the device time zone applies.
2. Force-stop the app, then fire `android.intent.action.INSERT` with data `content://com.android.calendar/events` and extras `title`, `beginTime`, `endTime` (longs, ms), `eventLocation`, `description`. Only a fresh editor reads the extras; a running one ignores them.
3. Tap Save. First save on a new install shows a reminder `Disclaimer` (`OK`) and the Android 14 notification permission (`Allow`); without notification permission Fossify refuses to save an event that has a reminder.
4. Success: the editor closed and the event appears in the simple list under the right date.

### `list_events(days, max_items)`

Switch to the simple event list and walk it: `{events: [{date (ISO), title, time}], count}`. `days=1` keeps only today. Upcoming only; past events are not listed by this view.

### `get_event(title)`

Search by title, open the first row with that exact title, read every editor field, press BACK (no changes, so no discard prompt).

## Failure modes

- Creating the same event twice makes two events; the action is not idempotent.
- Section headers carry no year; the skill assumes the next occurrence of that month.
