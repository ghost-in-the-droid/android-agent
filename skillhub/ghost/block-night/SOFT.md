# block-night - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `pt.tiago.blocknight` (Block Night, MIT, version 0.3.10 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- Main menu: `Climb to floor 1`, Daily challenge, Free play, Settings, Statistics. Tapping Climb opens a bottom sheet with `Play`.
- Game screen header (real text): `Floor 1`, pieces left (a number above `left`), the goal `0 / 2` and `N points`. The board is a canvas.
- Controls: drag to move (about 55 px per cell at 720 px width), tap to rotate, swipe down to drop, tap HOLD to swap.
- BACK or reopening the app pauses the floor (sheet with Resume, Restart, Save and exit). Restart asks a second confirmation.
- Gravity runs in real time at speed 1, so a piece may lock by itself between two calls.

## Actions

### `start_floor()`

From any state: pause sheet > Restart > confirm, running floor > BACK > Restart > confirm, or menu > Climb > Play. Success: header shows Floor 1, pieces left and the goal.

### `play_pieces(shifts)`

start_floor, then per move: rotate taps, a slow drag of shift cells, a fast swipe down. Waits until the pieces-left counter drops (repeats the swipe if the drop was swallowed).

### `drop_piece(shift, rotate)`

Resume the floor if paused, then the same drag/rotate/drop for one piece.

### `hold_piece()`

Tap the HOLD box (top right).

### `get_progress()`

Resume the pause sheet if shown, then read the header texts. Returns floor, pieces_left, lines, lines_goal, points.

## Adapting

Other falling-block games use the same gestures; recompute the cell size from the screen width and re-find the header texts with `dump_xml`.
