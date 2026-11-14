# Control Dart Checker on Android with an AI agent

**Control Dart Checker on Android with an AI agent.** Keep darts score on your phone: an agent enters each dart and reads what is left to checkout.

Target search phrase: _AI agent keeps darts score on Android_

Demo shows: `new_game (mode=301, players=1)`

> Ghost in the Droid seed skill for Dart Checker (`com.DartChecker`), an offline darts scorer for X01 games. Every control has a resource id and the scores are text, so an agent can keep score dart by dart. Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `new_game` | Restart the app and start an X01 game: mode (101 to 1001, default 301) and 1 to 8 players. | `mode`, `players` |
| `throw` | Enter one dart: 1-20, d1-d20 (double), t1-t20 (triple), bull (25), dbull (50) or miss. | `dart` |
| `throw_darts` | Enter several darts in a row, e.g. t20,t20,d10 (three darts is one turn). | `darts` |
| `end_turn` | Press continue: the remaining darts of the turn count as misses and the next player is up. | none |
| `undo` | Take back the last dart. | none |
| `get_state` | Read the scores left, the darts of the current turn, the average, the darts thrown and any message. | none |

## Toolkit

An agent can drive the whole app with these; compose them.

| Role | Action |
|---|---|
| Entry | new_game |
| Primitives | throw, throw_darts, end_turn, undo |
| Read state | get_state |

## Install

The app: F-Droid, or `https://f-droid.org/packages/com.DartChecker/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/dart-checker
```

## Use

```bash
ghost skill run ghost/dart-checker new_game --param mode=301 --device <serial>
ghost skill run ghost/dart-checker throw --param dart=t20 --device <serial>
```

```python
run_skill(name="ghost/dart-checker", action="throw", params={"dart": "t20"})
# {"result": {"dart": "t20", "state": {"scores": [241], "turn_darts": ["T20", "-", "-"]}}}
```

Try asking: "Start a 301 darts game and enter triple twenty, twenty and a miss, then tell me the score left."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), Dart Checker 49. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 49 | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.0 | 2026-11-02 |

### Recorded failures

- end_turn (continue) counts the unused darts of the turn as misses.
- The app may show messages (checkout hints, bust); they are returned in state.messages.
- Only X01 is supported; other game types are not driven.
- Do not press BACK in the app: it leaves the game.

### Popups and first-run screens handled

- None.
