# maps - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on, and how success is recognised, so an agent can adapt it to another Maps version or map app.

**Package**: `com.google.android.apps.maps` (Google Maps)
**Verified**: 2026-10-05 on a headless emulator pool, Android 14 google_apis x86_64, 1080x2400 @ 420 dpi, Maps 11.71.0300, en-US, German IP, never signed in.
**Skill class**: HARD. No login, no checkpoints.

## How it drives Maps

Every action fires a public intent instead of typing: `geo:0,0?q=<query>` for searches, `geo:<lat>,<lng>?q=<lat>,<lng>` for coordinates, and `https://www.google.com/maps/dir/?api=1&origin=..&destination=..&travelmode=<mode>` for routes. Values are percent-encoded in `helpers.encode`. Maps reuses its running activity, so the previous screen stays up for a moment after the intent: readers wait until the screen is fresh (omnibox shows the query, the route header shows both end points and the right mode, or the screen signature changed).

Maps uses Compose; most nodes have no resource id. Landmarks:
- Place card: a name node whose `text == content-desc`, detail lines below it (rating as `4.7 stars (190,475)`, address, category, hours), then a button with desc `Directions to <name>, <address>`.
- Result list: each result has a node with resource id `title`; detail lines follow. Sponsored entries start with `Ad ·` and are skipped.
- Route (driving, walking, bicycling): one node whose desc reads `walking. 34 minutes. via B2 and Unter den Linden. 2.5 km. Activate to open step list`; children hold `34 min`, `(2.5 km)`, `via ...`.
- Route (transit): the screen desc is `transit directions`; trip cards have id `directions_trip_card` with legs (`U5, then Walk for 4 min`), duration, `8:12 PM – 8:21 PM`, and a fare like `€4`.

## Actions

### `search_place(query)`

Return the place card for the query (or the first result when Maps shows a list): `{name, rating, reviews, details[]}`.

### `list_places(query, max_results)`

Return up to `max_results` results from the result list, scrolling as needed. A query with one exact match opens a card; that card is returned as the only result.

### `show_location(lat, lng)`

Return the place Maps resolves at the coordinates. Maps snaps to a nearby business or landmark, so the name can be in the local language; the address line is in `details`.

### `get_directions(origin, destination, mode)`

Return the recommended route: `{mode, duration, distance, via, summary}` (transit adds `times` and `fare`). Navigation is never started.

## Popups and first run

A never-signed-in Maps shows "Make it your map" with `Sign in` and `SKIP`; the skill always taps `SKIP`. No location permission is requested because the skill never asks for "my location".

## Failure modes

- Ambiguous queries can open the wrong card; pass city or country.
- Transit coverage varies by region; when no transit route exists the action fails with `no route summary`.
