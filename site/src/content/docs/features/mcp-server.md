---
title: "MCP Server"
description: 64 Android/iOS automation tools for any LLM agent — Claude Code, Cursor, Codex, ChatGPT.
---

The MCP server exposes the entire Android automation system as 66 tools any LLM agent can call. Supports MCP (Model Context Protocol) for Claude Code, Cursor, Codex CLI, and OpenClaw via stdio or HTTP, plus an OpenAPI-compatible REST layer for ChatGPT/GPT Actions.

## Architecture

```
LLM Agent Platforms
  Claude Code · Cursor · Codex CLI · OpenClaw (MCP stdio or HTTP)
  ChatGPT / GPT Actions (OpenAPI REST)
        |                    |
        v                    v
  mcp_server.py         FastAPI server
  port 8002             port 5055
  66 tools              /api/* endpoints
        |                    |
        +--------+-----------+
                 v
       Physical Android phones via ADB
```

**File:** `gitd/mcp_server.py` — single file, 66 tools.

## Ghost Skills vs MCP Tools

These are two separate things:

- **MCP Tools** — 66 tools the agent calls directly (`tap`, `screenshot`, `launch_app`, etc.). This is what LLM agents interact with.
- **Ghost Skills** — high-level reusable automations recorded in `registry/` (TikTok upload, Instagram crawl, Gmail send). Think macros.

Five MCP tools bridge the two: `list_skills`, `run_workflow`, `run_action`, `create_skill`, `explore_app`. They let an agent discover and run pre-built skills, or record new ones.

## All 64 Tools

### Screen Reading (11 tools)

| Tool | Description |
|------|-------------|
| `get_screen_tree` | LLM-friendly indented UI hierarchy — primary tool for understanding the screen |
| `get_elements` | JSON array of UI elements with idx, text, bounds, clickable |
| `screenshot` | Full screen as base64 PNG |
| `screenshot_annotated` | Screenshot with numbered element labels overlaid |
| `screenshot_cropped` | Zoom into a specific pixel region |
| `get_screen_xml` | Raw uiautomator XML — when you need exact attributes |
| `get_phone_state` | Current app, activity, keyboard state, focused element |
| `classify_screen` | Heuristic: home / search / profile / dialog / error / loading |
| `find_on_screen` | Search for text — XML first, OCR fallback |
| `ocr_screen` | Full screen OCR via RapidOCR — for WebViews, games, canvas |
| `ocr_region` | OCR a specific pixel region |

### Input & Control (10 tools)

| Tool | Description |
|------|-------------|
| `tap` | Tap at pixel coords (x, y) |
| `tap_element` | Tap element by idx from `get_elements()` |
| `swipe` | Swipe/scroll between two points with duration |
| `long_press` | Long press — context menus, drag initiation |
| `type_text` | Type ASCII into focused field |
| `type_unicode` | Type emoji / CJK / accented chars via ADBKeyboard broadcast |
| `paste_text` | Set clipboard and paste into focused field in one call |
| `press_back` | Android Back button |
| `press_home` | Android Home button |
| `press_key` | Any key event: ENTER, POWER, VOLUME_UP, KEYCODE_* |

### App Management (5 tools)

| Tool | Description |
|------|-------------|
| `launch_app` | Open app by package name (handles disabled packages, ROM quirks) |
| `open_camera` | Open camera in photo / video / selfie / selfie_video + optional timer (2s/3s/5s/10s) |
| `launch_intent` | Full Android intent — URLs, deep links, share sheets, extras |
| `search_apps` | Find installed app by name → returns package name |
| `list_apps` | All installed apps with human-readable names |

### Clipboard (3 tools)

| Tool | Description |
|------|-------------|
| `clipboard_get` | Read current clipboard |
| `clipboard_set` | Write to clipboard via Ghost portal |
| `paste_text` | Write clipboard + paste in one shot (preferred) |

### System & Utility (6 tools)

| Tool | Description |
|------|-------------|
| `get_notifications` | All active notifications as JSON |
| `open_notifications` | Pull down notification shade |
| `web_search` | Open search in best available browser |
| `speak_text` | Phone speaks text aloud via TTS (works from PC and on-device) |
| `list_devices` | All connected ADB devices with model names |
| `toggle_overlay` | Toggle numbered element overlay for visual debugging |

### Skill Bridge (5 tools)

Connect MCP to the Ghost Skills system in `registry/`.

