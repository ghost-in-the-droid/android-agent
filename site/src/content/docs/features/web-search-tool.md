---
title: "Web Search Tool"
description: An agent tool that opens a search results page in the browser on the phone — one shortcut instead of "launch Chrome, tap the address bar, type, submit". No API key, no search provider.
---

⭐ **New in 1.3** — `web_search` is a tool the agent can call mid-conversation to pull up a search on the device. It's a one-shot shortcut for "the user asked me to look something up."

## What it actually does (read this first)

`web_search` **opens a search results page in a browser on the connected phone**. That's it.

It does **not**:
- call a search API (no [Serper](https://serper.dev/), no [Brave Search API](https://brave.com/search/api/), no server-side search)
- return search results or snippets to the model
- require an API key or any provider signup

It **does**: build a search-engine URL, then fire an Android [`VIEW` intent](https://developer.android.com/reference/android/content/Intent#ACTION_VIEW) at the best browser installed on the device so the results page appears on screen. The agent gets back a short status string ("Opened Chrome → google search for: …"), not the page contents.

Think of it as the fast path for *"search for X"* — replacing the four-step dance of launch Chrome → tap address bar → type → submit with a single tool call.

## How it works

```
Agent calls web_search(device, query, engine)
        │
        ▼
open_search()  — gitd/services/web_search.py:72
        │
        ├─ 1. Build URL:  _ENGINE_URLS[engine] + urlencode(query)
        │
        ├─ 2. List installed browsers:  adb shell pm list packages
        │
        ├─ 3. Walk the browser priority chain, for each installed one:
        │        am start -a android.intent.action.VIEW -d <url> -p <package>
        │        (first one that handles the intent wins)
        │
        ├─ 4. Fallback: bare VIEW intent → system default browser
        │
        └─ 5. Last resort: open Play Store to install a browser
```

Because `am start` returns exit code 0 even when no activity handles the intent, `_try_open()` (`web_search.py:57`) inspects stdout for `Error:`, `SecurityException`, and `no activities found` to detect real failures.

### Engines

The `engine` argument selects a URL prefix (`_ENGINE_URLS`, `web_search.py:39`). Unknown values fall back to Google.

| `engine` | Opens |
|---|---|
| `google` *(default)* | [`google.com/search?q=`](https://www.google.com/search) |
| `ddg` / `duckduckgo` | [`duckduckgo.com/?q=`](https://duckduckgo.com/) |
| `bing` | [`bing.com/search?q=`](https://www.bing.com/search) |
| `brave` | [`search.brave.com/search?q=`](https://search.brave.com/search) |

### Browser fallback chain

`open_search` tries browsers in priority order (`_BROWSER_CANDIDATES`, `web_search.py:27`) and uses the first one that's installed:

Chrome → Firefox → Samsung Internet → Edge → Brave → Opera → Opera GX → Vivaldi → DuckDuckGo Browser → system default → *(Play Store, if nothing else)*

So on a stock device you'll land in Chrome; on a stripped vendor build with no browser, Ghost opens the Play Store search for "browser" rather than failing silently.

## The tool the model sees

`web_search` is a static entry in the agent tool list (`gitd/services/agent_tools.py:249`), in [Anthropic tool-use format](https://docs.anthropic.com/en/docs/build-with-claude/tool-use) and auto-converted for other providers:

```json
{
  "name": "web_search",
  "description": "Open a web search in the best available browser. Use when the user asks to search/look up something…",
  "input_schema": {
    "type": "object",
    "properties": {
      "device": { "type": "string" },
      "query":  { "type": "string" },
      "engine": { "type": "string", "description": "google, ddg, bing, brave. Default google." }
    },
    "required": ["device", "query"]
  }
}
```

The same tool is exposed to the [MCP Server](../mcp-server/) (`gitd/mcp_server.py:403`), so a claude-code / Cursor client driving Ghost gets it too. Both paths call the one `open_search` implementation.

## When it fires

**Always available — no flag, no config, no gate.** `web_search` is a permanent member of the tool list every provider receives, so the model can call it any time. It's steered purely by the description: *"Use when the user asks to search/look up something."* Say *"look up the weather in Berlin"* in [Agent Chat](../dashboard/) and the model will typically fire `web_search` on the active device.

## What comes back

The return value is a status string, one of:

| Situation | Returned string |
|---|---|
| Success (named browser) | `Opened Chrome → google search for: <query>` |
| Success (system default) | `Opened default browser → google search for: <query>` |
| Empty query | `web_search error: empty query` |
| No browser handled it | `web_search failed: no browser handled the VIEW intent. Opened Play Store to install one. (Tried: …)` |

## When to use / when NOT to use

**Use it when:**
- You want the agent to surface a search *on the phone* for a human to look at
- You're building a flow where the phone screen is the output surface (kiosk, demo, assisted browsing)

**Don't reach for it when:**
- You want the agent to *read and reason over* search results — it can't; results never come back to the model. For research-style reasoning, use a cloud provider whose model has its own web tool (see [LLM Providers](../llm-providers/)).
- You need headless search with no visible browser — this tool is fundamentally "put a results page on the screen".

## Gotchas

- **Results are display-only.** The model receives a status string, not page content. This is the single most important thing to understand about the tool.
- **No cost, no rate limit** at Ghost's layer — there's no search API to bill or throttle.
- **Short ADB timeouts:** `pm list packages` is 10 s, each `am start` is 8 s (`web_search.py`).
- **`ddg` and `duckduckgo`** both work, though only `ddg` is advertised in the schema.

## Related

- [MCP Server](../mcp-server/) — exposes `web_search` (and every other tool) to external MCP clients
- [ADB Device Control](../adb-device/) — the intent/`am start` layer this tool builds on
- [LLM Providers](../llm-providers/) — for models that reason over web results, pick a provider with its own web tool
