---
generated_with: ghost skill migrate
source: v1 class docstrings, elements*.yaml, recorded.json, FLOW.md
---

# tiktok_ios: SOFT notes (LLM-adaptable narrative)

TikTok iOS automation smoke skill using Appium/WebDriverAgent

Target: `com.zhiliaoapp.musically` on ios. Each action below wraps the v1 implementation unchanged (see `helpers.py`); this file is the reference an agent uses to adapt the skill when the replay fails on a different device or app version.

## Actions

### `open_app_smoke()`

v1 workflow `open_app_smoke` (`OpenAppSmoke` in `workflows.py`).

Launch TikTok on iOS and dismiss common first-run prompts

Success: the wrapped v1 run reports success (`helpers:v1_ok`); the v1 class decides via its own precondition, execute result and postcondition.

### `search_smoke(query, max_lines, wait_timeout)`

v1 workflow `search_smoke` (`SearchSmoke` in `workflows.py`).

Launch TikTok on iOS, open search, and submit a query

Params:

- `query` (str, default `#fyp`)
- `max_lines` (int, default `80`)
- `wait_timeout` (float, default `8.0`)

Success: the wrapped v1 run reports success (`helpers:v1_ok`); the v1 class decides via its own precondition, execute result and postcondition.

### `profile_smoke(max_lines, expected, wait_timeout)`

v1 workflow `profile_smoke` (`ProfileSmoke` in `workflows.py`).

Launch TikTok on iOS, navigate to Profile, and capture visible text evidence

Params:

- `max_lines` (int, default `80`)
- `expected` (str, default `Profile`)
- `wait_timeout` (float, default `8.0`)

Success: the wrapped v1 run reports success (`helpers:v1_ok`); the v1 class decides via its own precondition, execute result and postcondition.

### `open_app()`

v1 action `open_app` (`OpenApp` in `actions/core.py`).

Launch TikTok on iOS

Success: the wrapped v1 run reports success (`helpers:v1_ok`); the v1 class decides via its own precondition, execute result and postcondition.

### `dismiss_popup()`

v1 action `dismiss_popup` (`DismissPopup` in `actions/core.py`).

Dismiss common TikTok iOS popups when visible

Success: the wrapped v1 run reports success (`helpers:v1_ok`); the v1 class decides via its own precondition, execute result and postcondition.

### `tap_search()`

v1 action `tap_search` (`TapSearch` in `actions/core.py`).

Tap TikTok iOS search control

Success: the wrapped v1 run reports success (`helpers:v1_ok`); the v1 class decides via its own precondition, execute result and postcondition.

### `type_and_search(query)`

v1 action `type_and_search` (`TypeAndSearch` in `actions/core.py`).

Type a query into TikTok iOS search and submit

Params:

- `query` (str)

Success: the wrapped v1 run reports success (`helpers:v1_ok`); the v1 class decides via its own precondition, execute result and postcondition.

### `navigate_to_profile()`

v1 action `navigate_to_profile` (`NavigateToProfile` in `actions/core.py`).

Tap TikTok iOS Profile tab

Success: the wrapped v1 run reports success (`helpers:v1_ok`); the v1 class decides via its own precondition, execute result and postcondition.

### `capture_visible_text(max_lines)`

v1 action `capture_visible_text` (`CaptureVisibleText` in `actions/core.py`).

Capture visible TikTok iOS text for workflow evidence

Params:

- `max_lines` (int, default `80`)

Success: the wrapped v1 run reports success (`helpers:v1_ok`); the v1 class decides via its own precondition, execute result and postcondition.

### `wait_visible_text(expected, timeout, interval, max_lines)`

v1 action `wait_visible_text` (`WaitVisibleText` in `actions/core.py`).

Wait until expected TikTok iOS text is visible

Params:

- `expected` (str, default `TikTok`)
- `timeout` (float, default `8.0`)
- `interval` (float, default `0.5`)
- `max_lines` (int, default `300`)

Success: the wrapped v1 run reports success (`helpers:v1_ok`); the v1 class decides via its own precondition, execute result and postcondition.

### `verify_visible_text(expected)`

v1 action `verify_visible_text` (`VerifyVisibleText` in `actions/core.py`).

Verify expected text appears in TikTok iOS XML

Params:

- `expected` (str, default `TikTok`)

Success: the wrapped v1 run reports success (`helpers:v1_ok`); the v1 class decides via its own precondition, execute result and postcondition.

## UI landmarks (iOS, from `elements_ios.yaml`)

Locators in priority order: resource id, content-desc, text. Verify them against a fresh a11y dump before relying on them on a different app version.

- `search_tab`: content_desc=`Search`, text=`Search`
- `search_field`: content_desc=`Search`, text=`Search`
- `profile_tab`: content_desc=`Profile`, text=`Profile`
- `close`: content_desc=`Close`, text=`Close`
