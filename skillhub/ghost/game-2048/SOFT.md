# game-2048 - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `org.secuso.privacyfriendly2048` (2048 (Privacy Friendly), GPL-3.0, version 1.4.2 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- First launch shows a 4-slide welcome (`btn_skip`). Start screen: `button_newGame`, `button_continueGame`, board-size selector (4x4).
- Game screen: `id/points`, `id/record`, `id/restartButton`; the 4x4 board is 16 Buttons (about 148 px squares, y 448-1094) whose text is the tile number (empty cells have no text).
- Moves are swipes on the board. New tiles spawn at random, so the board after a move is not predictable: the skill asserts points and tile sum, never exact tiles.
- Leaving the game with BACK keeps it: `Continue game` resumes it.

## Actions

### `new_game()`

Skip the welcome if shown, leave a running game with BACK, tap START NEW GAME. Success: 0 points and two tiles.

### `swipe(direction)`

Continue game, swipe across the board, return before/after. A blocked move changes nothing.

### `play_moves(directions)`

Swipes in order, reading points and tile sum after each. Returns the log and the final board.

### `restart()`

Tap the restart button on the board screen. Success: 0 points.

### `get_board()`

Parses the 16 cell buttons by position and the points/record texts.

## Adapting

Other 2048 clones also expose tiles as text or content-desc; reuse the grid parser and re-measure the swipe region.
