# Control Dooz on Android with an AI agent — play tic-tac-toe

**Control Dooz on Android with an AI agent.** Play noughts and crosses against the computer on your phone: an agent starts a game, marks cells and reads the board.

Target search phrase: _AI agent plays tic-tac-toe on Android_

Demo shows: `new_game (cells=1,5,9)`

> Ghost in the Droid seed skill for Dooz (`io.github.yamin8000.dooz`), a simple offline tic-tac-toe game against the computer from F-Droid. Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `new_game` | Start a new game against the computer | none |
| `play_cell` | Mark one cell 1-9 and read the computer's answer | `cell` |
| `play_cells` | New game, then mark several cells in order | `cells` |
| `get_board` | Read free/occupied cells, result and difficulty | none |

## Toolkit

An agent can drive the whole app with these; compose them.

| Role | Action |
|---|---|
| Entry | new_game |
| Primitives | play_cell, play_cells |
| Read state | get_board |

## Install

The app: F-Droid, or `https://f-droid.org/packages/io.github.yamin8000.dooz/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/tic-tac-toe
```

## Use

```bash
ghost skill run ghost/tic-tac-toe new_game --device <serial>
ghost skill run ghost/tic-tac-toe play_cell --param cell=5 --device <serial>
```

```python
run_skill(name="ghost/tic-tac-toe", action="get_board")
# {"board": {"free": [2, 4, 6, 7, 8, 9], "occupied": [1, 3, 5], "result": "Unknown", "game_over": false}}
```

Try asking: "Play tic-tac-toe: take the top left, then the centre, then the bottom right."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), Dooz 1.0.24. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 1.0.24 | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.0 | 2026-11-02 |

### Recorded failures

- The computer sometimes opens the game (and may take the centre): play_cell reports `taken: true` instead of failing.
- The board is fully disabled while the computer thinks: the helpers wait until a read is stable and not all-disabled.
- The Portal accessibility tree drops the `enabled` attribute, so the helpers read the plain uiautomator dump.
- Undo did not take a move back against the computer, so the skill has no undo action.

### Popups and first-run screens handled

- None: the app has no first-run screens and asks for no permissions.