| Tool | Description |
|------|-------------|
| `list_skills` | Discover installed skills with their actions and workflows |
| `run_workflow` | Run a full skill workflow: `run_workflow(device, "tiktok", "upload_video", params)` |
| `run_action` | Run a single action: `run_action(device, "tiktok", "open_app", {})` |
| `create_skill` | Record a new reusable skill from a JSON step list |
| `explore_app` | BFS crawl an app's UI and return a state graph |

### Skill Execution (4 tools)

| Tool | Description |
|------|-------------|
| `find_skill` | Find the installed skill action that matches a natural-language intent |
| `run_skill` | Run a v2 skill action; `needs_input` returns a token for `run_skill_resume` |
| `run_skill_resume` | Continue a paused skill using a schema-typed JSON answer |
| `get_skill_notes` | Return a skill's SOFT.md reference notes for hand-driving when the hard replay is unavailable |
| `draft_skill` | Distil the device's latest chat conversation into draft replayable steps (nothing written) |
| `save_skill` | Save the device's chat conversation as a hard (replay) or soft (guidance) skill |

### App State & Device Health (7 tools)

| Tool | Description |
|------|-------------|
| `force_stop` | Force-stop an Android package or terminate an iOS bundle id |
| `app_state` | Whether a package or bundle id is installed, running, or foreground |
| `list_packages` | Raw package names or bundle ids (prefer `list_apps` for display names) |
| `device_health` | Comprehensive device health check |
| `fix_device_health` | Apply the recovery action returned by `device_health.recommended_fix` |
| `list_crashes` | Recent app crashes and ANRs from the logcat crash buffer (no root) |
| `get_crash` | Full stack trace of the most recent crash |

### Screen Recording & Streaming (4 tools)

| Tool | Description |
|------|-------------|
| `start_screen_recording` | Start recording the device screen |
| `stop_screen_recording` | Stop a running recording and save the MP4 |
| `screen_recording_status` | Active recording status for a device |
| `get_stream_info` | Effective stream metadata without opening the stream |

### Browser, Text & News (8 tools)

| Tool | Description |
|------|-------------|
| `open_url` | Open a URL in the platform browser |
| `browser_back` | Navigate back in the current browser or app context |
| `get_current_url` | Current browser URL when the platform exposes it |
| `wait_for_text` | Wait until text appears on screen and return visible text context |
| `extract_visible_text` | Visible text with browser chrome filtered by default |
| `extract_articles` | Likely article and headline candidates on the current browser page |
| `read_news` | Open a news page and return structured headlines plus snippets |
| `clear_notifications` | Dismiss visible notifications when the platform exposes a clear control |

### Orchestration (2 tools)

| Tool | Description |
|------|-------------|
| `run_flow` | Run an ordered batch of tool calls server-side in one round-trip |
| `wait` | Pause execution for a fixed number of seconds |

## Connecting a client

Ghost speaks MCP over two transports:

- **stdio** — run `android-agent-mcp` (or `python3 -m gitd.mcp_server`)
- **streamable HTTP** — `http://localhost:8002/mcp` (start the server with `python3 -m gitd.mcp_server`)

The fastest start is Claude Code:

### Limit device discovery for one agent

Start a dedicated MCP process with the selected connected device ref:

```bash
GHOST_DEVICE=emulator-5554 android-agent-mcp
```

Or put `"env": {"GHOST_DEVICE": "emulator-5554"}` in that server's MCP configuration.
`ANDROID_SERIAL` is also accepted; `GHOST_DEVICE` takes precedence when both are set.
Use `ios:<udid>` to select an iOS device. `list_devices` returns only the selected
connected ref, and other devices receive no model/status probes. If the selected
device is absent, the list is empty. Leaving both variables unset preserves full
discovery. The selection is also a strict scope: MCP tools, agent tools and `run_action`
refuse any other device ref, even one passed exactly, with an error naming the selected id.
With neither variable set, explicitly supplied device refs are accepted as before.

`list_devices` prints a header line, then one device per line: the id first, then
`key=value` details (`emulator-5554  model=Pixel 8`). Pass only the id as `device`.
A pasted display line, quotes or backticks are normalized back to the id only when that
id is the selected device (or, with no selection, a connected one); otherwise the call
is refused and the error names the valid id(s).

### Deny app packages for an agent session

