# decisions - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `de.markusfisch.android.libra` (Decisions, MIT, version 25 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- Issue list with an add button, an issue screen with a balance (orange against, green for), argument chips, a weight row from 10 on the left to 10 on the right and an argument field with a save button.

## Actions

### `open_issues()`

Force-stops and relaunches.

### `new_issue(title)`

Taps add, renames the issue through the pencil dialog and confirms.

### `add_argument(text, weight)`

Types the argument, taps the weight number on the scale row and saves.

### `get_issue()`

Reads the title and the argument chips; the side comes from the chip position.

### `list_issues()`

Navigates up from the issue and reads the list rows.

## Adapting

The weight number and the balance totals are drawn on a canvas, not in the accessibility tree: the skill reads a chip's side (pro, con, neutral) from its position and echoes the weight it set, but cannot read the weight back. Pass weight 0 for a neutral argument. Texts are typed through adb, so keep them plain.
