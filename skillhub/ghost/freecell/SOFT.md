# freecell - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `io.github.d_rk.openpatience` (Open Patience, GPL-3.0, version 1.1.2 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- Menu: `Klondike` and `FreeCell` buttons. FreeCell variants screen: cards `Classic · 4 cells`, `2 cells · hard`, `6 cells · relaxed`, each with `Play` and `Records`.
- Game screen: every card is an accessibility node with content-desc starting with its name ("seven of hearts"). Top row: free cells (left half, y < 290) and foundations (right half); below, 8 columns spaced 87 px apart. Toolbar: `Menu`, `Undo`, `Redo`; footer: elapsed time and `N moves`.
- Tapping a card makes the app move it to its best legal place (foundation, free cell or another column): that is the single move primitive. Tapping a card in a free cell sends it back to a column.
- The deal is random every time.

## Actions

### `new_game(variant)`

Back to the FreeCell variants screen, tap Play of the chosen card. Success: 52 cards on the board and 0 moves.

### `tap_card(card)`

Find the node whose desc starts with the card name (lowest one of the pile) and tap it. Returns the board before and after.

### `tap_column(column)`

Reads the board, takes the last card of the column and taps it.

### `undo_move(redo)`

Tap the Undo/Redo toolbar button. Returns the board.

### `get_board()`

Parses every card node by position. Returns `board` with `free_cells`, `foundations`, `columns`, `moves`, `time`.

## Adapting

The Klondike mode uses the same accessible cards; reuse get_board with the stock/waste piles added. Other solitaire apps that expose card descriptions can reuse the parser.
