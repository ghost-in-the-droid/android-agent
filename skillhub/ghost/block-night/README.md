# Control Block Night on Android with an AI agent — play falling-block puzzles

**Control Block Night on Android with an AI agent.** Play a polished falling-blocks puzzle: an agent starts a floor, moves, rotates and drops pieces and reads progress.

Target search phrase: _AI agent plays Tetris-style game on Android_

Demo shows: `start_floor (shifts=-3,3,0)`

> Ghost in the Droid seed skill for Block Night (`pt.tiago.blocknight`), a polished offline falling-blocks puzzle from F-Droid (every floor is a fixed set of pieces and a goal). Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `start_floor` | Start (or restart) floor 1 and return the starting progress | none |
| `play_pieces` | Fresh floor, then drop several pieces by cell shift (`2`, `-1`, `2r1` = shift 2 and rotate once) | `shifts` |
| `drop_piece` | Move/rotate and drop the current piece on the running floor | `shift`, `rotate` |
| `hold_piece` | Swap the falling piece with the held one | none |
| `get_progress` | Read floor, pieces left, lines done and goal, points | none |

## Toolkit

An agent can drive the whole app with these; compose them.

| Role | Action |
|---|---|
| Entry | `start_floor` |
| Primitives | `drop_piece`, `hold_piece`, `play_pieces` |
| Read state | `get_progress` |

## Install

The app: F-Droid, or `https://f-droid.org/packages/pt.tiago.blocknight/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/block-night
```

## Use

```bash
ghost skill run ghost/block-night start_floor --device <serial>
ghost skill run ghost/block-night drop_piece --param shift=2 --device <serial>
```

```python
run_skill(name="ghost/block-night", action="get_progress")
# {"progress": {"floor": "Floor 1", "pieces_left": 6, "lines": 0, "lines_goal": 2, "points": 82}}
```

Try asking: "Start the first floor in Block Night and drop three pieces: one to the left, one to the right and one in the middle."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), Block Night 0.3.10. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 0.3.10 | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.0 | 2026-11-02 |

### Recorded failures

- Piece gravity runs in real time: a piece can lock between two calls, so assert 'at least N pieces used' rather than exact counts.
- A drop right after a drag is sometimes swallowed as one gesture: the helper repeats the swipe if the counter did not drop.
- Restart asks a second confirmation ('Restart this floor?'); the subroutine handles both sheets.
- Points vary slightly between runs (timing), so they are never asserted.

### Popups and first-run screens handled

- The pause sheet and the restart confirmation are handled inside the subroutine; no other first-run screens.
