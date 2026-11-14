# outdoor-food-calculator - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `org.birdbird.outdoorfoodcalc` (Outdoor Food Calculator, MIT, version 2 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- A calculator tab with a days field, notes, three trip type chips (Short activity, Multi-day hike, Long distance), a Food Items section with an Add Food button, and a bottom bar of five meters (Calories, Protein, Carbs, Fat, Fiber) showing per-day amount over the daily target. Add Food opens a category list with an amount field and an add button per food.

## Actions

### `open_calculator()`

Force-stops and relaunches.

### `set_trip(days, type)`

Types the days and taps the trip type chip; daily targets change with the type.

### `add_food(name, grams)`

Opens Add Food, types the amount, scrolls the category list to the food and taps its add button.

### `get_totals()`

Reads the five meters.

## Adapting

Meters show the per-day average (total weight divided by the days) over a daily target that depends on the trip type. The foods you added are listed below the fold and are not read back one by one; Saved, Foods and Profiles tabs and saving a calculation are not driven. Start state is a fresh app with no foods.
