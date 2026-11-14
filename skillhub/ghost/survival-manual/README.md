# Control Survival Manual on Android with an AI agent

**Control Survival Manual on Android with an AI agent.** No signal and need survival advice? Your agent opens the right chapter and reads it out.

Target search phrase: _AI agent reads an offline survival manual on Android_

Demo shows: `open_chapter (name=Fire)`

> Ghost in the Droid seed skill for Survival Manual (`org.ligi.survivalmanual`), an offline survival guide. The chapter drawer and the chapter text are real text nodes, so an agent can look up how to make fire, find water or tie a knot without internet. Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `open_manual` | Restart the app and read the first page of the manual (Introduction). | none |
| `list_chapters` | Open the chapter drawer and list every chapter name. | none |
| `open_chapter` | Open a chapter by name (for example Water, Fire, Shelter) and return the text shown. | `name` |
| `read_page` | Read the text currently visible on the chapter page. | none |
| `scroll_page` | Scroll down one to five screens and return the new visible text. | `pages` |

## Toolkit

An agent can drive the whole app with these; compose them.

| Role | Action |
|---|---|
| Entry | open_manual |
| Primitives | open_chapter, scroll_page |
| Read state | list_chapters, read_page |

## Install

The app: F-Droid, or `https://f-droid.org/packages/org.ligi.survivalmanual/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/survival-manual
```

## Use

```bash
ghost skill run ghost/survival-manual open_chapter --param name=Fire --device <serial>
```

```python
run_skill(name="ghost/survival-manual", action="open_chapter", params={"name": "Fire"})
# {"result": {"chapter": "Fire", "state": {"text": "In many survival situations, ..."}}}
```

Try asking: "Open the Fire chapter of the survival manual and tell me the first things it says about starting a fire."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), Survival Manual 500. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 500 | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.0 | 2026-11-02 |

### Recorded failures

- A chapter name that does not exist raises an error listing the real chapters.
- Pictures and figures are not readable.

### Popups and first-run screens handled

- None.
