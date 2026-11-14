# Control Kin Nai D on Android with an AI agent

**Control Kin Nai D on Android with an AI agent.** No idea what to eat? Your agent keeps your list of foods and lets the app pick one.

Target search phrase: _AI agent decides what to eat with a random food picker on Android_

Demo shows: `add_food (name=Ramen)`

> Ghost in the Droid seed skill for Kin Nai D (`com.icesu.kinnaid`), an offline what-to-eat decider. The food list, the add button and the random result are text nodes, so an agent can manage a menu and let the app choose. Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `open_picker` | Restart the app and read the food list. | none |
| `add_food` | Add a food to the list. | `name` |
| `list_foods` | Read the foods currently in the list. | none |
| `remove_food` | Remove a food from the list by name. | `name` |
| `spin` | Press START RANDOM and return the food the app picked (at least two foods are needed). | none |

## Toolkit

An agent can drive the whole app with these; compose them.

| Role | Action |
|---|---|
| Entry | open_picker |
| Primitives | add_food, remove_food, spin |
| Read state | list_foods |

## Install

The app: F-Droid, or `https://f-droid.org/packages/com.icesu.kinnaid/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/kin-nai-d
```

## Use

```bash
ghost skill run ghost/kin-nai-d add_food --param name=Ramen --device <serial>
```

```python
run_skill(name="ghost/kin-nai-d", action="spin")
# {"result": {"food": "Sushi", "from": ["Sushi", "Ramen"]}}
```

Try asking: "Add Pizza, Sushi and Ramen to my what-to-eat list, then let the app pick what I should eat."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), Kin Nai D 567. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 567 | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.0 | 2026-11-02 |

### Recorded failures

- Spinning with fewer than two foods raises an error.
- Eliminate mode is not driven.

### Popups and first-run screens handled

- None.
