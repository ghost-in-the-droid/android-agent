# daily-diary - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `com.voklen.daily_diary` (Daily Diary, GPL-3.0-only, version 17 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- Header: title, a list button (previous entries) and a settings button. Body: one EditText holding today's entry. Previous-entries screen has a Back button.

## Actions

### `open_diary()`

Force-stops and relaunches.

### `write_entry(text)`

Selects all, deletes, types the text and reads it back. Replaces, does not append.

### `append_entry(text)`

Reads the entry, then rewrites it with the new text after a space (the field is cleared with select-all and retyped).

### `read_entry()`

Reads the entry field.

### `list_previous()`

Uses the in-app Back button, never the system key. A fresh install has no older days, so the list is empty.

## Adapting

The app keeps one page per day and autosaves. Text is typed through adb input, so keep entries short plain text (no emoji). Test entries live in the app only and are removed by clearing the app data.
