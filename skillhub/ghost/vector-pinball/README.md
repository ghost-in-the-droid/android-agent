# Control Vector Pinball on Android with an AI agent

**Control Vector Pinball on Android with an AI agent.** Play pinball on your phone: an agent picks a table, launches the ball and works the flippers.

Target search phrase: _AI agent plays pinball on Android_

Demo shows: `start_game (side=both, times=6)`

> Ghost in the Droid seed skill for Vector Pinball (`com.dozingcatsoftware.bouncy`), a free vector-graphics pinball game from F-Droid that runs fully offline. Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `start_game` | Start a game on the chosen table and launch the ball | `table_steps`, `unlimited_balls` |
| `flip` | Hit the left, right or both flippers N times | `side`, `times` |
| `end_game` | End the running game and return to the main menu | none |
| `select_table` | Step to the next/previous table on the main menu | `steps` |
| `get_status` | Read state (menu, playing, paused), table label and high scores | none |

## Toolkit

An agent can drive the whole app with these; compose them.

| Role | Action |
|---|---|
| Entry | start_game |
| Primitives | flip, select_table, end_game |
| Read state | get_status |

## Install

The app: F-Droid, or `https://f-droid.org/packages/com.dozingcatsoftware.bouncy/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/vector-pinball
```

## Use

```bash
ghost skill run ghost/vector-pinball start_game --device <serial>
ghost skill run ghost/vector-pinball flip --param side=both --param times=6 --device <serial>
```

```python
run_skill(name="ghost/vector-pinball", action="get_status")
# {"status": {"state": "playing"}}
```

Try asking: "Start a pinball game and hit both flippers a few times."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), Vector Pinball 1.16.0. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 1.16.0 | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.0 | 2026-11-02 |

### Recorded failures

- The score is painted, not text: get_status cannot return it. It reports the state and high scores only.
- Reopening the app pauses nothing, but a running game hides the menus: every action first reaches the main menu (pause > END GAME).
- Gameplay is real time: flips are fire-and-forget taps, the ball may drain between calls.

### Popups and first-run screens handled

- None: no first-run screens, no permissions.