Set a comma-separated list in the dedicated MCP process environment, alongside
`GHOST_DEVICE` (the same variables can go in the MCP configuration's `env`):

```bash
GHOST_DEVICE=emulator-5554 GHOST_DENY_PACKAGES=com.android.vending,com.example.private android-agent-mcp
```

Package names match exactly after trimming whitespace; unset or empty means no
restrictions. Explicit app/component launches and skills whose fingerprint names
any denied package are refused before execution. Android intents are resolved
before launch and refused if their target is denied or cannot be resolved.
Foreground ownership is checked before and after device tools, chain sub-actions,
skill steps, and Android input/launch commands. If a denied app is foreground,
Ghost sends HOME once and returns a clear error; the remaining chain or skill
stops even if an inner helper catches that error. An unreadable foreground fails
closed while this policy is enabled. The same checks accept iOS bundle IDs for
MCP tools and skills. This is an accident guard for one agent process, not an
OS sandbox: raw `adb shell` strings are only checked at the tool boundary.

### Serve a smaller tool surface (profiles)

`GHOST_MCP_PROFILE` drops every tool outside a named keep-set before the server
starts; `GHOST_MCP_HIDE_TOOLS` is a comma-separated list of extra tools to hide.

| Profile | Keeps |
|---|---|
| `skills-first` | `find_skill`, `list_skills`, `run_skill`, `run_skill_resume`, `get_skill_notes`, `create_skill`, `explore_app` plus the hand-drive basics (`list_devices`, `screenshot`, `get_elements`, `tap`, `type_text`, `swipe`, `press_back`, `press_home`, `launch_app`, `wait`) |
| `soft-only` | `skills-first` minus `run_skill` and `run_skill_resume`: the agent follows SOFT.md notes by hand |
| `hand-only` | the hand-drive basics only, no skill tools |

```bash
GHOST_MCP_PROFILE=skills-first android-agent-mcp
```

An empty or unknown profile serves the full surface.

### Claude Code (recommended)

Add `.mcp.json` to your project root:

```json
{
  "mcpServers": {
    "android-agent": {
      "command": "android-agent-mcp"
    }
  }
}
```

Or register globally:

```bash
claude mcp add android-agent android-agent-mcp
```

### Claude Desktop (HTTP)

```json
{
  "mcpServers": {
    "android-agent": {
      "url": "http://localhost:8002/mcp"
    }
  }
}
```

Start the server first: `python3 -m gitd.mcp_server`

### Cursor / Codex CLI (stdio)

```json
{
  "mcpServers": {
    "android-agent": {
      "command": "python3",
      "args": ["-m", "gitd.mcp_server"]
    }
  }
}
```

### ChatGPT / GPT Actions

ChatGPT uses OpenAPI, not MCP. Expose port 5055 via ngrok or Cloudflare Tunnel, then import the OpenAPI spec as a Custom GPT Action.

### Other clients

Every other client — Cursor, Windsurf, Zed, Continue, Cline, Codex CLI, Claude Desktop, Cherry Studio, OpenClaw, and ChatGPT / GPT Actions (via the OpenAPI REST layer) — has its own config format. The **[MCP Clients compatibility matrix](/features/mcp-clients/)** lists the transport each one supports and the exact snippet to wire Ghost in.

Prefer to drive Ghost from **LangChain or LlamaIndex** directly? Skip MCP entirely and use the native framework adapters — see [LangChain & LlamaIndex](/features/integrations/).

## Typical Agent Loop

```
1. list_devices()                              → pick device serial
2. list_skills()                               → check if skill exists for task
3a. If skill: run_workflow(dev, skill, wf, {}) → done in one call
3b. If not:   get_screen_tree(dev)             → understand screen
              tap / type / swipe / ...         → act
              get_screen_tree(dev)             → verify
              create_skill(name, pkg, steps)   → save for next time
```

## Testing

```bash
# Verify tools load
python3 -c "from gitd.mcp_server import mcp; print('OK')"

# List all tools via stdio
printf '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1"}}}\n{"jsonrpc":"2.0","id":2,"method":"tools/list"}\n' \
  | android-agent-mcp | python3 -c "import sys,json; [print(t['name']) for line in sys.stdin.read().split('\n') for d in [json.loads(line)] if d.get('id')==2 for t in d['result']['tools']]"

# HTTP mode
python3 -m gitd.mcp_server &
curl -s http://localhost:8002/mcp -X POST \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'
```

## Related

- [Skill System](/features/skill-system/) — skills that MCP tools can execute
- [Skill Hub](/features/skill-hub/) — browse and manage installed skills
- [ADB Device](/features/adb-device/) — raw device methods the MCP wraps
