---
title: "MCP Server"
description: 38 Android automation tools for any LLM agent — Claude Code, Cursor, Codex, ChatGPT.
---

The MCP server exposes the entire Android automation system as 38 tools any LLM agent can call. Supports MCP (Model Context Protocol) for Claude Code, Cursor, Codex CLI, and OpenClaw via stdio or HTTP, plus an OpenAPI-compatible REST layer for ChatGPT/GPT Actions.

## Architecture

```
LLM Agent Platforms
  Claude Code · Cursor · Codex CLI · OpenClaw (MCP stdio or HTTP)
  ChatGPT / GPT Actions (OpenAPI REST)
        |                    |
        v                    v
  mcp_server.py         FastAPI server
  port 8002             port 5055
  38 tools              /api/* endpoints
        |                    |
        +--------+-----------+
                 v
       Physical Android phones via ADB
```

**File:** `gitd/mcp_server.py` — single file, 38 tools.

## Ghost Skills vs MCP Tools

These are two separate things:

- **MCP Tools** — 38 primitive actions the agent calls directly (`tap`, `screenshot`, `launch_app`, etc.). This is what LLM agents interact with.
- **Ghost Skills** — high-level reusable automations recorded in `registry/` (TikTok upload, Instagram crawl, Gmail send). Think macros.

Four MCP tools bridge the two: `list_skills`, `run_workflow`, `run_action`, `create_skill`. They let an agent discover and run pre-built skills, or record new ones.

## All 38 Tools

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

### App Management (4 tools)

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

### System & Utility (5 tools)

| Tool | Description |
|------|-------------|
| `get_notifications` | All active notifications as JSON |
| `open_notifications` | Pull down notification shade |
| `web_search` | Open search in best available browser |
| `speak_text` | Phone speaks text aloud via TTS (works from PC and on-device) |
| `list_devices` | All connected ADB devices with model names |
| `toggle_overlay` | Toggle numbered element overlay for visual debugging |

### Skill Bridge (4 tools)

Connect MCP to the Ghost Skills system in `registry/`.

| Tool | Description |
|------|-------------|
| `list_skills` | Discover installed skills with their actions and workflows |
| `run_workflow` | Run a full skill workflow: `run_workflow(device, "tiktok", "upload_video", params)` |
| `run_action` | Run a single action: `run_action(device, "tiktok", "open_app", {})` |
| `create_skill` | Record a new reusable skill from a JSON step list |
| `explore_app` | BFS crawl an app's UI and return a state graph |

## Platform Setup

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
