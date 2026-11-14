# poet-assistant - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `ca.rmen.android.poetassistant` (Poet Assistant, GPL-3.0-only, version 113201 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- Search bar on top; tabs RHYMER, THESAURUS, DICTIONARY, COMPOSER, FAVORITES.
- Result list: header (the word), then rows: rhyme groups (`Strict rhyme matches:` ...), thesaurus entries (`noun`, `Synonyms:` ...) or dictionary rows (`word_type`, `definition`).

## Actions

### `open_poet()`

Force-stops and relaunches.

### `lookup(word, mode)`

Types the word into the search field, presses Enter, opens the tab and reads the rows (scrolling for long lists).

### `get_results()`

Detects the tab from the row ids and parses the rows.

## Adapting

The Composer and Favorites tabs, text to speech and the filter are not driven.
