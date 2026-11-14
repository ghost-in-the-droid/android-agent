# Control Reckoning Skills on Android with an AI agent

**Control Reckoning Skills on Android with an AI agent.** Want to test how fast an AI does mental maths? Your agent plays a game on your phone and reads the score.

Target search phrase: _AI agent plays a mental arithmetic game on Android_

Demo shows: `answer (value=7)`

> Ghost in the Droid seed skill for Reckoning Skills (`org.secuso.privacyfriendlyrecknoningskills`), an offline mental arithmetic trainer from the Privacy Friendly Apps. The problem, the keypad, the progress and the result rows are text nodes, so an agent can play a full 10 problem game. Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `open_menu` | Restart the app, skip the first-run tutorial and land on the game menu. | none |
| `new_game` | Start a new 10 problem game and return the first problem. | none |
| `get_problem` | Read the current problem, the progress (i of 10) and what is typed so far. | none |
| `answer` | Type a whole number on the keypad and confirm; returns whether it was right and the next problem. A wrong answer repeats the same problem. | `value` |
| `answer_many` | Answer several problems in a row with a list of numbers (up to 10), stopping at the result screen. | `values` |
| `get_result` | Read the result screen: solved N of 10, the highscore and every problem with the typed answer and whether it was right. | none |

## Toolkit

An agent can drive the whole app with these; compose them.

| Role | Action |
|---|---|
| Entry | open_menu, new_game |
| Primitives | answer, answer_many |
| Read state | get_problem, get_result |

## Install

The app: F-Droid, or `https://f-droid.org/packages/org.secuso.privacyfriendlyrecknoningskills/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/reckoning-skills
```

## Use

```bash
ghost skill run ghost/reckoning-skills answer --param value=7 --device <serial>
```

```python
run_skill(name="ghost/reckoning-skills", action="answer", params={"value": 7})
# {"result": {"problem": "3 * 3", "given": 7, "correct": false, "next": {...}}}
```

Try asking: "Start a new mental arithmetic game, solve the first three problems correctly and tell me each problem and your answer."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), Reckoning Skills 6. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 6 | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.0 | 2026-11-02 |

### Recorded failures

- Number range and operator selection are not driven.
- Only whole non-negative answers can be typed.

### Popups and first-run screens handled

- The first-run tutorial is skipped; the end-of-game Name Input dialog is cancelled.
