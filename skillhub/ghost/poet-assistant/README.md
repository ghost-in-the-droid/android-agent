# Control Poet Assistant on Android with an AI agent

**Control Poet Assistant on Android with an AI agent.** Find rhymes, synonyms and definitions offline: an agent looks a word up and reads the lists.

Target search phrase: _AI agent finds rhymes and synonyms on Android_

Demo shows: `lookup (word=love, mode=rhymes)`

> Ghost in the Droid seed skill for Poet Assistant (`ca.rmen.android.poetassistant`), an offline rhyming dictionary, thesaurus and dictionary for writers. Result rows are plain text, so an agent can fetch exact rhymes, synonyms and definitions. Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `open_poet` | Restart the app and read its state. | none |
| `lookup` | Look a word up and return the result of one tab: rhymes (default), thesaurus (synonyms and antonyms per part of speech) or dictionary (definitions). | `word`, `mode` |
| `get_results` | Read the result list of the tab that is currently shown. | none |

## Toolkit

An agent can drive the whole app with these; compose them.

| Role | Action |
|---|---|
| Entry | open_poet |
| Primitives | lookup |
| Read state | get_results |

## Install

The app: F-Droid, or `https://f-droid.org/packages/ca.rmen.android.poetassistant/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/poet-assistant
```

## Use

```bash
ghost skill run ghost/poet-assistant lookup --param word=love --param mode=rhymes --device <serial>
```

```python
run_skill(name="ghost/poet-assistant", action="lookup", params={"word": "love", "mode": "rhymes"})
# {"result": {"result": {"groups": {"Strict rhyme matches": ["above", "dove", "glove"]}}}}
```

Try asking: "Find words that rhyme with love and then give me synonyms for love."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), Poet Assistant 113201. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 113201 | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.0 | 2026-11-02 |

### Recorded failures

- The word must be ASCII letters.
- Long lists are scrolled and read; very long rhyme lists are cut after about five screens.
- An unknown word returns an empty or short list.

### Popups and first-run screens handled

- None.
