# Agent Tools Reference

The catalog of tools the LLM agent can call. Identical surface across both
inference paths so prompts/skills behave the same regardless of where the
model runs:

- **MCP server** (`gitd/mcp_server.py`) — exposed to `claude-code` over MCP. The CLI auto-prefixes them as `mcp__android-agent__<tool>`.
- **Local tool list** (`gitd/services/agent_tools.py` → `TOOLS`) — exposed to the on-device Gemma provider (`agent_chat_ondevice.py`) and any other in-process tool-using loop.

Both paths execute the same underlying logic — for tools with non-trivial
behavior (e.g. `web_search`) they share a service module so there's one
implementation, not two drifts.

## App lifecycle

### `launch_app(device, package, fresh=false)`

Launch an Android app by package name.

| arg | type | required | default | notes |
|---|---|---|---|---|
| `device` | str | yes | — | ADB serial |
| `package` | str | yes | — | e.g. `com.android.chrome` |
| `fresh` | bool | no | `false` | If `true`, force-stop the app first (cold start). Use for benchmarks or when prior in-app state would interfere. If `false` (default), warm start — resumes wherever the user left off. |

The LLM picks based on context: a benchmark task or "open Reddit fresh" → `fresh=true`. "Go back to Chrome" / general use → `fresh=false`.

### `force_stop(device, package)`

Kill an app outright. No relaunch.

### `search_apps(device, query)` / `list_apps(device)` / `list_packages(device)`

Find package names. Use `search_apps` first, fall back to `list_apps`.

## Web

### `web_search(device, query, engine="google")`

Open a search results page in whatever browser is on the device. Faster than
`launch_app(chrome) → tap_element(address bar) → type_text → press_enter`
(four steps collapsed to one).

| arg | type | required | default | notes |
|---|---|---|---|---|
| `device` | str | yes | — | ADB serial |
| `query` | str | yes | — | Free-text. Don't pre-URL-encode — the tool handles it. |
| `engine` | str | no | `"google"` | One of `google`, `ddg` / `duckduckgo`, `bing`, `brave`. |

#### How fallback works

Implemented in `gitd/services/web_search.py:open_search`:

1. Build the search URL: e.g. `https://www.google.com/search?q=<urlencoded>`.
2. One ADB call probes installed packages: `pm list packages` → set.
3. Walk a priority list of browsers, skipping ones that aren't installed:

   Chrome → Firefox → Samsung Internet → Edge → Brave → Opera → Opera GX → Vivaldi → DuckDuckGo Browser

4. For the first hit, fire `am start -a android.intent.action.VIEW -d <url> -p <pkg>`. Parse stdout for `Error:` / `no activities found` to detect failure.
5. If every priority browser failed (or none was installed), fire the same intent **without** `-p` and let Android resolve to whatever browser handles `VIEW`.
6. As a true last resort (e.g. an extreme stripped-down vendor build with zero browsers): open `market://search?q=browser&c=apps` to nudge the user to install one, and return a clear failure string the agent can show.

#### URL safety

The URL is passed to `subprocess` as a single argument (list form), so
`&` and `?` aren't interpreted by the shell. URL-encoding via
`urllib.parse.quote` covers the rest.

#### Examples

```python
web_search(device, "best gemma 4 benchmarks")            # → Chrome / Google
web_search(device, "self-hosted langfuse", engine="ddg") # → Chrome / DuckDuckGo
```

Both work the same when the model is `claude-code` (MCP) or `on-device` Gemma.

## Intents (escape hatch)

### `launch_intent(device, action, data, package, extras)`

Fire an arbitrary Android intent. Use when no dedicated tool fits.

```text
Open a URL:    action=android.intent.action.VIEW data=https://google.com
Open Settings: package=com.android.settings
Share text:    action=android.intent.action.SEND extras='{"android.intent.extra.TEXT": "hello"}'
```

## UI primitives

| tool | purpose |
|---|---|
| `tap(device, x, y)` | Raw coordinate tap. |
| `tap_element(device, idx)` | Tap by element index from `get_screen_tree`. Prefer this. |
| `swipe(device, direction)` | `up` / `down` / `left` / `right`. |
| `long_press(device, x, y, duration_ms=1000)` | Long-press for context menus. |
| `type_text(device, text)` | Type into the focused field. |
| `press_key(device, key)` | `BACK`, `HOME`, `ENTER`, etc. |

## Observation

| tool | purpose |
|---|---|
| `screenshot(device)` | Full PNG. Use when OCR / visual reasoning is needed. |
| `get_screen_tree(device)` | XML accessibility tree, indexed for `tap_element`. Cheaper than screenshots. |
| `get_phone_state(device)` | Foreground app, activity, keyboard state. The lightest "where am I?" probe. |
| `find_on_screen(device, text)` | Locate visible text via XML first, OCR fallback. |

## Notifications

| tool | purpose |
|---|---|
| `get_notifications(device)` | JSON of active notifications. |
| `open_notifications(device)` | Pull down the shade. |

---

## Adding a new tool

The convention is:

1. **Implementation** in a service module under `gitd/services/`. One module per
   feature area (`web_search.py`, `device_context.py`, etc.).
2. **MCP exposure** in `gitd/mcp_server.py` — a thin `@mcp.tool()` wrapper that
   imports from the service module. Docstring is what claude-code sees.
3. **Local tool list** in `gitd/services/agent_tools.py`:
   - Add a dict to `TOOLS` (name, description, JSON-schema input).
   - Add a branch in `execute_tool` that imports from the service module and
     calls it.

Sharing the service module guarantees both paths execute the *exact same*
logic — there's no drift between "what claude does" and "what Gemma does."

## Observability

Every tool call becomes a `tool:<name>` span under the parent `chat:*` trace
in Langfuse (see `docs/OBSERVABILITY.md`). Args land as `input`, return value
as `output`, errors get `level=ERROR`. So if the agent picks the wrong tool
for a job, you'll see it in the trace timeline.
