# Control Memo Game (Privacy Friendly) on Android with an AI agent — play the memory card game

**Control Memo Game (Privacy Friendly) on Android with an AI agent.** Play the memory card game on your phone: an agent starts a game, flips cards and tracks pairs, tries and time.

Target search phrase: _AI agent plays memory card game on Android_

Demo shows: `new_game (difficulty=1)`

> Ghost in the Droid seed skill for Memo Game (Privacy Friendly) (`org.secuso.privacyfriendlymemory`), a classic card-pair memory game from the SECUSO privacy-friendly apps (no permissions, no ads). Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `new_game` | Start a single-player game at difficulty 1-3 | `difficulty` |
| `flip_card` | Flip one card by row and column | `row`, `col` |
| `flip_pair` | Try a pair: flip two cards and wait for the result | `first`, `second` |
| `get_status` | Read pairs found/total, tries, time, grid size | none |

## Toolkit

An agent can drive the whole app with these; compose them.

| Role | Action |
|---|---|
| Entry | new_game |
| Primitives | flip_card, flip_pair |
| Read state | get_status |

## Install

The app: F-Droid, or `https://f-droid.org/packages/org.secuso.privacyfriendlymemory/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/memory-game
```

## Use

```bash
ghost skill run ghost/memory-game new_game --param difficulty=1 --device <serial>
ghost skill run ghost/memory-game flip_pair --param first=1,1 --param second=1,2 --device <serial>
```

```python
run_skill(name="ghost/memory-game", action="get_status")
# {"status": {"pairs_found": 1, "pairs_total": 8, "tries": 1, "time": "00:00:18", "cards": 16}}
```

Try asking: "Start a memory game and try the pairs (row 1 col 1 with row 1 col 2) and (row 2 col 1 with row 2 col 2)."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), Memo Game (Privacy Friendly) 1.1.3. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 1.1.3 | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.1 | 2026-11-06 |

### Recorded failures

- Restarting an active game opens a quit confirmation. `new_game` confirms it; read/flip actions cancel a pending quit prompt to preserve the board.
- The card faces are images with no description: the skill cannot tell which cards match; the agent must use a screenshot, the counters only confirm.
- The deal is random: never assert specific matches, only that tries went up by one.
- The timer runs while the game is open; reads of the grid are stable.
- flip_card cannot read the face of the card it just flipped (card faces are unlabeled images); only the card count and the score counters are checked.

### Popups and first-run screens handled

- The first-run welcome dialog is dismissed in the start_screen subroutine.
