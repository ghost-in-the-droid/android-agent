# kin-nai-d - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `com.icesu.kinnaid` (Kin Nai D, GPL-3.0-or-later, version 567 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- A picker with two mode buttons, a food field with ADD FOOD, the food list (each row has a delete icon) and START RANDOM; a result screen with the chosen food and RANDOM AGAIN, which returns to the picker.

## Actions

### `open_picker()`

Force-stops and relaunches.

### `add_food(name)`

Types the name into the food field and taps ADD FOOD.

### `list_foods()`

Reads the food rows.

### `remove_food(name)`

Taps the delete icon on the matching row.

### `spin()`

Taps START RANDOM and waits for the confetti result screen.

## Adapting

The food list is kept between launches, so a clean reset starts with an empty list. Eliminate mode and the language switch are not driven. The result reveal takes a few seconds; the skill waits for it.
