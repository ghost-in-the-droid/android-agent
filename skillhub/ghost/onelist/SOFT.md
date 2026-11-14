# onelist - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `com.lolo.io.onelist` (1List, MIT, version 22 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- Top: app title, Settings, import and + (create list). Below: one tab per list (a fresh install has Tutorial and TODO).
- Input field with an add button above the items; each item is a row of text (swipe left to delete, swipe right to edit, tap to mark done).

## Actions

### `open_lists()`

Force-stops and relaunches.

### `create_list(name)`

Taps the + button, types the name and taps Save.

### `select_list(name)`

Taps the list tab at the top.

### `add_item(item)`

Types into the input field above the items and taps the add button.

### `remove_item(item)`

Swipes the item row to the left; the app shows an Undo bar for a few seconds.

### `get_items()`

Reads the tabs and the item rows.

## Adapting

The done (strikethrough) state is not exposed in the accessibility tree, so items are not toggled or read as done. Only the item text is handled. The currently selected tab is not exposed either.
