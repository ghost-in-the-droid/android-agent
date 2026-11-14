# Control LibreBible on Android with an AI agent

**Control LibreBible on Android with an AI agent.** An agent opens any book and chapter of the Latin Vulgate on your phone and reads the verses back.

Target search phrase: _AI agent reads the Latin Vulgate Bible on Android_

Demo shows: `open_chapter (book=Ruth, chapter=1)`

> Ghost in the Droid seed skill for LibreBible (`xyz.yeikoff.librebible`), an offline Latin Vulgate reader. Books, chapters and verses are plain text nodes, so an agent can navigate and read them. Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `open_books` | Restart the app and show the book list. | none |
| `list_books` | Scroll the whole book list and return every book name. | none |
| `open_chapter` | Open a book and chapter by name and number. | `book`, `chapter` |
| `read_chapter` | Read every verse of the open chapter (Latin text, verse numbers by order). | none |

## Toolkit

An agent can drive the whole app with these; compose them.

| Role | Action |
|---|---|
| Entry | open_books |
| Primitives | list_books, open_chapter |
| Read state | read_chapter |

## Install

The app: F-Droid, or `https://f-droid.org/packages/xyz.yeikoff.librebible/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/librebible
```

## Use

```bash
ghost skill run ghost/librebible open_chapter --param book=Ruth --param chapter=1 --device <serial>
```

```python
run_skill(name="ghost/librebible", action="open_chapter", params={"book": "Ruth", "chapter": "1"})
```

Try asking: "Open Ruth chapter 1 in LibreBible and tell me the first verse in Latin."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), LibreBible 20231110. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 20231110 | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.0 | 2026-11-02 |

### Recorded failures

- Book names must match the list exactly (for example 2 King, not 2 Kings).
- Long chapters need several scroll pages, so reading takes up to a minute.

### Popups and first-run screens handled

- None.
