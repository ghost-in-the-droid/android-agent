# Control Quick Calculation on Android with an AI agent

**Control Quick Calculation on Android with an AI agent.** How fast can an AI do mental maths? Your agent plays a timed game on your phone and reports the score.

Target search phrase: _AI agent plays a quick mental maths game on Android_

Demo shows: `start_game (operator=Addition, timer=120)`

> Ghost in the Droid seed skill for Quick Calculation (`io.github.subhamtyagi.quickcalculation`), an offline timed mental maths game. The question, the four answer buttons, the running score and the results are text nodes, so an agent can play and see its score. Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `open_setup` | Restart the app and read the setup form (operator, number ranges). | none |
| `start_game` | Pick an operator and a timer (30, 45, 60, 90, 120, 300 or 600 seconds), start the game and return the first question with its four options. | `operator`, `timer` |
| `get_question` | Read the current question, its four options, the time left and the score. | none |
| `answer` | Answer the current question by option text (value) or button position 1-4 (option); returns right or wrong and the next question. Tapping an option answers at once. | `value`, `option` |
| `answer_many` | Answer several questions in a row (up to 8), by answer texts (values) or button positions (options), comma separated. | `values`, `options` |
| `finish_game` | End the game with Submit and read the results (correct answers and attempts). | none |
| `get_result` | Read the results screen: total correct and total attempts. | none |

## Toolkit

An agent can drive the whole app with these; compose them.

| Role | Action |
|---|---|
| Entry | open_setup, start_game |
| Primitives | answer, answer_many, finish_game |
| Read state | get_question, get_result |

## Install

The app: F-Droid, or `https://f-droid.org/packages/io.github.subhamtyagi.quickcalculation/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/quick-calculation
```

## Use

```bash
ghost skill run ghost/quick-calculation answer --param option=2 --device <serial>
```

```python
run_skill(name="ghost/quick-calculation", action="answer", params={"value": "148"})
# {"result": {"question": "74 + 74", "chosen": "148", "correct": true, "feedback": "CORRECT!", ...}}
```

Try asking: "Start a Quick Calculation addition game, solve the first three questions by picking the right option each time, then end the game and tell me the score."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), Quick Calculation 5. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 5 | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.0 | 2026-11-02 |

### Recorded failures

- A game with a short timer can end before a slow agent finishes; the next action then sees the results screen.
- Number range fields are not driven.

### Popups and first-run screens handled

- None.
