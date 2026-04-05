---
title: "MCP Server"
description: Expose Android automation as tools for any LLM agent — Claude, Cursor, Codex, OpenClaw, ChatGPT.
---

The MCP server exposes the entire Android automation system as tools that any LLM agent can use. Supports MCP (Model Context Protocol) for Claude Code, Cursor, Codex CLI, and OpenClaw, plus an OpenAPI-compatible REST layer for ChatGPT/GPT Actions.

## Architecture

```
LLM Agent Platforms
  Claude Code · Cursor · Codex CLI · OpenClaw (MCP stdio or HTTP)
  ChatGPT / GPT Actions (OpenAPI REST)
        |                    |
        v                    v
  mcp_server.py         FastAPI server
  port 8002             port 5055
  33 tools              /api/* endpoints
        |                    |
        +--------+-----------+
                 v
       Physical Android phones via ADB
```

**File:** `gitd/mcp_server.py` — single file, ~540 lines, 33 tools.

## Tool Tiers

### Tier 1: Raw Android Control

Work with ANY app. The agent figures out what to do by looking at elements/screenshots.

| Tool | Description |
|------|-------------|
| `list_devices` | List connected phones with serial + model |
| `screenshot` | Base64 PNG of current screen |
| `get_elements` | JSON array of all UI elements (idx, text, bounds, clickable) |
| `get_phone_state` | Current app, activity, keyboard state, focused element |
| `tap` | Tap at (x, y) coordinates |
| `tap_element` | Tap element by idx from `get_elements()` |
| `swipe` | Swipe from (x1,y1) to (x2,y2) with duration |
| `type_text` | Type ASCII text into focused field |
| `type_unicode` | Type emoji/CJK via ADBKeyboard |
| `press_back` | Android Back button |
| `press_home` | Android Home button |
| `press_key` | Any key event (POWER, VOLUME_UP, ENTER, etc.) |
| `launch_app` | Launch app by package name |
| `long_press` | Long press at coordinates |

### Tier 1.5: Context & Screen Reading

| Tool | Description |
|------|-------------|
| `get_screen_tree` | Structured UI tree with hierarchy |
| `get_screen_xml` | Raw Android UI hierarchy XML |
| `screenshot_annotated` | Screenshot with element bounding boxes |
| `screenshot_cropped` | Crop a region of the screen |
| `ocr_screen` | OCR all text on screen |
| `ocr_region` | OCR a specific screen region |
| `classify_screen` | Identify which app/screen is showing |
| `toggle_overlay` | Toggle element overlay on device |
| `clipboard_get` / `clipboard_set` | Read/write clipboard |
| `get_notifications` | Read notification shade |
| `open_notifications` | Pull down notification shade |
| `launch_intent` | Launch Android intent with extras |
| `find_on_screen` | Find element by text or description |

### Tier 2: Skill Workflows

One tool call = one complete automation task. Uses installed skills.

| Tool | Description |
|------|-------------|
| `run_workflow` | Run a skill workflow (e.g. TikTok upload, Gmail send) |
| `run_action` | Run a single skill action (e.g. tiktok/open_app) |

### Tier 3: Meta / Discovery

Let the agent discover capabilities and create new ones.

| Tool | Description |
|------|-------------|
| `list_skills` | List all installed skills with actions/workflows |
| `explore_app` | BFS explore an app's UI, returns state graph |
| `create_skill` | Create new skill from JSON step list |

## Platform Setup

### Claude Code / Cursor (stdio)

Add to `.mcp.json` in the project root:
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

### Claude Desktop (HTTP)

Start server: `python3 -m gitd.mcp_server`

Add to Claude Desktop config:
```json
{
  "mcpServers": {
    "android-agent": {
      "url": "http://localhost:8002/mcp"
    }
  }
}
```

### OpenAI Codex CLI

Add to `~/.codex/config.toml`:
```toml
[mcp_servers.android-agent]
command = "python3"
args = ["-m", "gitd.mcp_server"]
```

### ChatGPT / GPT Actions

ChatGPT uses OpenAPI, not MCP. Expose port 5055 via ngrok or Cloudflare Tunnel, then import the OpenAPI spec as a Custom GPT Action. See `docs/features/mcp-server.md` for the full OpenAPI schema.

## Typical Agent Flow

1. `list_devices()` -- get device serial
2. `list_skills()` -- check if a skill exists for the task
3. If skill exists: `run_workflow(device, skill, workflow, params)`
4. If not: `get_elements(device)` -- understand screen -- `tap`/`type`/`swipe` raw
5. After building a new flow: `create_skill(name, package, steps)` to save it

## Testing

```bash
# Verify tools load
python3 -c "from gitd.mcp_server import mcp; print('OK')"

# HTTP mode
python3 -m gitd.mcp_server &
curl -s http://localhost:8002/mcp -X POST \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "method": "tools/list", "id": 1}'
```

## Dependencies

```bash
pip install "mcp[cli]"
```

## Related

- [Skill System](/features/skill-system/) -- skills that MCP tools can execute
- [Skill Hub](/features/skill-hub/) -- browse and manage installed skills
- [ADB Device](/features/adb-device/) -- the raw device methods MCP wraps
