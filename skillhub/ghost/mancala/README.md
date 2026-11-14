# Control Mancala on Android with an AI agent

**Control Mancala on Android with an AI agent.** Play Mancala on your phone: an agent sets up a game, sows pits for each player and reads the board and the winner.

Target search phrase: _AI agent plays Mancala on Android_

Demo shows: `move (pit=3)`

> Ghost in the Droid seed skill for Mancala (`com.willie.mancala`), an offline two-player Mancala (Kalah) game played in a text console. The transcript is fully readable, so the board, both stores, whose turn it is and the winner are parsed exactly. Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `new_game` | Restart and set up a game (default 6 pits, 4 seeds) | `pits`, `seeds` |
| `move` | Sow one pit for whoever is to move; returns the board, stores and next player | `pit` |
| `play_moves` | Play several pits in a row (3,1,5) | `pits` |
| `get_state` | Read both rows, both stores, whose turn it is and the result | none |

## Toolkit

An agent can drive the whole app with these; compose them.

| Role | Action |
|---|---|
| Entry | new_game |
| Primitives | move, play_moves |
| Read state | get_state (rows, stores, to_move, game_over, result) |

## Install

The app: F-Droid, or `https://f-droid.org/packages/com.willie.mancala/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/mancala
```

## Use

```bash
ghost skill run ghost/mancala new_game --param pits=6 --param seeds=4 --device <serial>
ghost skill run ghost/mancala move --param pit=3 --device <serial>
```

```python
run_skill(name="ghost/mancala", action="move", params={"pit": 3})
# {"result": {"player": 1, "extra_turn": true, "state": {"player1_store": 1, ...}}}
```

Try asking: "Start a Mancala game and play pits 3, 1 and 5."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), Mancala 12. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 12 | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.0 | 2026-11-02 |

### Recorded failures

- Hot-seat game: no computer opponent; the agent plays both sides.
- After the game ends the app asks whether to start another game; new_game restarts the app instead of answering it.
- Never type exit: it quits the app (the skill refuses to type unless the console is on screen).
- The transcript prints an Invalid input line after each prompt; it is app noise and is ignored.

### Popups and first-run screens handled

- None.
