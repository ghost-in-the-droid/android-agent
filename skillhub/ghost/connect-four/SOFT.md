# connect-four - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `io.github.patrickric.connectfourstudio` (ConnectFour Studio, GPL-3.0, version 1.0.1 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- The board is drawn on a canvas and is **not** in the accessibility tree: a move is one tap inside the column (x from the 7-column grid, y at about 31% of the screen height).
- Real TextViews: `id/status` ("New game.", "Computer is thinking...", "Computer played N in ..."), `id/turn_text` (side to move), and the Info panel pairs (`Move:` then its number). Buttons: `New`, `<<`, `<`, `>`, `>>`, `Move`, `Analyze`.
- The engine plays at level 14 Perfect with an opening book. Its reply varies between equally good moves, so replies differ from run to run; the skill never asserts a specific reply column.
- Right after a tap or New the labels lag behind the board, so the helpers read the state twice until it is stable.

## Actions

### `new_game()`

Tap `New` (no confirmation). Success: status "New game." and the move counter is 1.

### `play_column(column)`

Tap the column, wait until the status reads "Computer played N" and the move counter rose by 2. Returns the before and after state.

### `play_moves(columns)`

New game, then each column in turn, waiting for the reply each time. Returns the reply after every move and the final state.

### `get_state()`

Reads `Move:`, `turn_text` and `status` from the screen.

### `undo_move()`

Tap `<`; the move counter drops. Returns the state before and after.

## Adapting

Other Connect Four apps differ in the controls but usually expose a status line. The canvas board means moves are coordinate taps; recompute the column centres from the board width.
