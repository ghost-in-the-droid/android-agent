# privacy-friendly-notes - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `org.secuso.privacyfriendlynotes` (Privacy Friendly Notes, GPL-3.0-only, version 105 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- List: search field (`search_src_text`), cards (`text_view_title`, `text_view_description`, `note_text_extra` for the done counter), add button (`fab`). Text editor: `etName`, `etContent`. Checklist editor: `etNewItem`, `btn_add`, rows `item_name` and `item_checkbox`.

## Actions

### `open_notes()`

Force-stops and relaunches; taps Skip on the first-run welcome pager.

### `create_note(title, text)`

Opens the add menu, picks New text, types the fields, taps Save, then Navigate up and finds the note in the list.

### `create_checklist(title, items)`

Types each item in New item and taps ADD, checks the rows, taps Save.

### `list_notes()`

Reads the note cards; checklist previews show [ ] and [x] marks.

### `read_note(title)`

Taps the card, reads the editor fields, goes back with Navigate up.

### `check_item(title, item)`

Opens the checklist, taps the checkbox of the item, confirms it flipped, taps Save and goes back.

### `search_notes(query)`

Types in the search field and reads the filtered cards.

## Adapting

Audio and sketch notes are not part of the skill. Save keeps the editor open, so the skill returns with the Navigate up arrow (never the system Back key). First launch shows a welcome pager that open_notes skips.
