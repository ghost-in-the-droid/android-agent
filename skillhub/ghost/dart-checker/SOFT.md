# dart-checker - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `com.DartChecker` (Dart Checker, GPL-3.0, version 49 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- Setup: Game (`gamemode`, cycles 101..1001 on tap), Players (`playerCountButton`, cycles 1-4), double/master in/out switches, `startButton`.
- Game: `p1name`, `dart1..3` (this turn: `T20`, `20`, `-`), `scorePlayer1..N` (points left), `average`, `dartsThrown`, Double/Triple toggles, buttons `b1..b20`, `bull`, `missedButton`, `continueButton`, `undoButton`.
- BACK from the game leaves the app, so the skill never presses it.

## Actions

### `new_game(mode, players)`

Force-stops the app, relaunches, cycles the Game and Players buttons to the wanted values and taps Start.

### `throw(dart)`

Taps Double or Triple if needed, then the number button; Missed for a miss.

### `throw_darts(darts)`

Same as throw for each dart.

### `end_turn()`

Taps continue.

### `undo()`

Taps undo.

### `get_state()`

Reads scorePlayerN, dart1-3, average and dartsThrown.

## Adapting

Only the X01 game type is driven. Double-out and master-out switches keep the setup default; the skill does not change them.
