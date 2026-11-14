# Control Markor on Android with an AI agent — write Markdown notes

Demo shows: `create_note (title=Demo-031222, content="# Demo\n- recorded by Ghost")`

> Ghost in the Droid seed skill for Markor (`net.gsantner.markor`), the FOSS Markdown and todo.txt editor. Offline, no account; notes are plain files.

| Action | What it does | Params |
|---|---|---|
| `create_note` | Create a new Markdown note (refuses an existing title) | `title`, `content` |
| `read_note` | Return a note's full text | `title` |
| `list_notes` | List files and folders in the notebook | none |
| `add_todo` | Append a task to `todo.txt` | `text` |
| `append_quicknote` | Append a line to `QuickNote.md` | `text` |

## Install

The app: F-Droid (`net.gsantner.markor`). The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/markor
```

## Use

```bash
ghost skill run ghost/markor create_note --param title=Shopping --param content=$'Milk\nEggs' --device emulator-5554
ghost skill run ghost/markor add_todo --param text="Call mom" --device emulator-5554
```

```python
run_skill(name="ghost/markor", action="read_note", params={"title": "Shopping"})
# {"title": "Shopping", "content": "Milk\nEggs"}
```

On first use the skill grants Markor **All files access** through the system settings page, because Markor stores notes as plain files.

## Tested on

Android 14 emulator (google_apis x86_64, 1080x2400, 420 dpi), Markor 2.16.1, en-US, fresh install. Signed self-runs in `runs/`. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Signed self-runs (pass/total) | Dates |
|---|---|---|---|---|---|
| 2.16.1 | 14 | Google/sdk_gphone64_x86_64 (emulator, 1080x2400, 420 dpi, en-US) | 1.0.0 | 10/10 | 2026-10-05 |

Android 13 was additionally replayed on a 720x1600 Samsung SM-A037F (300 dpi, en-GB) and a 1080x2400 emulator (420 dpi, en-US). See [the cross-device report](../../../docs/reports/samsung-failure-fixes.md) for measured outcomes and limitations; other profiles remain unverified.

### Recorded failures

The historical runs above were green. Samsung failures and subsequent fixes are recorded in [the cross-device report](../../../docs/reports/samsung-failure-fixes.md).

### Popups and first-run screens handled

- Intro page
- Intro last page
- What's new / about dialog (first launch and after updates)

### Other known failure modes

- Titles with `/` or other special characters are rejected before any tap.
- If All files access is revoked later, the explainer appears again and the subroutine grants it again.

Filename entry requires fresh native bounds and confirmed name-field focus before typing, then exact readback before saving. It retries only while unsaved if the keyboard moves the dialog or drops characters. The optional rating prompt is declined with NO THANKS.
