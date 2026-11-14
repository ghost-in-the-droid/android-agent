# quick-calculation - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `io.github.subhamtyagi.quickcalculation` (Quick Calculation, GPL-3.0-or-later, version 5 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- Setup form with an operator spinner, a timer spinner and two number ranges; game screen with a timer, a correct/attempts score, a question and four answer buttons; Submit ends the game; a results screen shows Total Correct and Total Attempts.

## Actions

### `open_setup()`

Force-stops and relaunches.

### `start_game(operator, timer)`

Chooses both spinner entries from their popup lists and taps Starts Now!.

### `get_question()`

Reads the question, the four answer buttons, the timer and the correct/attempts score.

### `answer(value, option)`

Taps the matching answer button, waits for the score to change and reads the RIGHT/WRONG label.

### `answer_many(values, options)`

Repeats answer and returns a right or wrong flag per question.

### `finish_game()`

Taps Submit, which ends the game and shows the results screen.

### `get_result()`

Reads the two result counters.

## Adapting

Tapping an answer button answers at once; Submit ends the game (it is not an answer confirmation). The timer keeps running while idle, so use a long timer (default 120 s) and finish within it; when it expires the app shows the results by itself. The number ranges are not driven. The app keeps hidden view groups in its tree, so the skill recognises the results screen by the DONE! label.
