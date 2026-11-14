# sgt-puzzles - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `name.boyle.chris.sgtpuzzles` (Simon Tatham's Puzzles, MIT, version 2025-09-12 (build 149) from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- Puzzle list: one entry per puzzle (`id/text`, "Net: Rotate tiles ..."); Settings, Load, Help in the toolbar.
- Puzzle screen: toolbar title (the puzzle name), `Game` (`id/game_menu`: New game, Restart, Show solution, Load, Save, Share, Settings) and `Type` (`id/type_menu`: sizes/variants) menus, `id/status_bar` text, bottom bar with Undo/Redo (content-desc).
- The board is a canvas: not in the accessibility tree. For Net the status line reads `Active: n/25` (tiles connected to the centre) and `Auto-solved.` after Show solution. The skill taps tiles by computed coordinates (5x5 board at x 10-710, y 410-1105 on a 720 px screen).
- Choosing a Type entry starts a new board of that type.

## Actions

### `open_puzzle(name)`

Back to the puzzle list, scroll until an entry starting with `<name>:` shows, tap it. Returns the puzzle state.

### `new_game(type)`

Game > New game, or Type > <entry> when `type` is given. Success: puzzle screen, not solved.

### `tap_tile(row, col, times, size)`

Tap the computed tile centre `times` times (row/col 1-based from top left, size defaults to 5). Returns the status before and after.

### `undo_move()`

Tap the Undo button; the Active count returns.

### `show_solution()`

Game > Show solution. Success: status `Auto-solved.`

### `get_state()`

Reads `status_bar` and the toolbar title. Returns `state`.

## Adapting

The other 39 puzzles share the menus and the status line; open_puzzle, new_game, undo_move, show_solution and get_state work for them. Only tap_tile is Net specific (square grid of tiles).
