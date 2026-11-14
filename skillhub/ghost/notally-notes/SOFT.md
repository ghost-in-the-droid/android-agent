# notally-notes - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `com.omgodse.notally` (Notally, GPL-3.0-only, version 57 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- List: toolbar (drawer, Search), note cards (Title, Date, Note preview), buttons Make list and Take note.
- Editor: toolbar (up, Pin, Share, More options), `EnterTitle`, `DateCreated`, `EnterBody`; leaving the editor saves.
- Selecting a card (long press) shows a toolbar whose More options menu has Delete.

## Actions

### `open_notes()`

Force-stops and relaunches.

### `create_note(title, body)`

Taps Take note, types title and body, then the up arrow which saves the note.

### `list_notes()`

Reads the note cards.

### `read_note(title)`

Taps the card, reads the editor fields and returns with the up arrow.

### `delete_note(title, confirm)`

Long-presses the card, opens More options and taps Delete. The note moves to the app's Deleted section.

## Adapting

Checklists (Make list), labels, colours, pinning, sharing and search are not driven. The skill never touches Share.
