# antimine - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on, and how success is recognised, so an agent can adapt it to another minesweeper app or version.

**Package**: `dev.lucanlm.antimine` (Antimine, AGPL/GPL FOSS game, version 17.6.3 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-10-05 on a headless emulator pool, Android 14 google_apis x86_64, 1080x2400 @ 420 dpi, en-US. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- Main menu: `id/continueGame` (`START` or `CONTINUE`), `id/newGameShow` (`NEW GAME`, expands the difficulty list), `id/themes`, `id/controls`, `id/settings`, `id/stats`, `id/previousGames`, ...
- Difficulty buttons after expanding: `id/startBeginner` (9x9, 10 mines), `id/startIntermediate` (16x16, 40), `id/startExpert` (24x24, 99), `id/startMaster` (50x50, 450); their text is the upper-case difficulty name.
- Game screen: the board is drawn on a canvas and is **not** in the accessibility tree. The app bar has `id/minesCount`, `id/timer` (appears after the first move), `id/hintCounter`; an untouched board shows `id/tapToBegin` (`TAP TO BEGIN`) in its centre. Flag/open mode buttons sit at the bottom.
- The first game offers a tutorial ("Do you know how to play minesweeper?"); the detector taps `Close`.
- Settings: every option is a `Switch` with its label as text and a checked state (read from the Portal tree).

## Actions

### `start_new_game(difficulty)`

Fresh launch > NEW GAME > difficulty. Success: the mine counter equals the difficulty's mine count and the board is untouched.

### `reveal_first_tile(difficulty)`

New game, then tap the centre of the board (`TAP TO BEGIN`). Antimine generates the field after the first tap so it is never a mine (and "No guessing" mode is on by default). Success: the timer is running.

### `get_stats()`

Statistics screen: label/value pairs, or `{}` with `games_finished: 0` while it shows `Empty`.

### `get_settings()`

Settings screen, scrolled: `{label: on/off}` for every switch. Read-only.

## Failure modes

- Further moves need cell coordinates from a screenshot or OCR, because the board is not in the tree; this skill stops after the safe opening move.
