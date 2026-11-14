# Control Square Chess on Android with an AI agent — play chess against the computer

**Control Square Chess on Android with an AI agent.** Play chess against the computer on your phone: an agent starts a game, plays moves like e2e4, reads the position and the engine's replies, takes back or resigns.

Target search phrase: _AI agent plays chess on Android_

Demo shows: `new_game (side=white, level=3)`

> Ghost in the Droid seed skill for Square Chess (`com.dataespresso.squarechess`), an offline chess game against a built-in engine from F-Droid (DroidFish was blocked by Google Play Protect on the test phone, so this skill uses Square Chess). Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `new_game` | Start a game against the computer (white/black, level 1-9) | `side`, `level` |
| `make_move` | Play one UCI move (e2e4, e7e8q to promote) and wait for the reply | `move` |
| `make_moves` | Play several of your moves in a row | `moves` |
| `undo_move` | Take back your last move | none |
| `resign` | Resign the running game | none |
| `get_board` | Read FEN placement, status, opening, SAN moves, last move | none |

## Toolkit

An agent can drive the whole app with these; compose them.

| Role | Action |
|---|---|
| Entry | new_game |
| Primitives | make_move, make_moves, undo_move, resign |
| Read state | get_board |

## Install

The app: F-Droid, or `https://f-droid.org/packages/com.dataespresso.squarechess/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/chess
```

## Use

```bash
ghost skill run ghost/chess new_game --param side=white --device <serial>
ghost skill run ghost/chess make_moves --param moves=e2e4,g1f3,f1c4 --device <serial>
```

```python
run_skill(name="ghost/chess", action="get_board")
# {"board": {"placement": "rnbqkb1r/pppppppp/5n2/8/4P3/8/PPPP1PPP/RNBQKBNR", "status": "Your move", "opening": "B02 Alekhine Defense", "moves": ["e4", "Nf6"], "last_move": "Nf6"}}
```

Try asking: "Start a chess game as white and play the Italian opening: e2e4, g1f3, f1c4."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), Square Chess 1.4.1. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 1.4.1 | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.0 | 2026-11-02 |

### Recorded failures

- The computer's reply varies between runs: assert the move list grew and the position changed, never a specific reply.
- The accessibility tree can lag (62 of 64 squares) right after a tap or a new game: the helpers poll until all 64 are present.
- Reopening the app can leave a menu or resign dialog on top: the board subroutine closes it (Back to board / Keep playing).
- FEN has only the piece placement and the side to move (castling and en passant rights are not shown by the app).
- The SAN move list is only readable inside Menu > Move list: make_move and get_board open and close it (about 6 s extra).
- Take back asks for a confirmation ("Take back the last turn?"); against the computer both plies are removed.
- Needs the Portal build shipped with this repo; older Portal builds drop the legal-target squares while a piece is selected and moves fail.
- Portal reads take 0.5-0.9 s (plain uiautomator took 3.3 s), so actions take 10-35 s.

### Popups and first-run screens handled

- None at first launch; the menu and resign dialogs are closed by the helpers.
