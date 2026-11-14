# easy-notes - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `com.kin.easynotes` (Easy Notes, GPL-3.0-only, version 14 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- List: search field, note cards (title and preview), New Note button. Editor: Name and Description fields and a Done check. Note view: title and body with a Back arrow.

## Actions

### `open_notes()`

Force-stops and relaunches.

### `create_note(title, text)`

Taps New Note, types into Name and Description, checks both fields, taps Done and finds the note in the list.

### `list_notes()`

Reads the note cards.

### `read_note(title)`

Taps the card, reads the view, goes back with the in-app Back arrow.

### `search_notes(query)`

Searches the list and clears the search field again.

## Adapting

Deleting a note from its view crashes the app (it reloads the deleted note), so the skill does not delete; clear the app data to remove test notes. Keep titles and text short plain text.
