# Control Privacy Friendly Notes on Android with an AI agent

**Control Privacy Friendly Notes on Android with an AI agent.** Tell your agent to jot a note or build a shopping checklist: it creates it in Privacy Friendly Notes and ticks items off later.

Target search phrase: _AI agent makes a checklist on Android_

Demo shows: `create_note (title=Garden plan, text=Plant tomatoes in May)`

> Ghost in the Droid seed skill for Privacy Friendly Notes (`org.secuso.privacyfriendlynotes`), an offline notes app from the SECUSO group with text notes and checklists. Fields, cards and checkboxes have real ids, so an agent can write, tick and search notes. Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `open_notes` | Restart the app, skip the welcome pages and read the note list. | none |
| `create_note` | Create a text note with a title and a body. | `title`, `text` |
| `create_checklist` | Create a checklist note from comma-separated items. | `title`, `items` |
| `list_notes` | Return every note with its title, preview and done counter (checklists show for example 0/2). | none |
| `read_note` | Open a note by exact title and return its text or its checklist items with checked state. | `title` |
| `check_item` | Tick (or untick) one item of a checklist and save. | `title`, `item` |
| `search_notes` | Search the notes and return the matching cards, then clear the search. | `query` |

## Toolkit

An agent can drive the whole app with these; compose them.

| Role | Action |
|---|---|
| Entry | open_notes |
| Primitives | create_note, create_checklist, check_item, search_notes |
| Read state | list_notes, read_note |

## Install

The app: F-Droid, or `https://f-droid.org/packages/org.secuso.privacyfriendlynotes/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/privacy-friendly-notes
```

## Use

```bash
ghost skill run ghost/privacy-friendly-notes create_checklist --param title=Groceries --param items=Milk,Eggs --device <serial>
```

```python
run_skill(name="ghost/privacy-friendly-notes", action="create_checklist", params={"title": "Groceries", "items": "Milk,Eggs"})
```

Try asking: "Create a checklist called Groceries with Milk and Eggs in Privacy Friendly Notes, then tick Milk."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), Privacy Friendly Notes 105. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 105 | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.1 | 2026-11-06 |

### Recorded failures

- Titles and item names must match exactly.
- Notes with the same title are ambiguous: the first card wins.

### Popups and first-run screens handled

- A welcome pager on first launch (skipped).

First-run welcome handling is shared by every action. Previously, calling create_checklist directly on a fresh install failed at the welcome pager; it now dismisses that pager before opening the editor. An unrecognised screen still fails instead of reporting success.
