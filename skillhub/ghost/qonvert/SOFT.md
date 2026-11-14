# qonvert - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `org.tessoft.qonvert` (Qonvert, GPL-3.0-only, version 12 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- Output row: `outBaseText`, buttons BIN OCT DEC DOZ HEX STD (`outToggleButton2/8/10/12/16`), then `textOutput0..n`.
- Input row: `inBaseText`, the same base buttons (`inToggleButton*`), `editInput`, `clearButton`.

## Actions

### `open_converter()`

Force-stops and relaunches.

### `convert(value, from_base, to_base)`

Taps the input and output base buttons, clears the field, types the number and reads the output rows.

### `get_result()`

Reads editInput, inBaseText, outBaseText and textOutput rows.

### `clear_input()`

Taps the clear button.

## Adapting

Only the standard (STD) positional systems BIN, OCT, DEC, DOZ and HEX are driven; the complement, DMS and nega-base options keep their defaults.
