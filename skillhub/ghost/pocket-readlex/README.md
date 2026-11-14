# Control Pocket ReadLex on Android with an AI agent

**Control Pocket ReadLex on Android with an AI agent.** Ask your agent to write a phrase in the Shavian alphabet: it looks each word up in Pocket ReadLex and reads back the letters.

Target search phrase: _AI agent translates English to Shavian on Android_

Demo shows: `search_word (word=hello)`

> Ghost in the Droid seed skill for Pocket ReadLex (`uk.co.busydoingnothing.pocketrl`), an offline English to Shavian dictionary (the ReadLex). Rows and entry fields have real ids, so an agent can look up words and spell phrases in Shavian. Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `open_search` | Restart the app and read the search screen. | none |
| `search_word` | Search an English word or prefix and return the matching rows (word, Shavian spelling, type). | `word` |
| `get_entry` | Open the exact entry for an English word and return its Shavian spelling, IPA and word type. | `word` |
| `transliterate` | Write up to 8 English words in Shavian by looking each one up. | `text` |

## Toolkit

An agent can drive the whole app with these; compose them.

| Role | Action |
|---|---|
| Entry | open_search |
| Primitives | search_word, get_entry |
| Read state | transliterate |

## Install

The app: F-Droid, or `https://f-droid.org/packages/uk.co.busydoingnothing.pocketrl/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/pocket-readlex
```

## Use

```bash
ghost skill run ghost/pocket-readlex get_entry --param word=hello --device <serial>
```

```python
run_skill(name="ghost/pocket-readlex", action="transliterate", params={"text": "hello world"})
```

Try asking: "Write hello world in the Shavian alphabet using Pocket ReadLex and show me the IPA for hello."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), Pocket ReadLex 1. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 1 | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.0 | 2026-11-02 |

### Recorded failures

- Only English letters, apostrophes and hyphens are accepted.
- A word the dictionary does not know shows as ? in transliterate.

### Popups and first-run screens handled

- None.
