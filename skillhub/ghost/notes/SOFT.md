# notes - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on, and how success is recognised, so an agent can adapt it to another notes app or version.

**Package**: `org.fossify.notes` (Fossify Notes, GPL-3.0 FOSS app, installed from the official F-Droid repository, sha256-verified)
**Verified**: 2026-10-05 on a headless emulator pool, Android 14 google_apis x86_64, 1080x2400 @ 420 dpi, Fossify Notes 1.7.0, en-US. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- Toolbar: `id/open_search`, `id/open_note` (only shown when 2+ notes exist), `id/new_note`, `More options`.
- One note per pager page; the editor is `id/text_note_view` (hint `Insert text here` when empty). Neighbouring pages stay in the tree at off-screen x positions, so readers keep only nodes with `0 <= left < 1080`.
- Note tabs show titles across the top; the `Open note` picker lists `id/open_note_item_holder` cards with `id/open_note_item_title` and `id/open_note_item_text` (preview).
- New-note dialog: label field `id/locked_note_title` (focused), `Text note`/`Checklist` radios, `OK` (`android:id/button1`).

## Save behaviour

Text is saved when the activity pauses, not while typing. Force-stopping right after typing loses the text. Writers therefore press BACK twice (hide the keyboard, leave the app) and relaunch before validating.

## Actions

### `create_note(title, text)`

`new_note` > type the title > OK > tap the editor > type the text > BACK, BACK > relaunch. Success: the picker lists `title` with a preview starting with `text`. A duplicate title keeps the dialog open and fails.

### `append_to_note(title, text)`

Open the note through the picker, tap low in the editor and move the caret to the end, type a space plus `text`, save as above. Success: the reopened note ends with `text`.

### `list_notes()`

Read the picker cards (titles and previews). With a single note the picker button is hidden; the default note is reported as `General note`.

### `read_note(title)`

Open the note through the picker and return the editor text.

## Failure modes

- `input text` cannot type newlines or some symbols; multi-line text needs a clipboard paste.
- Locked notes (`Lock note`) ask for a PIN; the skill does not handle them.
