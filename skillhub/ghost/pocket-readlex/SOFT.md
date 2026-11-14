# pocket-readlex - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `uk.co.busydoingnothing.pocketrl` (Pocket ReadLex, GPL-3.0-or-later, version 1 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- Search: `search_edit`, `clear_search_button`, rows with `word`, `translation`, `word_type`. Entry: `entry_translation` (word then arrow then Shavian), `entry_ipa`, `entry_type`.

## Actions

### `open_search()`

Force-stops and relaunches.

### `search_word(word)`

Clears the field, types the word and reads the visible rows.

### `get_entry(word)`

Searches, taps the exact row, reads the entry and returns with one Back key press.

### `transliterate(text)`

One search per word; unknown words come back as ? and are listed in missing.

## Adapting

Shavian letters are Unicode characters (U+10450 and up), so results contain them as text. The entry screen has no on-screen back arrow; the skill uses one Back key press from the entry, which returns to the search screen of the same app.
