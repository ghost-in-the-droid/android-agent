---
generated_with: ghost skill migrate
source: v1 class docstrings, elements*.yaml, recorded.json, FLOW.md
---

# google_maps: SOFT notes (LLM-adaptable narrative)

Google Maps: search places and fetch directions with per-mode ETA and distance

Target: `com.google.android.apps.maps` on android. Each action below wraps the v1 implementation unchanged (see `helpers.py`); this file is the reference an agent uses to adapt the skill when the replay fails on a different device or app version.

## Actions

### `get_directions(destination, mode)`

v1 workflow `get_directions` (`GetDirections` in `workflows/get_directions.py`).

Search a destination and return route summary (ETA, distance, per-mode times)

Params:

- `destination` (str)
- `mode` (str, default `driving`)

Success: the wrapped v1 run reports success (`helpers:v1_ok`); the v1 class decides via its own precondition, execute result and postcondition.

### `open_app()`

v1 action `open_app` (`OpenApp` in `actions/core.py`).

Force-stop Google Maps and relaunch to the explore/home screen.

Success: the wrapped v1 run reports success (`helpers:v1_ok`); the v1 class decides via its own precondition, execute result and postcondition.

### `search_place(query)`

v1 action `search_place` (`SearchPlace` in `actions/core.py`).

Type a place into the search box and land on its place card.

Handles both outcomes of a search: direct hit (place card opens) and
results list (taps the first result). Steps are linear in a Workflow,
so this branching lives inside one action.

Params:

- `query` (str)

Success: the wrapped v1 run reports success (`helpers:v1_ok`); the v1 class decides via its own precondition, execute result and postcondition.

### `open_directions()`

v1 action `open_directions` (`OpenDirections` in `actions/core.py`).

Tap the Directions button on an open place card.

Success: the wrapped v1 run reports success (`helpers:v1_ok`); the v1 class decides via its own precondition, execute result and postcondition.

### `select_travel_mode(mode)`

v1 action `select_travel_mode` (`SelectTravelMode` in `actions/core.py`).

Select a travel mode tab (driving / transit / walking / cycling).

Params:

- `mode` (str, default `driving`)

Success: the wrapped v1 run reports success (`helpers:v1_ok`); the v1 class decides via its own precondition, execute result and postcondition.

### `read_route_summary(mode)`

v1 action `read_route_summary` (`ReadRouteSummary` in `actions/core.py`).

Parse the directions screen into structured route data. Read-only.

Params:

- `mode` (str)

Success: the wrapped v1 run reports success (`helpers:v1_ok`); the v1 class decides via its own precondition, execute result and postcondition.

### `close_card()`

v1 action `close_card` (`CloseCard` in `actions/core.py`).

Close the current place card or directions view.

Success: the wrapped v1 run reports success (`helpers:v1_ok`); the v1 class decides via its own precondition, execute result and postcondition.

## UI landmarks (Android, from `elements.yaml`)

Locators in priority order: resource id, content-desc, text. Verify them against a fresh a11y dump before relying on them on a different app version.

- `search_box`: resource_id=`com.google.android.apps.maps:id/search_omnibox_text_box`
- `search_clear`: resource_id=`com.google.android.apps.maps:id/search_omnibox_text_clear`
- `close_card`: resource_id=`com.google.android.apps.maps:id/terra_navigation_header_close_button`
- `trip_summary`: resource_id=`com.google.android.apps.maps:id/trip_details_summary_header`
- `route_options`: resource_id=`com.google.android.apps.maps:id/directions_header_preference_action_button`
- `mode_tabs`: resource_id=`com.google.android.apps.maps:id/directions_mode_tabs`
- `start_navigation`: content_desc=`Start`
- `swap_start_destination`: content_desc=`Swap start and destination`
- `add_stops`: content_desc=`Add stops`
