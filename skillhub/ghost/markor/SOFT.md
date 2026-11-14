# markor - SOFT skill (LLM-adaptable narrative)

**Package**: `net.gsantner.markor` (Markor, Apache-2.0, from F-Droid)
**Verified**: 2026-10-05 on a headless emulator pool, Android 14 google_apis x86_64, 1080x2400 @ 420 dpi, Markor 2.16.1, en-US, fresh install.
**Skill class**: HARD. Offline, no account. Notes are plain files in the notebook folder `/storage/emulated/0/Documents/markor/`.

## Layout reference

Main screen bottom tabs (resource ids under `net.gsantner.markor:id/`): `nav_notebook` (file browser), `nav_todo` (editor on `todo.txt`), `nav_quicknote` (editor on `QuickNote.md`), `nav_more`. File rows: `opoc_filesystem_item__title`. New file FAB: content-desc `Create a new file or folder`; its dialog has `new_file_dialog__name` and an `OK` button. Editor: `document__fragment__edit__highlighting_editor` (its text is the whole document), toolbar content-desc `Save`, `Undo`, `View Mode`.

First launch: a 5-page intro (`id/next` with content-desc `NEXT`, then `DONE`), a "what's new" dialog (`Official project sources ...`, `OK`), and Markor's own explainer `Storage permission required to read and write files` that leads to the system **All files access** page; the skill taps `OK`, toggles `Allow access to manage all files`, and goes back. Markor needs this to keep notes as plain files.

Saving: Markor saves on `Save` and when the editor pauses. Tapping `Save` right after typing can save the old text, so the skill waits a second first, and `create_note` also leaves the editor with BACK.

## Actions

### `create_note(title, content)`

Refuses if `<title>.md` already exists (Markor would open the old file and the typed text would land at the cursor). Notebook tab, FAB, type the name, `OK`, type the content line by line (Enter between lines), `Save`, BACK. Success: the file on disk contains the content.

### `read_note(title)`

Notebook tab, tap the title resource ID with the exact filename or the folded row description beginning `File <title>.md `, then read the editor text. This is the only file-row tap in the manifest; the other actions use tab IDs or create a new file. Success: the text equals the file on disk.

### `list_notes()`

Notebook tab; collect `opoc_filesystem_item__title` rows or folded file descriptions (scrolling), without `..`. Names with a dot are collected as files, the rest as folders. The validator independently runs `ls -1Ap` on the notebook directory and compares file/folder sets and count. A UI omission or wrong file/folder classification fails.

### `add_todo(text)`

To-Do tab, Ctrl+End to the end of `todo.txt`, new line, type. Markor prefixes new lines with today's date (`2026-10-05 Call mom`), so the check is "a line ends with the text".

### `append_quicknote(text)`

QuickNote tab, Ctrl+End, new line, type, `Save`. Success: `QuickNote.md` contains the text.

## Failure modes

- Titles with `/` or other special characters are rejected before any tap.
- If All files access is revoked later, the explainer appears again and the subroutine grants it again.
