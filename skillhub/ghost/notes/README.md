# Control Notes on Android with an AI agent

Demo shows: `create_note (title=Groceries0324, text=milk eggs bread)`

> Ghost in the Droid seed skill for Fossify Notes (`org.fossify.notes`), a FOSS notes app from F-Droid. Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `create_note` | New text note with a title and one line of text | `title`, `text` |
| `append_to_note` | Add text to the end of an existing note | `title`, `text` |
| `list_notes` | All note titles with previews | none |
| `read_note` | Full text of a note | `title` |

## Install

Install the app from F-Droid (`org.fossify.notes`), then:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/notes
```

## Use

```bash
ghost skill run ghost/notes create_note --param title=Groceries --param "text=milk eggs bread" --device emulator-5554
ghost skill run ghost/notes read_note --param title=Groceries --device emulator-5554
```

From any MCP agent:

```python
run_skill(name="ghost/notes", action="list_notes")
# {"notes": [{"title": "Groceries", "preview": "milk eggs bread"}], "count": 1}
```

## Tested on

Android 14 emulator (google_apis x86_64, 1080x2400, 420 dpi), Fossify Notes 1.7.0, en-US. Signed self-runs live in `runs/`.

## Notes

Nothing leaves the device. Notes are never deleted by this skill. License: MIT (the skill; the app is GPL-3.0).

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Signed self-runs (pass/total) | Dates |
|---|---|---|---|---|---|
| 1.7.0 | 14 | Google/sdk_gphone64_x86_64 (emulator, 1080x2400, 420 dpi, en-US) | 1.0.0 | 12/12 | 2026-10-05 |

Physical-device launch attempts are also recorded on Samsung SM-A156B (Android 16, 1080×2340, en-US). Results remain action-specific; an attempt does not imply success. See the demos and current signed runs for evidence.

Untested so far: other OEM skins, other screen sizes and other locales.

### Recorded failures

None in the signed self-runs.

### Popups and first-run screens handled

- None app-specific; Android permission dialogs go through the engine's OS popup layer.

### Other known failure modes

- `input text` cannot type newlines or some symbols; multi-line text needs a clipboard paste.
- Locked notes (`Lock note`) ask for a PIN; the skill does not handle them.
