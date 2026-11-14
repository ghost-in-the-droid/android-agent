# Control Geological Time Scale on Android with an AI agent

**Control Geological Time Scale on Android with an AI agent.** How old is the Jurassic? Your agent reads the time scale and tells you the dates.

Target search phrase: _AI agent looks up the geological time scale on Android_

Demo shows: `lookup_unit (name=Jurassic)`

> Ghost in the Droid seed skill for Geological Time Scale (`org.tengel.timescale`), an offline geological time scale. The coloured table cells are text nodes, so an agent can answer when a period began and how units nest. Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `open_timescale` | Restart the app and read the time scale table at its default zoom. | none |
| `get_scale` | Read the table now shown: every row with its parent units, the unit name and its start in million years ago. | none |
| `zoom_in` | Zoom one level deeper (eras, periods, epochs, ages) and return the table. | none |
| `zoom_out` | Zoom one level out and return the table. | none |
| `lookup_unit` | Find a unit by name (Jurassic, Cambrian, Holocene ...), zooming in until it shows, and return its hierarchy and when it started in million years ago. | `name` |

## Toolkit

An agent can drive the whole app with these; compose them.

| Role | Action |
|---|---|
| Entry | open_timescale |
| Primitives | zoom_in, zoom_out |
| Read state | get_scale, lookup_unit |

## Install

The app: F-Droid, or `https://f-droid.org/packages/org.tengel.timescale/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/geological-timescale
```

## Use

```bash
ghost skill run ghost/geological-timescale lookup_unit --param name=Jurassic --device <serial>
```

```python
run_skill(name="ghost/geological-timescale", action="lookup_unit", params={"name": "Jurassic"})
# {"result": {"unit": "Jurassic", "start_mya": 201.4, "end_mya": 145.0, ...}}
```

Try asking: "When did the Jurassic period start and end? Look it up in the geological time scale."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), Geological Time Scale 14. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 14 | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.0 | 2026-11-02 |

### Recorded failures

- A unit that is not in the table raises an error.
- Rows that scroll off the screen are not read.

### Popups and first-run screens handled

- None.
