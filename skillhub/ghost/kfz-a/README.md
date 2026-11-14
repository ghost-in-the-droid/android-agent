# Control KFZ-A on Android with an AI agent

**Control KFZ-A on Android with an AI agent.** Spot an Austrian car plate? Your agent decodes the letters into the city or district and federal state.

Target search phrase: _AI agent decodes Austrian licence plates on Android_

Demo shows: `lookup (code=W)`

> Ghost in the Droid seed skill for KFZ-A (`de.herk.kfza`), an offline lookup of Austrian vehicle registration codes. The code field and the three result blocks are text nodes, so an agent can decode plates. Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `open_lookup` | Restart the app and read the lookup screen. | none |
| `lookup` | Look up one Austrian plate code (1 to 3 letters) and return district, federal state and type. | `code` |
| `lookup_many` | Look up several plate codes in a row (comma separated, up to 15). | `codes` |
| `get_result` | Read the result currently shown. | none |

## Toolkit

An agent can drive the whole app with these; compose them.

| Role | Action |
|---|---|
| Entry | open_lookup |
| Primitives | lookup, lookup_many |
| Read state | get_result |

## Install

The app: F-Droid, or `https://f-droid.org/packages/de.herk.kfza/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/kfz-a
```

## Use

```bash
ghost skill run ghost/kfz-a lookup --param code=W --device <serial>
```

```python
run_skill(name="ghost/kfz-a", action="lookup", params={"code": "W"})
```

Try asking: "Which Austrian city and federal state does the licence plate code W stand for? Then look up GU."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), KFZ-A 5. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 5 | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.0 | 2026-11-02 |

### Recorded failures

- Codes are 1 to 3 letters; digits are not accepted.
- Unknown codes return No match.

### Popups and first-run screens handled

- None.
