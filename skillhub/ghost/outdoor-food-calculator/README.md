# Control Outdoor Food Calculator on Android with an AI agent

**Control Outdoor Food Calculator on Android with an AI agent.** Your agent plans the food for a hike: set the days, add foods by weight and read calories and macros against the daily target.

Target search phrase: _AI agent plans hiking food and calories on Android with an outdoor food calculator_

Demo shows: `set_trip (days=5, type=Multi-day hike)`

> Ghost in the Droid seed skill for Outdoor Food Calculator (`org.birdbird.outdoorfoodcalc`), an offline trip food planner. The trip length, trip type chips, food list and the five nutrient meters are all text nodes, so an agent can plan a menu and read the nutrition. Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `open_calculator` | Restart the app and read the trip settings and nutrient meters. | none |
| `set_trip` | Set the number of days and/or the trip type. | `days`, `type` |
| `add_food` | Add a food by weight and return the updated per-day totals. | `name`, `grams` |
| `get_totals` | Read days, calories, protein, carbs, fat and fibre per day with targets. | none |

## Toolkit

An agent can drive the whole app with these; compose them.

| Role | Action |
|---|---|
| Entry | open_calculator |
| Primitives | set_trip, add_food |
| Read state | get_totals |

## Install

The app: F-Droid, or `https://f-droid.org/packages/org.birdbird.outdoorfoodcalc/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/outdoor-food-calculator
```

## Use

```bash
ghost skill run ghost/outdoor-food-calculator add_food --param name="Oat Flakes" --param grams=150 --device <serial>
```

```python
run_skill(name="ghost/outdoor-food-calculator", action="get_totals")
# {"result": {"state": {"days": 5, "totals": {"calories": {"per_day": 263, "target": 3200}}}}}
```

Try asking: "Plan food for a 5 day hike: set it to Multi-day hike, add 150 g of oat flakes and 200 g of rice, then tell me the calories per day."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), Outdoor Food Calculator 2. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 2 | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.0 | 2026-11-02 |

### Recorded failures

- Adding a food that is not in the list raises an error.
- Days must be 1 to 60 and grams 1 to 5000.

### Popups and first-run screens handled

- None.
