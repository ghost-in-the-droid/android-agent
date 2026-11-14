# files - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on, and how success is recognised, so an agent can adapt it to another file manager or version.

**Package**: `com.google.android.documentsui` (Files / DocumentsUI)
**Verified**: 2026-10-05 on a headless emulator pool, Android 14 google_apis x86_64, 1080x2400 @ 420 dpi, DocumentsUI 14, en-US, no Google account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- A folder opens directly with `android.intent.action.VIEW`, MIME `vnd.android.document/directory`, data `content://com.android.externalstorage.documents/document/primary%3A<url-encoded path>`.
- Header `id/header_title` reads `Files in <folder>`; it is the proof that the requested folder (not a fallback view) is showing. An unknown path opens another view, and the actions then fail.
- Items: `id/item_root` cards (grid) or rows (list). Inside, framework ids: `android:id/title` (name), `android:id/details` (size; absent for folders), `android:id/date`.
- Toolbar: `id/option_menu_search` (Search), `More options` overflow with `New folder`, `Sort by...`, `Select all`.

## Actions

### `list_folder(path)`

Open the folder by URI, read items while scrolling. Returns `items: [{name, size, date, is_folder}]`.

### `search_files(query)`

From a folder, tap Search, type the query, press Enter. DocumentsUI searches all of internal storage by name. Returns matching items; success requires every returned name to contain the query.

### `create_folder(path, name)`

Open the parent folder, `More options` > `New folder`, tap the name field (`android:id/text1`), type, tap `OK` (`android:id/button1`; the dialog moves up when the keyboard opens, so it is located again after typing). Success: a folder item named `name` in the parent.

## Test fixture

Files were pushed with `adb shell` into `/sdcard/Download` and `/sdcard/Documents` (`notes.txt`, `report-2026.pdf`, `todo.txt`).

## Failure modes

- Read-only roots (Recent, Images) offer no `New folder`; `create_folder` fails with a clear error.
- Names with characters the IME cannot type via `input text` (emoji) need a clipboard paste.
