# stoic-reading - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `app.reading.stoic.stoicreading2` (Stoic Reading, GPL-3.0-or-later, version 77 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- An author list with a Dark Mode checkbox, an author page with one button per work, an optional list of books or chapter groups, and a reader that is one large text node.

## Actions

### `open_library()`

Force-stops and relaunches.

### `list_works(author)`

Taps the author button and reads the work buttons.

### `open_work(author, work, part)`

Walks author, work and part buttons by name; steps back with a checked system BACK when needed.

### `read_text(offset, length)`

The whole text is one text node; the skill returns the requested slice and says whether more follows.

## Adapting

The reader has no on-screen back arrow, so the skill goes back with a system BACK only after checking that the app is in the foreground and not on the author list. Long books are read in slices with offset and length. Author and work names are matched case-insensitively by substring.
