# vector-pinball - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `com.dozingcatsoftware.bouncy` (Vector Pinball, GPL-3.0, version 1.16.0 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- Menus are real widgets: `startGameButton`, `highScoreButton`, `preferencesButton`, `nextTableButton` / `previousTableButton`, `unlimitedBallsToggle`, and while paused `resumeGameButton` / `endGameButton`. The pause icon sits at the top left of the header (`scoreView`).
- State: `startGameButton` visible = main menu, `resumeGameButton` = paused, neither (but `scoreView`) = a ball is in play.
- The table and the score are painted on a canvas: the score and the ball counter are **not** in the accessibility tree, so the skill cannot read them (they are visible in the clip). High scores are real text in a dialog.
- Touch controls: the first tap on the table launches the ball; tapping the left or right half drives the left or right flipper.

## Actions

### `start_game(table_steps, unlimited_balls)`

Open the main menu (pausing/ending any running game), optionally step tables, tap START GAME, tap the table once to launch. Success: state is `playing`.

### `flip(side, times)`

Resume the game if paused, then tap the lower left/right half N times. Success: still playing (or the game ended).

### `end_game()`

Pause (header icon), tap END GAME. Success: the main menu shows.

### `select_table(steps)`

Tap the table arrows `steps` times. The table label stays 'Select Table' (the name is part of the canvas).

### `get_status()`

Classifies the screen by widget ids; from the menu or pause screen it opens High Scores, reads the lines and closes it.

## Adapting

Other pinball or arcade apps use the same touch halves for flippers; classify the screen by widget ids and re-find the pause icon position.
