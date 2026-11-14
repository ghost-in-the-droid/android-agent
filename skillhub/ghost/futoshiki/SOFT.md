# futoshiki - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `com.hexcorp.futoshiki` (Futoshiki, GPL-3.0, version 5 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- Menu: NEW GAME, HELP, THEMES. New game: grid size (4x4, 5x5, 6x6), difficulty (EASY, MEDIUM, HARD), START. This skill supports the 4x4 grid.
- Game screen: a 4x4 grid of rounded cells (digits are text nodes), a number pad 1-4 at the bottom, RESET and a pause button, a timer. The grid appears about a second after START.
- Arrows between cells (> and ^ signs) are drawn graphics: not in the tree.

## Actions

### `new_game(difficulty)`

Force-stops, relaunches, NEW GAME > 4 x 4 > difficulty > START, then waits for the grid. Success: at least 3 digits shown and RESET visible.

### `place(row, col, digit)`

Taps the cell, then the pad digit. accepted is false when the cell is a given (it keeps its digit).

### `reset_puzzle(confirm)`

Taps RESET.

### `get_grid()`

Maps digit text nodes to cells by position.

## Adapting

To solve the puzzle an agent needs the arrows: take a screenshot after new_game. The grid read cannot tell givens from your own digits; a place on a given cell reports accepted false. rows_cols_complete checks Latin-square completeness, not the arrows.
