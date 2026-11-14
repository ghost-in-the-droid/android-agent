# Control Stoic Reading on Android with an AI agent

**Control Stoic Reading on Android with an AI agent.** Want a Stoic quote? Your agent opens Marcus Aurelius, Epictetus or Seneca and reads the passage.

Target search phrase: _AI agent reads Stoic philosophy texts on Android_

Demo shows: `list_works (author=Seneca)`

> Ghost in the Droid seed skill for Stoic Reading (`app.reading.stoic.stoicreading2`), an offline library of classic Stoic texts. Authors, works and the full text are real text nodes, so an agent can find and quote a passage without internet. Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `open_library` | Restart the app and list the authors. | none |
| `list_works` | Open an author and list their works. | `author` |
| `open_work` | Open a work (and a book or chapter group if it has one) of an author and return the text when it opens, or the list of parts when it has more levels. | `author`, `work`, `part` |
| `read_text` | Read a slice of the open text (offset and length in characters, default the first 2500). | `offset`, `length` |

## Toolkit

An agent can drive the whole app with these; compose them.

| Role | Action |
|---|---|
| Entry | open_library |
| Primitives | open_work, list_works |
| Read state | read_text |

## Install

The app: F-Droid, or `https://f-droid.org/packages/app.reading.stoic.stoicreading2/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/stoic-reading
```

## Use

```bash
ghost skill run ghost/stoic-reading open_work --param author=Aurelius --param work=Meditations --param "part=Book 2" --device <serial>
```

```python
run_skill(name="ghost/stoic-reading", action="open_work", params={"author": "Aurelius", "work": "Meditations", "part": "Book 2"})
# {"result": {"state": {"screen": "reader", "title": "Book 2", "text": "1. Begin the morning by saying to yourself ..."}}}
```

Try asking: "Open Marcus Aurelius, Meditations, Book 2 in Stoic Reading and quote me the first lines."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), Stoic Reading 77. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 77 | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.0 | 2026-11-02 |

### Recorded failures

- An author or work that does not match raises an error listing what is available.
- The dark mode checkbox is not driven.

### Popups and first-run screens handled

- None.
