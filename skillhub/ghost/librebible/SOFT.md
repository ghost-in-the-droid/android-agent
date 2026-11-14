# librebible - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `xyz.yeikoff.librebible` (LibreBible, GPL-3.0-only, version 20231110 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- Book list: rows of TextViews. Chapter grid: number cells. Chapter: one TextView per verse, header title `Book N` and an in-app Back arrow (content-desc Back).

## Actions

### `open_books()`

Force-stops and relaunches.

### `list_books()`

Scrolls the list from the top and merges pages.

### `open_chapter(book, chapter)`

Goes back to the book list with the in-app Back arrow, scrolls to the book, taps it and then the chapter.

### `read_chapter()`

Scrolls from the top and merges pages; verses are unnumbered rows so verse n is the nth row.

## Adapting

The text is Latin and has no verse numbers; the skill numbers verses by row order. The skill uses the in-app Back arrow, never the system Back key.
