# Control Counter on Android with an AI agent — count with tally counters

**Control Counter on Android with an AI agent.** Create named tally counters, count up, reset and list them from your phone by asking an agent.

Target search phrase: _AI agent tally counter Android_

Demo shows: `add_counter (name=Groceries, value=0)`

> Ghost in the Droid seed skill for Counter (`me.tsukanov.counter`), a FOSS tally counter from F-Droid. Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `add_counter` | Create a named counter with a starting value | `name`, `value` |
| `increment_counter` | Select a counter and tap it N times, return before/after | `name`, `times` |
| `select_counter` | Make a counter the active one, return its value | `name` |
| `reset_counter` | Reset a counter to zero, return before and after | `name` |
| `get_counters` | List every counter with its value | none |

## Toolkit

An agent can drive the whole app with these; compose them.

| Role | Action |
|---|---|
| Entry | add_counter |
| Primitives | select_counter, increment_counter, reset_counter |
| Read state | get_counters |

## Install

The app: F-Droid, or `https://f-droid.org/packages/me.tsukanov.counter/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/tally-counter
```

## Use

```bash
ghost skill run ghost/tally-counter add_counter --param name=Groceries --device <serial>
ghost skill run ghost/tally-counter increment_counter --param name=Groceries --param times=3 --device <serial>
```

```python
run_skill(name="ghost/tally-counter", action="get_counters")
# {"counters": [{"name": "First counter", "value": 0}, {"name": "Groceries", "value": 3}]}
```

Try asking: "Create a counter called Groceries and count three items on it."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), Counter 35. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 35 | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.0 | 2026-11-02 |

### Recorded failures

- A dialog left open by an aborted earlier run hides the counter screen: the `open_counter` subroutine presses BACK when it sees the dialog title.
- The drawer can already be open from a previous run: `open_list` only taps the hamburger when the drawer is closed.
- `increment_counter`, `select_counter` and `reset_counter` fail with "no counter named ..." when the title does not exist; run `get_counters` first.

### Popups and first-run screens handled

- None: the app has no first-run screens and asks for no permissions.
