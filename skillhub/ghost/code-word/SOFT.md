# code-word - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `com.peaceray.codeword` (Code Word, GPL-3.0, version 1.4.4 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- Game screen: 6 rows of 5 tiles from y 286 (pitch 123 px). Typed letters are `textView` nodes (blank tiles are a space); the keyboard keys are `keyTextView`; the submit key is the right-most FrameLayout of the bottom row. `action_puzzle_info` opens the puzzle dialog whose NEW PUZZLE button leads to a Daily/Seeded/Custom screen with a PLAY button (`createPuzzleButton`) and the seed.
- Tile colours (right place / elsewhere / absent) are not exposed; only a screenshot shows them.

## Actions

### `new_puzzle()`

Puzzle Info > NEW PUZZLE > PLAY with the default settings. Success: empty board, keyboard visible.

### `guess(word)`

Taps each letter key, then the submit key. accepted is true when the typed row appears in the board; a non-word is rejected by the app and the row stays empty.

### `get_board()`

Reads the letter tiles row by row.

## Adapting

To use the feedback an agent needs vision: take a screenshot after each guess (blue/green = right place, yellow = elsewhere, grey = absent).
