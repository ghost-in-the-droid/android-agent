# regex-crossword - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `de.chagemann.regexcrossword` (Regex Crossword, GPL-3.0, version 33 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- Category list (`categoryNameTextView`, `levelStatsTextView`), level list (`levelNameTextView`), then the puzzle: clues are plain TextViews above the columns and left of the rows, cells are EditTexts (one character each), `verifyCrosswordButton` at the bottom.
- Verify opens a dialog (`android:id/alertTitle` Level Completed!) when the grid is right.
- Rows and columns are derived from the cell positions, so rectangular grids work.

## Actions

### `list_levels()`

Backs out to the category list and reads it.

### `open_level(category, level)`

Taps the category, then the level by name; lists the level names when the name is wrong.

### `get_puzzle()`

column_clues above the grid, row_clues left of it, grid rows with . for empty cells.

### `enter(rows)`

Taps each cell, clears it and types the character; . leaves a cell untouched.

### `verify()`

Waits for the Level Completed dialog (up to about 4 s).

## Adapting

The agent solves the regexes itself; the skill never knows the answer. A clue that is already satisfied can disappear from the clue list. Rectangular grids only: hexagonal levels (if any) are not mapped.
