# Control Notally on Android with an AI agent

**Control Notally on Android with an AI agent.** Keep notes on your phone: an agent writes notes, lists them, reads one back and deletes one.

Target search phrase: _AI agent takes notes on Android_

Demo shows: `create_note (title=Shopping idea, body=Buy milk and eggs)`

> Ghost in the Droid seed skill for Notally (`com.omgodse.notally`), a minimalist local notes app. Note cards and the editor fields are plain nodes, so an agent can write, list, read and delete notes. Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `open_notes` | Restart the app and read the note list. | none |
| `create_note` | Create a note with a title and an optional body (plain ASCII). | `title`, `body` |
| `list_notes` | Read all notes (title, body preview, date). | none |
| `read_note` | Open a note by title and return its full title and body. | `title` |
| `delete_note` | Delete a note by title (it moves to the app's trash). Needs confirm=yes. | `title`, `confirm` |

## Toolkit

An agent can drive the whole app with these; compose them.

| Role | Action |
|---|---|
| Entry | open_notes |
| Primitives | create_note, read_note, delete_note |
| Read state | list_notes |

## Install

The app: F-Droid, or `https://f-droid.org/packages/com.omgodse.notally/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/notally-notes
```

## Use

```bash
ghost skill run ghost/notally-notes create_note --param title=Ideas --param body="Buy milk" --device <serial>
```

```python
run_skill(name="ghost/notally-notes", action="create_note", params={"title": "Ideas", "body": "Buy milk"})
# {"result": {"title": "Ideas", "state": {"notes": [{"title": "Ideas"}]}}}
```

Try asking: "Create a note called Shopping idea saying Buy milk and eggs, then list my notes."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), Notally 57. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 57 | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.0 | 2026-11-02 |

### Recorded failures

- Plain ASCII only.
- delete_note needs confirm=yes; the note moves to the trash of the app, it is not erased at once.
- Two notes with the same title: the first one is used.

### Popups and first-run screens handled

- None.
