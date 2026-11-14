# Control Scoreboard on Android with an AI agent

**Control Scoreboard on Android with an AI agent.** Keep score on your phone: an agent adds players and rounds, enters each score and reads the totals.

Target search phrase: _AI agent keeps score for game night on Android_

Demo shows: `add_player (name=Anna)`

> Ghost in the Droid seed skill for Scoreboard (`com.github.vatbub.scoreboard`), an offline score table for game nights: players as columns, rounds as rows, totals underneath. The whole table is readable, so an agent can keep score and report who is winning. Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `add_player` | Add a player column and optionally name it | `name` |
| `add_round` | Add a round (a new row of scores) | none |
| `set_score` | Set one cell (1-based round and player) | `round`, `player`, `value` |
| `get_scores` | Read players, rounds and totals | none |

## Toolkit

An agent can drive the whole app with these; compose them.

| Role | Action |
|---|---|
| Entry | add_player |
| Primitives | add_round, set_score |
| Read state | get_scores (players, rounds, totals) |

## Install

The app: F-Droid, or `https://f-droid.org/packages/com.github.vatbub.scoreboard/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/scoreboard
```

## Use

```bash
ghost skill run ghost/scoreboard add_player --param name=Anna --device <serial>
ghost skill run ghost/scoreboard set_score --param round=1 --param player=1 --param value=7 --device <serial>
```

```python
run_skill(name="ghost/scoreboard", action="get_scores")
# {"result": {"table": {"players": ["Anna", "Ben"], "totals": ["10", "5"], ...}}}
```

Try asking: "Start a scoreboard with Anna and Ben, add two rounds and give Anna 7 and Ben 5 in round 1, then tell me who is winning."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), Scoreboard 264. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 264 | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.0 | 2026-11-02 |

### Recorded failures

- Totals are read from the app; the skill does not compute them.
- A player that is already named keeps its name (add_player names only the newest column).
- Negative or decimal scores are not supported by set_score.

### Popups and first-run screens handled

- None.
