# Control 2048 (Privacy Friendly) on Android with an AI agent

**Control 2048 (Privacy Friendly) on Android with an AI agent.** Play 2048 on your phone: an agent swipes the tiles and reads the board and the score.

Target search phrase: _AI agent plays 2048 on Android_

Demo shows: `new_game (directions=left,up,left,down,left,up)`

> Ghost in the Droid seed skill for 2048 (Privacy Friendly) (`org.secuso.privacyfriendly2048`), the classic 2048 puzzle from the SECUSO privacy-friendly apps (no permissions, no ads). Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `new_game` | Start a new 4x4 game and return the board | none |
| `swipe` | Swipe left/right/up/down once on the game in progress | `direction` |
| `play_moves` | New game, then a sequence of swipes | `directions` |
| `restart` | Restart the running game | none |
| `get_board` | Read the grid, points, record, tile sum, max tile, game over | none |

## Toolkit

An agent can drive the whole app with these; compose them.

| Role | Action |
|---|---|
| Entry | new_game |
| Primitives | swipe, play_moves, restart |
| Read state | get_board |

## Install

The app: F-Droid, or `https://f-droid.org/packages/org.secuso.privacyfriendly2048/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/game-2048
```

## Use

```bash
ghost skill run ghost/game-2048 new_game --device <serial>
ghost skill run ghost/game-2048 swipe --param direction=left --device <serial>
```

```python
run_skill(name="ghost/game-2048", action="get_board")
# {"board": {"grid": [[2,0,0,0],[8,2,0,0],[0,0,0,0],[0,0,0,0]], "points": 16, "record": 16, "max_tile": 8}}
```

Try asking: "Start a new 2048 game and swipe left, up, left, down, left, up."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), 2048 (Privacy Friendly) 1.4.2. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 1.4.2 | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.0 | 2026-11-02 |

### Recorded failures

- Tiles spawn at random: never assert exact tiles, assert points >= before and tile sum >= before.
- A swipe that cannot move changes nothing; the helper still reports before/after.
- The record survives restarts but not `pm clear`.
- The welcome slides only show on the first launch after install or clear (SKIP is handled).

### Popups and first-run screens handled

- The first-run welcome (btn_skip) is handled in the open_menu subroutine.
