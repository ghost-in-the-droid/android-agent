---
generated_with: ghost skill migrate
source: v1 class docstrings, elements*.yaml, recorded.json, FLOW.md
---

# safari: SOFT notes (LLM-adaptable narrative)

Configurable iOS Chrome/browser smoke automation

Target: `com.google.chrome.ios` on ios. Each action below wraps the v1 implementation unchanged (see `helpers.py`); this file is the reference an agent uses to adapt the skill when the replay fails on a different device or app version.

## Actions

### `open_ghost_site(url, bundle_id)`

v1 workflow `open_ghost_site` (`OpenGhostSite` in `workflows.py`).

Open ghostinthedroid.com in the configured iOS browser

Params:

- `url` (str, default `https://ghostinthedroid.com`)
- `bundle_id` (str)

Success: the wrapped v1 run reports success (`helpers:v1_ok`); the v1 class decides via its own precondition, execute result and postcondition.

### `read_news(url, max_headlines, max_articles, bundle_id, wait_s, save_screenshots, out_dir)`

v1 workflow `read_news` (`ReadNewsWorkflow` in `workflows.py`).

Read headlines and article snippets from a text-friendly news site in iOS Chrome/browser

Params:

- `url` (str, default `https://text.npr.org/`)
- `max_headlines` (int, default `5`)
- `max_articles` (int, default `3`)
- `bundle_id` (str)
- `wait_s` (float, default `2.0`)
- `save_screenshots` (bool, default `False`)
- `out_dir` (str)

Success: the wrapped v1 run reports success (`helpers:v1_ok`); the v1 class decides via its own precondition, execute result and postcondition.

### `open_browser(bundle_id)`

v1 action `open_browser` (`OpenBrowser` in `actions/core.py`).

Launch the configured iOS browser

Params:

- `bundle_id` (str)

Success: the wrapped v1 run reports success (`helpers:v1_ok`); the v1 class decides via its own precondition, execute result and postcondition.

### `open_safari(bundle_id)`

v1 action `open_safari` (`OpenSafari` in `actions/core.py`).

Launch the configured iOS browser; kept as a compatibility alias

Params:

- `bundle_id` (str)

Success: the wrapped v1 run reports success (`helpers:v1_ok`); the v1 class decides via its own precondition, execute result and postcondition.

### `open_url(url)`

v1 action `open_url` (`OpenUrl` in `actions/core.py`).

Open a URL in the active iOS browser

Params:

- `url` (str, default `https://ghostinthedroid.com`)

Success: the wrapped v1 run reports success (`helpers:v1_ok`); the v1 class decides via its own precondition, execute result and postcondition.

### `verify_page(expected)`

v1 action `verify_page` (`VerifyPage` in `actions/core.py`).

Verify expected text is visible in the iOS browser source

Params:

- `expected` (str, default `ghostinthedroid`)

Success: the wrapped v1 run reports success (`helpers:v1_ok`); the v1 class decides via its own precondition, execute result and postcondition.

### `read_news_action(url, max_headlines, max_articles, bundle_id, wait_s, save_screenshots, out_dir)`

v1 action `read_news` (`ReadNews` in `actions/core.py`).

Open a news site in iOS Chrome/browser and extract headlines plus article snippets

Params:

- `url` (str, default `https://text.npr.org/`)
- `max_headlines` (int, default `5`)
- `max_articles` (int, default `3`)
- `bundle_id` (str)
- `wait_s` (float, default `2.0`)
- `save_screenshots` (bool, default `False`)
- `out_dir` (str)

Success: the wrapped v1 run reports success (`helpers:v1_ok`); the v1 class decides via its own precondition, execute result and postcondition.

## UI landmarks (iOS, from `elements_ios.yaml`)

Locators in priority order: resource id, content-desc, text. Verify them against a fresh a11y dump before relying on them on a different app version.

- `address_field`: content_desc=`Address`
- `tab_overview`: content_desc=`Tabs`
- `share`: content_desc=`Share`
