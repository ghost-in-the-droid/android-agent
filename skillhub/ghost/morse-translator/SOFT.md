# morse-translator - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `rocks.poopjournal.morse` (Morse, Apache-2.0, version 13 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- Top: `buttonOne` and `buttonTwo` show the direction (TEXT to MORSE or MORSE to TEXT) with a switch between them.
- `input` (EditText) and `output` (TextView); below the output: save, flash, screen, audio and copy icons.

## Actions

### `open_translator()`

Force-stops and relaunches; on a fresh install the camera/flash permission dialog is denied.

### `translate(text, direction)`

Switches the direction if needed, clears the input, types the text and reads the output.

### `get_translation()`

Reads the TEXT/MORSE labels, the input field and the output.

### `clear_input()`

Taps the field and deletes its text.

## Adapting

The flash, screen and audio playback icons, the phrasebook and the microphone input are not driven. Morse decoding output is lower case.
