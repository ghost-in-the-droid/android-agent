# Control Regex Crossword on Android with an AI agent

**Control Regex Crossword on Android with an AI agent.** Solve regex crosswords on your phone: an agent opens a level, reads the regex clues, fills the grid and verifies.

Target search phrase: _AI agent solves regex crossword on Android_

Demo shows: `list_levels (category=Tutorial)`

> Ghost in the Droid seed skill for Regex Crossword (`de.chagemann.regexcrossword`), an offline crossword whose clues are regular expressions. Clues, cells and the Verify result are all readable, so an agent can reason about the regexes, type the letters and check the answer. Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `list_levels` | List the categories and how many levels are solved | none |
| `open_level` | Open a level; returns the clues and the grid | `category`, `level` |
| `get_puzzle` | Read clues (regexes) and the grid typed so far | none |
| `enter` | Type the grid, rows separated by slashes (II/AB) | `rows` |
| `verify` | Press Verify; reports solved plus the dialog text | none |

## Toolkit

An agent can drive the whole app with these; compose them.

| Role | Action |
|---|---|
| Entry | open_level |
| Primitives | enter, verify |
| Read state | get_puzzle, list_levels |

## Install

The app: F-Droid, or `https://f-droid.org/packages/de.chagemann.regexcrossword/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/regex-crossword
```

## Use

```bash
ghost skill run ghost/regex-crossword open_level --param category=Tutorial --param level=Backreference --device <serial>
ghost skill run ghost/regex-crossword enter --param 'rows=I/I' --device <serial>
```

```python
run_skill(name="ghost/regex-crossword", action="verify")
# {"result": {"solved": true, "title": "Level Completed!", ...}}
```

Try asking: "Open the Backreference level of the regex crossword tutorial, read the clues, solve it and verify."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), Regex Crossword 33. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 33 | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.0 | 2026-11-02 |

### Recorded failures

- Letters are typed in upper case through adb text input (letters, digits and space only).
- The Level Completed dialog stays open; the next action backs out of it.
- Only Latin letters, digits and space can be typed.

### Popups and first-run screens handled

- None.
