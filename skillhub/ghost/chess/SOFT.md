# chess - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `com.dataespresso.squarechess` (Square Chess, GPL-3.0, version 1.4.1 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- Home list: `Play against computer`, Puzzles, Over the board, Record physical game, Chess clock. The new-game dialog has a level slider (9 dots at x 122 + 52.7 per level, y 458), `White`/`Black`, hints and evaluation checkboxes and `Start game`.
- Board: every one of the 64 squares is a node with content-desc `e2, white pawn` or `a6, empty` (squares become readable text). A move is two taps: from-square, then to-square.
- Header: status (`Your move`, `Game over`) plus the opening name on a second line; the SAN move list is real text ("1. e4 Nf6"); `Menu` opens Undo / take back, Resign, Review game, Move list, Flip board, Share FEN/PGN, Save & home.
- The computer answers by itself within a second or two at low levels; as black it opens.
- Needs a Portal build that keeps legal-target squares while a piece is selected (the Portal APK shipped with this repo does): older builds dropped them (`e4, empty, legal destination`). a piece is selected, older Portal builds dropped the legal-target squares (`e4, empty, legal destination`); the helpers now read the Portal tree only.

## Actions

### `new_game(side, level)`

Home > Play against computer > set the level slider and side > Start game. As black the computer opens.

### `make_move(move)`

Tap the from square, then the to square, wait until the status is Your move again and the position changed. Returns before/after board and the computer's reply (SAN).

### `make_moves(moves)`

make_move for each UCI move; stops when the game is over. Returns the reply after each.

### `undo_move()`

Menu > Undo / take back. Fails with a clear error when no move was played.

### `resign()`

Menu > Resign > confirm. The game stays in the app's history.

### `get_board()`

Parses the 64 square descriptions and the header/move list.

## Adapting

Any chess app that labels squares (or pieces) in the accessibility tree can reuse the parser; otherwise map square bounds from the board frame. SAN input would need a move generator: the skill takes UCI squares on purpose.
