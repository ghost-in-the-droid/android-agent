# habit-tracker - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `org.isoron.uhabits` (Loop Habit Tracker, GPL-3.0, version 2.3.2 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- First launch shows a welcome (`skip`). List screen: `actionCreateHabit` (+), `action_filter`; one row per habit (the name is a TextView) followed by four day cells (today, yesterday, ...) at x about 400/490/580/670 on a 720 px screen.
- Create flow: + > `buttonYesNo` ("Yes or No") > `nameInput`, optional `questionInput` > `buttonSave`.
- Tapping a day cell opens a small dialog with `yesBtn` (done) and `noBtn` (missed); the check marks themselves are drawn, not text.
- Habit detail (tap the name): `scoreLabel` (e.g. 5%), `monthDiffLabel`, `yearDiffLabel`, `totalCountLabel`, `frequencyLabel`, charts.

## Actions

### `create_habit(name, question)`

+ > Yes or No > type the name (and question) > SAVE. Success: the name shows in the list.

### `check_habit(name, day, result)`

Tap the habit's day cell, wait for the dialog, tap yesBtn (done) or noBtn (missed). Result is `done` or `missed` (yes/no and true/false are accepted; the CLI turns bare yes/no into booleans).

### `get_habits()`

Reads the name TextViews left of the day cells.

### `get_habit_stats(name)`

Open the habit, read the overview labels, go back. Returns `stats`.

## Adapting

Other habit trackers also split a list and a detail screen; the day-cell positions and the done/missed dialog are the app-specific parts.
