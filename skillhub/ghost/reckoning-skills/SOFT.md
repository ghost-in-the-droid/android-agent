# reckoning-skills - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `org.secuso.privacyfriendlyrecknoningskills` (Reckoning Skills, GPL-3.0-or-later, version 6 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- Menu (number range, operator buttons, NEW GAME, CONTINUE), game (x operator y, keypad 0-9 with X and check, progress i/10, timer), a Name Input dialog after the tenth answer and a result screen.

## Actions

### `open_menu()`

Force-stops, relaunches and taps SKIP on the tutorial if it shows.

### `new_game()`

Taps NEW GAME with the default range of 10 and all four operators.

### `get_problem()`

Reads the two numbers, the operator and the progress counter.

### `answer(value)`

Taps the digit keys and the check key, cancels the highscore name dialog after the tenth answer.

### `answer_many(values)`

Repeats answer; each result says whether it was right.

### `get_result()`

Reads the solved counter and the problem rows; right or wrong is checked by arithmetic.

## Adapting

The game runs with the default number range 10 and all four operators; range and operator toggles are not driven. A wrong answer repeats the same problem, so a game can have more than 10 answers' worth of attempts in the result list. The Name Input dialog at the end is cancelled, so no highscore name is stored. Division is shown with a slash and rounded down by the skill's checker.
