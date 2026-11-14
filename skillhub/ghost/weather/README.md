# Control Breezy Weather on Android with an AI agent — read weather forecasts

Demo shows: `get_current_weather (location=Berlin)`

> Ghost in the Droid seed skill for Breezy Weather (`org.breezyweather`), a FOSS weather app from F-Droid. No account, no GPS.

| Action | What it does | Params |
|---|---|---|
| `add_location` | Search a city by name and save it | `query`, `country`, `region`, legacy `match` |
| `list_locations` | Saved cities with their current condition | none |
| `get_current_weather` | Condition, temperature, feels-like, day range | `location` |
| `get_daily_forecast` | Daily day/night temperatures, conditions, rain chance | `location` |

## Install

Install the app from F-Droid (`org.breezyweather`), then:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/weather
```

## Use

```bash
ghost skill run ghost/weather add_location --param query=Berlin --param country=Germany --device emulator-5554
ghost skill run ghost/weather get_current_weather --param location=Berlin --device emulator-5554
```

From any MCP agent:

```python
run_skill(name="ghost/weather", action="get_daily_forecast", params={"location": "Berlin"})
# {"daily": [{"day": "Tomorrow", "date": "October 6", "day_temp": "67 degrees Fahrenheit", "precip_probability": 2, ...}]}
```

## Tested on

Android 14 emulator (google_apis x86_64, 1080x2400, 420 dpi), Breezy Weather 6.2.2 (freenet), en-US. Signed self-runs live in `runs/`.

## Notes

Never uses "Add current location"; no location permission is requested. License: MIT (the skill; the app is LGPL-3.0).

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Signed self-runs (pass/total) | Dates |
|---|---|---|---|---|---|
| 6.2.2_freenet | 14 | Google/sdk_gphone64_x86_64 (emulator, 1080x2400, 420 dpi, en-US) | 1.0.0 | 12/12 | 2026-10-05 |

Samsung SM-A156B regression target: Android 16 Samsung SM-A156B, Breezy Weather 6.2.2 freenet, English UI. Three consecutive clean-reset add_location(query=Berlin, country=Germany) replays passed on 2026-11-03 (8.77s, 7.45s, 7.53s). Earlier outcomes above are historical; only current digest-bound signed runs establish current coverage. Other OEM skins/locales remain untested.

### Recorded failures

The Samsung SM-A156B comparison exposed a wrong-city result: a fixed y>290 filter dropped Germany’s first row (y=280), and a missing region match silently fell back to the first remaining Berlin. Version 1.0.1 removes the pixel cutoff and refuses ambiguous or unmatched results. The validator checks selected country/region evidence and the saved city.

### Popups and first-run screens handled

- Notification permission prompt

### Other known failure modes

- Needs network for search and forecasts.
- Units follow the app setting (°F for en-US by default); values are returned as displayed.

### Location disambiguation

For common names, pass the displayed English country and optionally a state/region. `country=United States, region=New Hampshire` and `country=Germany` select different Berlins. No qualifier is accepted only when exactly one result remains. Ambiguous or unmatched searches return candidate names/regions and fail before saving; the caller must ask the user rather than guess. Legacy `match` remains supported, with no first-result fallback. The final city list does not display country, so validation retains the selected search-row country as evidence and checks it against the requested qualifiers and saved name.

Recorded setup failure: an accessibility-bridge port collision forced native UI Automator fallback. On the tested build, that fallback omits saved city rows even though the card is visible. The validator correctly refused success. Use a unique per-device alias/bridge port; do not accept pixels or weaken country/list readback. The failed diagnostic logs are preserved separately; stale-digest artifacts are pruned before the final replay.
