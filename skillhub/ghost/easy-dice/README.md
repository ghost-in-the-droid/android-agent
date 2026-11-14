# Control Easy Dice on Android with an AI agent

**Control Easy Dice on Android with an AI agent.** Your agent rolls the dice for your tabletop game: say 2d6 plus a d20 and get the total.

Target search phrase: _AI agent rolls dice for D&D on Android with a polyhedral dice roller_

Demo shows: `add_dice (sides=20, count=2)`

> Ghost in the Droid seed skill for Easy Dice (`net.pejici.easydice`), an offline polyhedral dice roller. The ROLL and RESET buttons and the total text are readable, so an agent can build a hand, roll it and report the sum. Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `open_dice` | Restart the app and read the hand. | none |
| `add_dice` | Add dice of one size to the hand. | `sides`, `count` |
| `roll` | Roll the dice in the hand and return the total. | none |
| `reset_hand` | Remove all dice from the hand. | none |
| `roll_dice` | Clear the hand, add the dice in a notation like 2d6+d20, roll and return the total. | `spec` |

## Toolkit

An agent can drive the whole app with these; compose them.

| Role | Action |
|---|---|
| Entry | open_dice |
| Primitives | add_dice, roll, reset_hand, roll_dice |
| Read state | roll (returns the sum and dice count) |

## Install

The app: F-Droid, or `https://f-droid.org/packages/net.pejici.easydice/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/easy-dice
```

## Use

```bash
ghost skill run ghost/easy-dice roll_dice --param spec=2d6+d20 --device <serial>
```

```python
run_skill(name='ghost/easy-dice', action='roll_dice', params={'spec': '2d6+d20'})
# {"result": {"spec": "2d6+d20", "dice": [6, 6, 20], "sum": 20}}
```

Try asking: "Roll 2d6 and a d20 for my D&D attack and tell me the total."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), Easy Dice 11. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 11 | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.0 | 2026-11-02 |

### Recorded failures

- Rolling with no dice in the hand raises an error.
- Sides must be 2, 4, 6, 8, 10, 100, 12, 20 or 30.

### Popups and first-run screens handled

- None.
