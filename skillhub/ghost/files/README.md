# files

Demo shows: `create_folder (path=Documents, name=Receipts0323)`

> Ghost in the Droid seed skill for the Android Files app (`com.google.android.documentsui`). Works without an account.

| Action | What it does | Params |
|---|---|---|
| `list_folder` | Items in an internal-storage folder | `path` (default `Download`) |
| `search_files` | Files whose name matches a query | `query` |
| `create_folder` | Create an empty folder inside a parent folder | `path` (default `Documents`), `name` |

## Install

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/files
```

## Use

```bash
ghost skill run ghost/files list_folder --param path=Download --device emulator-5554
ghost skill run ghost/files search_files --param query=report --device emulator-5554
ghost skill run ghost/files create_folder --param path=Documents --param name=Receipts --device emulator-5554
```

From any MCP agent:

```python
run_skill(name="ghost/files", action="list_folder", params={"path": "Download"})
# {"items": [{"name": "notes.txt", "size": "19 B", "date": "8:17 PM", "is_folder": false}], "count": 1}
```

## Tested on

Android 14 emulator (google_apis x86_64, 1080x2400, 420 dpi), DocumentsUI 14, en-US. Signed self-runs live in `runs/`.

## Notes

Nothing is deleted, moved or uploaded. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Signed self-runs (pass/total) | Dates |
|---|---|---|---|---|---|
| 14-10541443 | 14 | Google/sdk_gphone64_x86_64 (emulator, 1080x2400, 420 dpi, en-US) | 1.0.0 | 9/9 | 2026-10-05 |

Untested so far: physical devices, other OEM skins, other screen sizes, other locales.

### Recorded failures

None in the signed self-runs.

### Popups and first-run screens handled

- None app-specific; Android permission dialogs go through the engine's OS popup layer.

### Other known failure modes

- Read-only roots (Recent, Images) offer no `New folder`; `create_folder` fails with a clear error.
- Names with characters the IME cannot type via `input text` (emoji) need a clipboard paste.
