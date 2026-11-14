# kfz-d - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `de.herk.kfzd` (KFZ-D, GPL-3.0-or-later, version 6 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- An EditText for the code and three blocks: District / Authority, Federal state, Type, each a label followed by a value; a footer shows the data status month.

## Actions

### `open_lookup()`

Force-stops and relaunches.

### `lookup(code)`

Clears the field, types the code and waits for the three result blocks to settle.

### `lookup_many(codes)`

Repeats lookup and collects district and state for each.

### `get_result()`

Reads the three result blocks and the data status line.

## Adapting

Results update as the code is typed (no search tap needed). A code with no match shows No match. Only the letter part of a plate is used.
