# geological-timescale - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `org.tengel.timescale` (Geological Time Scale, GPL-3.0-or-later, version 14 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- One table (Eonothem, Erathem, then System, Series and Stage as you zoom in) with the start of each unit in mya; zoom minus and plus in the toolbar.

## Actions

### `open_timescale()`

Force-stops and relaunches.

### `get_scale()`

Rebuilds the rows from the age column and the name cells that span them.

### `zoom_in()`

Taps the plus button in the toolbar.

### `zoom_out()`

Taps the minus button in the toolbar.

### `lookup_unit(name)`

Reads the table, zooms in level by level until a row name matches.

## Adapting

The end of a unit is the start of the row above it, which lookup_unit reports as end_mya (0 for the newest). Stage level may not fit one screen, rows beyond the screen are not read. Some boundary cells carry a tilde and are ignored.
