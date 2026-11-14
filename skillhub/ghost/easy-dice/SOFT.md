# easy-dice - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `net.pejici.easydice` (Easy Dice, GPL-3.0-or-later, version 11 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- A play area where the chosen dice appear, a status line (Adds to N), RESET and ROLL buttons and a palette of nine dice (d2 d4 d6 d8 d10 d100 d12 d20 d30) below. Tapping a die adds it to the hand.

## Actions

### `open_dice()`

Force-stops and relaunches.

### `add_dice(sides, count)`

Taps the die in the palette.

### `roll()`

Taps ROLL and waits for the total to settle.

### `reset_hand()`

Taps RESET.

### `roll_dice(spec)`

Resets, taps each die, then ROLL.

## Adapting

Individual faces are drawn, not text, so only the total is returned, never each die. A freshly added die counts at its maximum until it is rolled. Up to 12 dice per add; the Add and Remove hand buttons and settings are not driven.
