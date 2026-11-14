# weather - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on, and how success is recognised, so an agent can adapt it to another weather app or version.

**Package**: `org.breezyweather` (Breezy Weather, LGPL-3.0 FOSS app, freenet build 6.2.2 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-10-05 on a headless emulator pool, Android 14 google_apis x86_64, 1080x2400 @ 420 dpi, en-US (temperatures in °F). No account. No GPS: locations are added by name.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- Locations screen: rows `id/container` with `id/title1` (name) and `id/title2` (current condition). "Add a new location" is button text when the list is empty and a FAB description otherwise. "Add current location" (GPS) is never used. A "Stay informed" notifications card may sit at the top; it is left alone.
- Search (`SearchActivity`): field "Search for a location…", results are pairs of lines (name, then region such as "Germany, State of Berlin, ..."), footer "Location results by Open-Meteo (CC BY 4.0) • GeoNames".
- After picking a result, a "Weather sources" sheet shows the free default sources (Bright Sky/DWD, Open-Meteo); `Save` accepts them.
- Weather view: toolbar "Location list" button and the location name; `id/container_main_header_weather_condition_description`, `id/container_main_header_temperature_value` and `_unit`, `id/container_main_header_feels_like`, `id/container_main_header_temperature_range`, `id/refreshTimeText` (desc "Last updated ..."). Daily cards `id/item_trend_daily` carry the whole forecast in their content-desc: "Conditions, Tomorrow, October 6, Daytime: 67 degrees Fahrenheit, Partly cloudy, Precipitation probability: 2%, Nighttime: ...".

## Top-band safety

The "Location list" button and the first search results sit where heads-up notifications appear; taps there go through `guarded_tap` (refuses while SystemUI's `mHeadsUpPinnedMode` is true).

## Actions

### `add_location(query, country="", region="", match="")`

Locations > Add a new location > type the city > Enter. Read every visible name/region pair, including the first row above y=290 on Samsung. Filter by exact displayed country and optional state/region; legacy match is an additional filter. Save only when exactly one result remains. If ambiguous or unmatched, return candidates and ask for country/region; never select the first result as a fallback. Success requires matching selected-country evidence and the saved city. The Locations list itself omits country.

### `list_locations()`

Read the rows: `{name, condition}`. Empty list on a fresh install.

### `get_current_weather(location)`

Open the saved location (exact name, else substring) and read the header. Returns `weather: {location, condition, temperature, unit, feels_like, range, updated}`.

### `get_daily_forecast(location)`

Open the saved location and parse every visible daily card into `{day, date, day_temp, day_condition, precip_probability, night_temp, night_condition}` (precipitation: the higher of day and night).

## Failure modes

- Needs network for search and forecasts.
- Units follow the app setting (°F for en-US by default); values are returned as displayed.
