# maps

Demo shows: `get_directions (origin=Alexanderplatz Berlin, destination=Brandenburg Gate, mode=walking)`

> Ghost in the Droid seed skill for Google Maps (`com.google.android.apps.maps`), used without signing in.

| Action | What it does | Params |
|---|---|---|
| `search_place` | Look up a place, return name, rating, reviews, address/category lines | `query` |
| `list_places` | Return the top N search results | `query`, `max_results` (default 5) |
| `show_location` | Identify what Maps shows at coordinates | `lat`, `lng` |
| `get_directions` | Route summary (duration, distance, via; transit adds times and fare) | `origin`, `destination`, `mode` (driving, walking, bicycling, transit) |

## Install

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/maps
```

## Use

```bash
ghost skill run ghost/maps search_place --param "query=Eiffel Tower" --device emulator-5554
ghost skill run ghost/maps get_directions --param "origin=Alexanderplatz Berlin" \
  --param "destination=Brandenburg Gate Berlin" --param mode=walking --device emulator-5554
```

From any MCP agent:

```python
run_skill(name="ghost/maps", action="get_directions",
          params={"origin": "Alexanderplatz Berlin", "destination": "Brandenburg Gate Berlin", "mode": "walking"})
# {"route": {"mode": "walking", "duration": "34 min", "distance": "2.5 km", "via": "via B2 and Unter den Linden", ...}}
```

## Tested on

Android 14 emulator (google_apis x86_64, 1080x2400, 420 dpi), Maps 11.71, en-US, fresh and reused app state. Signed self-runs live in `runs/`.

## Notes

Uses only public Maps intents and reads the screen; never signs in, never starts navigation, never saves places. `ghost/google_maps` is the older migrated v1 skill; prefer this one on fresh devices. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Signed self-runs (pass/total) | Dates |
|---|---|---|---|---|---|
| 11.71.0300 | 14 | Google/sdk_gphone64_x86_64 (emulator, 1080x2400, 420 dpi, en-US) | 1.0.0, 1.0.1 | 12/12 | 2026-10-05 |

Untested so far: physical devices, other OEM skins, other screen sizes, other locales.

### Recorded failures

None in the signed self-runs.

### Popups and first-run screens handled

- First-run sign-in upsell (never sign in)
- Location History upsell

### Other known failure modes

- Ambiguous queries can open the wrong card; pass city or country.
- Transit coverage varies by region; when no transit route exists the action fails with `no route summary`.
