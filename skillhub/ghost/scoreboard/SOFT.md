# scoreboard - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `com.github.vatbub.scoreboard` (Scoreboard, Apache-2.0, version 264 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- Header row of player-name EditTexts (`Player 1`), one row of score EditTexts per round, a totals row of TextViews under the table, a `+` (`action_add_player`) in the toolbar and a round button (`fab`).
- A fresh install starts with one player and no rounds; the first add_round creates round 1.
- The keyboard has to be closed (BACK) after typing so the next tap hits the cell and not a key.

## Actions

### `add_player(name)`

Taps +, then renames the newest header cell.

### `add_round()`

Taps the round button.

### `set_score(round, player, value)`

Taps the cell, clears it, types the number, closes the keyboard; the totals update.

### `get_scores()`

Parses the header, the cells and the totals row.

## Adapting

Names are limited to letters, digits and spaces (typed through adb). Scores are whole numbers. Renaming an existing player and deleting rows or players are not driven by this version.
