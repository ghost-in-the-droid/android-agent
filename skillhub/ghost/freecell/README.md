# Control Open Patience on Android with an AI agent — play FreeCell and Klondike solitaire

**Control Open Patience on Android with an AI agent.** Play FreeCell solitaire on your phone: an agent deals a game, moves cards, undoes and reads the whole board.

Target search phrase: _AI agent plays FreeCell solitaire on Android_

Demo shows: `new_game (variant=Classic)`

> Ghost in the Droid seed skill for Open Patience (`io.github.d_rk.openpatience`), a free offline solitaire collection from F-Droid (this skill plays its FreeCell). Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `new_game` | Deal a new game (Classic, 2 cells, 6 cells) and return the board | `variant` |
| `tap_card` | Tap a card by name; the app plays it to its best place | `card` |
| `tap_column` | Tap the bottom card of column 1-8 | `column` |
| `undo_move` | Undo (or redo) the last move | `redo` |
| `get_board` | Read cells, foundations, 8 columns, moves and time | none |

## Toolkit

An agent can drive the whole app with these; compose them.

| Role | Action |
|---|---|
| Entry | new_game |
| Primitives | tap_card, tap_column, undo_move |
| Read state | get_board |

## Install

The app: F-Droid, or `https://f-droid.org/packages/io.github.d_rk.openpatience/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/freecell
```

## Use

```bash
ghost skill run ghost/freecell new_game --device <serial>
ghost skill run ghost/freecell tap_column --param column=3 --device <serial>
```

```python
run_skill(name="ghost/freecell", action="get_board")
# {"board": {"free_cells": [], "foundations": ["ace of hearts"], "columns": [["five of hearts", ...], ...], "moves": 1}}
```

Try asking: "Deal a new FreeCell game, then play the bottom card of columns 3, 5 and 7."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), Open Patience 1.1.2. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 1.1.2 | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.0 | 2026-11-02 |

### Recorded failures

- The deal is random: never assert specific cards, assert 52 cards on the board and 0 moves after a deal.
- A tap moves the card to the app's chosen place; it cannot be steered to a specific column, so an agent reads the board and picks which card to tap.
- Reopening the app resumes the game in progress: new_game goes back to the variants screen first.

### Popups and first-run screens handled

- None: no first-run screens, no permissions.
