# tic-tac-toe - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `io.github.yamin8000.dooz` (Dooz, GPL-3.0, version 1.0.24 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- Header: `Game info`, `Player v Computer`, `Difficulty range: Easy`, `Game's result: Unknown | Player is the winner | Computer is the winner | draw`.
- The nine cells are clickable Views without text (about 210 px squares); the X/O marks are drawn, but an occupied cell turns **disabled** (`enabled=false`), so occupancy is readable. The Portal tree drops `enabled`, so the helpers read the plain uiautomator dump.
- Bottom bar: Undo icon (`desc="Undo"`; it did not take a move back against the computer in version 1.0.24, so it is not part of the toolkit) and the `New game` button (its label is not a text node).
- You are X; the computer answers at once with O and sometimes opens the game itself. All cells are disabled while it thinks.

## Actions

### `new_game()`

Tap the New game button (by position, its label is not exposed). Success: the Game info panel and a board with 8-9 free cells (the computer may have opened).

### `play_cell(cell)`

Tap the cell (1 top left, 5 centre, 9 bottom right), wait until the board is enabled again, diff the free cells. Returns the board and `computer_cell`; `taken: true` when the cell was not free.

### `play_cells(cells)`

New game, then each cell in turn (taken cells are reported and skipped, the loop stops when the game is over). Returns the computer's answer after every move.

### `get_board()`

Reads the nine cells' enabled state and the `Game's result` text.

## Adapting

Other tic-tac-toe apps usually draw marks on a canvas or in Views; re-find the cell bounds with `dump_xml` and read the result text. The enabled-flag trick only works when the app disables played cells.
