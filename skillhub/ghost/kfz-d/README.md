# Control KFZ-D on Android with an AI agent

**Control KFZ-D on Android with an AI agent.** Spot a German car plate? Your agent decodes the letters into the city or district and state.

Target search phrase: _AI agent decodes German licence plates on Android_

Demo shows: `lookup (code=M)`

> Ghost in the Droid seed skill for KFZ-D (`de.herk.kfzd`), an offline lookup of German vehicle registration codes. The code field and the three result blocks are text nodes, so an agent can decode plates. Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `open_lookup` | Restart the app and read the lookup screen. | none |
| `lookup` | Look up one German plate code (1 to 3 letters) and return district, federal state and type. | `code` |
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

The app: F-Droid, or `https://f-droid.org/packages/de.herk.kfzd/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/kfz-d
```

## Use

```bash
ghost skill run ghost/kfz-d lookup --param code=M --device <serial>
```

```python
run_skill(name="ghost/kfz-d", action="lookup", params={"code": "M"})
# {"result": {"code": "M", "district": ["München, Landeshauptstadt", ...], "state": ["Bayern"]}}
```

Try asking: "Which city and federal state does the German licence plate code M stand for? Then look up HH."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), KFZ-D 6. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 6 | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.0 | 2026-11-02 |

### Recorded failures

- Codes are 1 to 3 letters; digits are not accepted.
- Unknown codes return No match.

### Popups and first-run screens handled

- None.
