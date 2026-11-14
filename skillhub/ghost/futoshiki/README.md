# Control Futoshiki on Android with an AI agent

**Control Futoshiki on Android with an AI agent.** Solve Futoshiki number puzzles on your phone: an agent starts a 4x4 puzzle, places digits and reads the grid.

Target search phrase: _AI agent solves Futoshiki on Android_

Demo shows: `new_game (difficulty=easy)`

> Ghost in the Droid seed skill for Futoshiki (`com.hexcorp.futoshiki`), an offline Futoshiki puzzle (a Latin square with inequality arrows). Every digit on the grid is readable; the arrows between cells are drawn only, and the given digits cannot be told from your own entries. Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `new_game` | Restart the app and start a 4x4 puzzle | `difficulty` |
| `place` | Put a digit 1-4 into a cell; reports whether the cell shows it | `row`, `col`, `digit` |
| `reset_puzzle` | Clear all your entries (needs confirm=yes) | `confirm` |
| `get_grid` | Read the 4x4 grid (0 = empty), the timer and whether rows and columns are complete | none |

## Toolkit

An agent can drive the whole app with these; compose them.

| Role | Action |
|---|---|
| Entry | new_game |
| Primitives | place, reset_puzzle |
| Read state | get_grid (digits only, NOT the inequality arrows) |

## Install

The app: F-Droid, or `https://f-droid.org/packages/com.hexcorp.futoshiki/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/futoshiki
```

## Use

```bash
ghost skill run ghost/futoshiki new_game --param difficulty=easy --device <serial>
ghost skill run ghost/futoshiki place --param row=2 --param col=2 --param digit=3 --device <serial>
```

```python
run_skill(name="ghost/futoshiki", action="place", params={"row": 2, "col": 2, "digit": 3})
# {"result": {"accepted": true, "cell_now": 3, "state": {"grid": [[3,1,0,2],[0,3,0,0],...]}}}
```

Try asking: "Start an easy Futoshiki puzzle, read the grid, then put a 3 in row 2 column 2."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), Futoshiki 5. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 5 | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.0 | 2026-11-02 |

### Recorded failures

- HONEST LIMIT: the inequality arrows are not readable from the accessibility tree; use a screenshot.
- Given digits and your entries look the same in the grid read; placing on a given cell returns accepted: false.
- Only the 4x4 grid is supported (cell positions are calibrated for it).
- There is a running timer and a pause button; the skill never taps pause.

### Popups and first-run screens handled

- None.
