# Control Easy Notes on Android with an AI agent

**Control Easy Notes on Android with an AI agent.** Tell your agent to jot a note: it creates it in Easy Notes, finds it again and reads it back.

Target search phrase: _AI agent creates notes on Android_

Demo shows: `create_note (title=Shopping list, text=Milk eggs bread)`

> Ghost in the Droid seed skill for Easy Notes (`com.kin.easynotes`), an offline markdown notes app. Note cards and fields are real text nodes, so an agent can create, list, search and read notes. Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `open_notes` | Restart the app and read the note list. | none |
| `create_note` | Create a note with a title and a text body. | `title`, `text` |
| `list_notes` | Return every note on the list with its title and text preview. | none |
| `read_note` | Open a note by exact title and return its title and body. | `title` |
| `search_notes` | Type a query in the search field and return the matching notes, then clear it. | `query` |

## Toolkit

An agent can drive the whole app with these; compose them.

| Role | Action |
|---|---|
| Entry | open_notes |
| Primitives | create_note, search_notes |
| Read state | list_notes, read_note |

## Install

The app: F-Droid, or `https://f-droid.org/packages/com.kin.easynotes/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/easy-notes
```

## Use

```bash
ghost skill run ghost/easy-notes create_note --param title='Groceries' --param text='Milk eggs bread' --device <serial>
```

```python
run_skill(name="ghost/easy-notes", action="create_note", params={"title": "Groceries", "text": "Milk eggs bread"})
```

Try asking: "Create a note called Shopping list with the text Milk eggs bread in Easy Notes, then read it back."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), Easy Notes 14. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 14 | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.0 | 2026-11-02 |

### Recorded failures

- read_note needs the exact title as shown on the card.
- There is no delete action because the app crashes on delete.

### Popups and first-run screens handled

- None.
