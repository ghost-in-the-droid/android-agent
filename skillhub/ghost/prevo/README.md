# Control PReVo on Android with an AI agent

**Control PReVo on Android with an AI agent.** Your agent looks words up in a full Esperanto dictionary offline: search in English, German or French and get the Esperanto word with its translations.

Target search phrase: _AI agent looks up Esperanto words with an offline dictionary on Android_

Demo shows: `search (term=water)`

> Ghost in the Droid seed skill for PReVo (`uk.co.busydoingnothing.prevo`), an offline Esperanto dictionary. The language list, search results and entry sections are text nodes, so an agent can look up a word and read its Esperanto form and translations. Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `open_dictionary` | Restart the app, pick the dictionary language on first launch and open the search screen. | `language` |
| `search` | Type a word into the search box and return the matching headwords. | `term` |
| `open_entry` | Search a word, open its entry and read the Esperanto headword and a translation. | `term`, `language` |
| `get_entry` | Read the open entry: headword and the translation in the given language. | `language` |
| `back_to_search` | Return from an entry to the search screen. | none |

## Toolkit

An agent can drive the whole app with these; compose them.

| Role | Action |
|---|---|
| Entry | open_dictionary |
| Primitives | search, open_entry, back_to_search |
| Read state | get_entry |

## Install

The app: F-Droid, or `https://f-droid.org/packages/uk.co.busydoingnothing.prevo/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/prevo
```

## Use

```bash
ghost skill run ghost/prevo open_entry --param term=cat --device <serial>
```

```python
run_skill(name='ghost/prevo', action='open_entry', params={'term': 'cat'})
# {"result": {"headword": "kat/o", "translation": "~o: cat, puss, pussy, pussycat; ~a: feline; ..."}}
```

Try asking: "Look up the English word cat in the Esperanto dictionary, then tell me the Esperanto word and its French translation."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), PReVo 27. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 27 | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.0 | 2026-11-02 |

### Recorded failures

- A term with no result raises an error.
- A language with no section in the entry returns an empty translation.

### Popups and first-run screens handled

- None.
