# Control Navy Fleet Battle on Android with an AI agent

**Control Navy Fleet Battle on Android with an AI agent.** Let your agent play Battleship against the computer on your phone: it starts a game, calls its shots and reports what happened.

Target search phrase: _AI agent plays Battleship on Android_

Demo shows: `fire (cell=B5)`

> Ghost in the Droid seed skill for Navy Fleet Battle (`net.tigr.navyfleetbattle`), the classic sea battle game against the computer. The fields are drawn on a canvas, but the turn, hit messages and ship counters are text, so an agent can aim and track the game. Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `open_menu` | Restart the app and read the start menu. | none |
| `new_game` | Start a new game against the computer with random ship placement. | none |
| `fire` | Fire at one cell (letter A-J and number 1-10) and return hit, sunk, miss or game over. | `cell` |
| `fire_many` | Fire at several cells in a row (comma separated, up to 20) and return the result of each. | `cells` |
| `get_state` | Read the turn, the hint line and how many enemy and own ships of each size are left (battleship, cruiser, destroyer, boat). | none |

## Toolkit

An agent can drive the whole app with these; compose them.

| Role | Action |
|---|---|
| Entry | open_menu, new_game |
| Primitives | fire, fire_many |
| Read state | get_state |

## Install

The app: F-Droid, or `https://f-droid.org/packages/net.tigr.navyfleetbattle/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/navy-fleet-battle
```

## Use

```bash
ghost skill run ghost/navy-fleet-battle fire --param cell=B5 --device <serial>
```

```python
run_skill(name="ghost/navy-fleet-battle", action="fire", params={"cell": "B5"})
```

Try asking: "Start a Navy Fleet Battle game against the computer and fire at B5, C3 and E5."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), Navy Fleet Battle 8. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 8 | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.0 | 2026-11-02 |

### Recorded failures

- Firing at a cell twice is refused.
- Placement is random, so a run cannot predict hits.

### Popups and first-run screens handled

- None.
