# Control Loop Habit Tracker on Android with an AI agent

**Control Loop Habit Tracker on Android with an AI agent.** Create habits, tick days and read your score and totals on your phone by asking an agent.

Target search phrase: _AI agent habit tracker Android_

Demo shows: `create_habit (name=Meditate)`

> Ghost in the Droid seed skill for Loop Habit Tracker (`org.isoron.uhabits`), the popular open-source habit tracker with scores and charts from F-Droid. Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `create_habit` | Create a yes/no habit | `name`, `question` |
| `check_habit` | Mark a day done or missed (day 0 = today ... 3) | `name`, `day`, `result` |
| `get_habits` | List the habit names | none |
| `get_habit_stats` | Read score, month/year change, total count, frequency | `name` |

## Toolkit

An agent can drive the whole app with these; compose them.

| Role | Action |
|---|---|
| Entry | create_habit |
| Primitives | check_habit |
| Read state | get_habits, get_habit_stats |

## Install

The app: F-Droid, or `https://f-droid.org/packages/org.isoron.uhabits/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/habit-tracker
```

## Use

```bash
ghost skill run ghost/habit-tracker create_habit --param name=Meditate --device <serial>
ghost skill run ghost/habit-tracker check_habit --param name=Meditate --param result=done --device <serial>
```

```python
run_skill(name="ghost/habit-tracker", action="get_habit_stats", params={"name": "Meditate"})
# {"stats": {"score": "5%", "total": "1", "month": "+5%", "year": "+5%", "frequency": "Every day"}}
```

Try asking: "Create a habit called Meditate, mark it done today and show me its stats."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), Loop Habit Tracker 2.3.2. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 2.3.2 | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.0 | 2026-11-02 |

### Recorded failures

- The yes/no dialog appears about half a second after the tap: the helper waits for the `yesBtn`/`noBtn` ids.
- Check marks are drawn, so the list cannot be read for ticks: use get_habit_stats (total and score) to verify.
- CLI turns `yes`/`no` into booleans, so the result enum is `done`/`missed`.
- Day cells are at fixed x positions for a 720 px wide screen; only the last four days are reachable.

### Popups and first-run screens handled

- The first-run welcome (`skip`) is handled in the open_list subroutine; the notification permission is pre-granted.
