# Control Simon Tatham's Puzzles on Android with an AI agent — play logic puzzles

**Control Simon Tatham's Puzzles on Android with an AI agent.** Play and auto-solve logic puzzles on your phone: an agent opens Net, rotates tiles and reads the progress.

Target search phrase: _AI agent solves logic puzzles on Android_

Demo shows: `open_puzzle (name=Net)`

> Ghost in the Droid seed skill for Simon Tatham's Puzzles (`name.boyle.chris.sgtpuzzles`), Simon Tatham's collection of 40 logic puzzles from F-Droid (this skill plays Net and can open any other puzzle). Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `open_puzzle` | Open any puzzle from the list by name (default Net) | `name` |
| `new_game` | Open Net and generate a fresh board (optionally a size/type) | `type` |
| `tap_tile` | Rotate a tile of the running Net board | `row`, `col`, `times`, `size` |
| `undo_move` | Take back the last rotation | none |
| `show_solution` | Let the app auto-solve the puzzle | none |
| `get_state` | Read screen, puzzle name, status, active/total tiles, solved | none |

## Toolkit

An agent can drive the whole app with these; compose them.

| Role | Action |
|---|---|
| Entry | open_puzzle, new_game |
| Primitives | tap_tile, undo_move, show_solution |
| Read state | get_state |

## Install

The app: F-Droid, or `https://f-droid.org/packages/name.boyle.chris.sgtpuzzles/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/sgt-puzzles
```

## Use

```bash
ghost skill run ghost/sgt-puzzles open_puzzle --param name=Net --device <serial>
ghost skill run ghost/sgt-puzzles show_solution --device <serial>
```

```python
run_skill(name="ghost/sgt-puzzles", action="get_state")
# {"state": {"screen": "puzzle", "puzzle": "Net", "status": "Active: 7/25", "active": 7, "total": 25, "solved": false}}
```

Try asking: "Open the Net puzzle, start a new game and solve it."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), Simon Tatham's Puzzles 2025-09-12 (build 149). License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 2025-09-12 (build 149) | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.0 | 2026-11-02 |

### Recorded failures

- Net boards are random: never assert the starting Active count, assert that it changes or that the status reads Auto-solved.
- The board is a canvas: tap_tile uses computed coordinates for a 5x5 board; other sizes need the size param and a visible board.
- Opening the app reopens the puzzle in progress, so the puzzle-list subroutine presses BACK first.

### Popups and first-run screens handled

- None: no first-run screens, no permissions.
