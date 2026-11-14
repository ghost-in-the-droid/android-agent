---
generated_with: ghost skill migrate
source: v1 class docstrings, elements*.yaml, recorded.json, FLOW.md
---

# play_store: SOFT notes (LLM-adaptable narrative)

Google Play Store automation: install, uninstall, update apps, check versions

Target: `com.android.vending` on android. Each action below wraps the v1 implementation unchanged (see `helpers.py`); this file is the reference an agent uses to adapt the skill when the replay fails on a different device or app version.

## Actions

### `install_by_name(query)`

v1 workflow `install_by_name` (`InstallByName` in `workflows.py`).

Search for an app by name and install the first result.

Params:

- `query` (str)

Success: the wrapped v1 run reports success (`helpers:v1_ok`); the v1 class decides via its own precondition, execute result and postcondition.

### `open_store()`

v1 action `open_store` (`OpenStore` in `actions/core.py`).

Open the Google Play Store app.

Success: the wrapped v1 run reports success (`helpers:v1_ok`); the v1 class decides via its own precondition, execute result and postcondition.

### `search_app(query)`

v1 action `search_app` (`SearchApp` in `actions/core.py`).

Search for an app in Play Store.

Params:

- `query` (str)

Success: the wrapped v1 run reports success (`helpers:v1_ok`); the v1 class decides via its own precondition, execute result and postcondition.

### `install_app(package)`

v1 action `install_app` (`InstallApp` in `actions/core.py`).

Install an app from Play Store by package name.

Params:

- `package` (str)

Success: the wrapped v1 run reports success (`helpers:v1_ok`); the v1 class decides via its own precondition, execute result and postcondition.

### `uninstall_app(package)`

v1 action `uninstall_app` (`UninstallApp` in `actions/core.py`).

Uninstall an app via ADB.

Params:

- `package` (str)

Success: the wrapped v1 run reports success (`helpers:v1_ok`); the v1 class decides via its own precondition, execute result and postcondition.

### `update_app(package)`

v1 action `update_app` (`UpdateApp` in `actions/core.py`).

Update an app via Play Store.

Params:

- `package` (str)

Success: the wrapped v1 run reports success (`helpers:v1_ok`); the v1 class decides via its own precondition, execute result and postcondition.

### `check_version(package)`

v1 action `check_version` (`CheckVersion` in `actions/core.py`).

Check installed version of an app.

Params:

- `package` (str)

Success: the wrapped v1 run reports success (`helpers:v1_ok`); the v1 class decides via its own precondition, execute result and postcondition.

## Login state

Open the signed-in account menu with Manage apps & device visible before search, install or update actions. Opening the store, local uninstall and version checks do not require this state. The read-only `logged_in` probe checks that positive selector on the current screen. A different screen, language or UI version can return missing/unknown even while a session exists; the runner then stops with `needs_state` rather than guessing. This skill has no automatic login provider. auto-login runner: beta.
