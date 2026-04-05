# MCP Server & Multi-Platform Integration — Feature Summary

## What It Does

Exposes the entire Android automation system as tools that any LLM agent can use. Supports MCP (Model Context Protocol) for Claude Code, Cursor, Codex CLI, and OpenClaw, plus an OpenAPI-compatible REST layer for ChatGPT/GPT Actions.

## Current State

**Working:**
- 19 MCP tools across 3 tiers (raw control, skill workflows, meta/discovery)
- stdio transport (Claude Code, Cursor, Codex CLI)
- HTTP transport on port 8002 (Claude Desktop, OpenClaw, web agents)
- REST API on port 5055 (ChatGPT/GPT Actions via existing Flask server)
- Dynamic skill loading (auto-discovers all installed skills including recorded ones)
- Full device interaction: tap, swipe, type, screenshot, elements, key events
- Workflow execution via `_run_skill.py` subprocess (same pipeline as Skill Hub)

## Architecture

```
┌────────────────────────────────────────────────────────┐
│          LLM Agent Platforms                           │
│  Claude Code · Cursor · Codex CLI · OpenClaw           │
│         (MCP stdio or HTTP)                            │
│  ChatGPT / GPT Actions                                │
│         (OpenAPI REST)                                 │
└────────────────┬──────────────────┬────────────────────┘
                 │ MCP              │ REST/OpenAPI
                 ▼                  ▼
┌─────────────────────┐  ┌──────────────────────┐
│ mcp_server.py       │  │ server.py (Flask)     │
│ port 8002           │  │ port 5055             │
│ 19 tools            │  │ /api/phone/* endpoints│
└────────┬────────────┘  └────────┬──────────────┘
         │ Python (Device + Skills)              │
         └────────────┬──────────────────────────┘
                      ▼
          Physical Android phones via ADB
```

## File

`gitd/mcp_server.py` — single file, ~280 lines.

## Tool Tiers

### Tier 1: Raw Android Control (14 tools)

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

### Tier 2: Skill Workflows (2 tools)

One tool call = one complete automation task. Uses installed skills.

| Tool | Description |
|------|-------------|
| `run_workflow` | Run a skill workflow (e.g. TikTok upload_video, Gmail recorded) |
| `run_action` | Run a single skill action (e.g. tiktok/open_app) |

### Tier 3: Meta / Discovery (3 tools)

Let the agent discover capabilities and create new ones.

| Tool | Description |
|------|-------------|
| `list_skills` | List all installed skills with actions/workflows |
| `explore_app` | BFS explore an app's UI, returns state graph |
| `create_skill` | Create new skill from JSON step list |

---

## Platform Integration Guides

### Claude Code (stdio) — Ready

Already configured in `.mcp.json`:
```json
{
  "mcpServers": {
    "android-agent": {
      "command": "python3",
      "args": ["-m", "gitd.mcp_server"],
      "cwd": "/path/to/android-agent"
    }
  }
}
```

Usage: tools appear automatically in Claude Code. Ask "list connected Android devices" and it calls `list_devices()`.

### Cursor (stdio) — Ready

Same `.mcp.json` format — Cursor reads it from the project root. No additional config needed.

### Claude Desktop (HTTP) — Ready

Add to `~/.config/Claude/claude_desktop_config.json` (Linux) or `~/Library/Application Support/Claude/claude_desktop_config.json` (Mac):
```json
{
  "mcpServers": {
    "android-agent": {
      "url": "http://localhost:8002/mcp"
    }
  }
}
```

Start server first: `python3 -m gitd.mcp_server`

### OpenAI Codex CLI (MCP) — Ready

Add to `~/.codex/config.toml`:
```toml
[mcp_servers.android-agent]
command = "python3"
args = ["-m", "gitd.mcp_server"]
cwd = "/path/to/android-agent"

# Per-tool approval settings (optional)
[mcp_servers.android-agent.tools.tap]
approval_mode = "auto"

[mcp_servers.android-agent.tools.screenshot]
approval_mode = "auto"

[mcp_servers.android-agent.tools.run_workflow]
approval_mode = "approve"
```

Or use HTTP transport:
```toml
[mcp_servers.android-agent]
url = "http://localhost:8002/mcp"
```

### OpenClaw — Ready (3 options)

OpenClaw (https://github.com/openclaw/openclaw) supports MCP, native plugins, and Skills.

**Option A: MCP bridge (easiest)**

Register the MCP server with OpenClaw:
```bash
openclaw mcp set android-agent \
  --command "python3" \
  --args "-m,gitd.mcp_server" \
  --cwd "/path/to/android-agent"
```

Then in any OpenClaw conversation: "use the android-agent tools to screenshot my phone"

**Option B: OpenClaw Skill (no code)**

Create `~/.openclaw/workspace/skills/android-agent/SKILL.md`:
```markdown
---
name: android-agent
description: Control Android phones via ADB
tools: [exec]
---

You can control connected Android phones. To interact:

1. List devices: `curl -s http://localhost:5055/api/phone/devices`
2. Screenshot: `curl -s http://localhost:5055/api/phone/screenshot/SERIAL`
3. Get elements: `curl -s http://localhost:5055/api/phone/elements/SERIAL`
4. Tap: `curl -X POST http://localhost:5055/api/phone/tap -H 'Content-Type: application/json' -d '{"device":"SERIAL","x":540,"y":1200}'`
5. Type: `curl -X POST http://localhost:5055/api/phone/type -H 'Content-Type: application/json' -d '{"device":"SERIAL","text":"hello"}'`
6. Run skill: `curl -X POST http://localhost:5055/api/skills/SKILL/run -H 'Content-Type: application/json' -d '{"workflow":"recorded","device":"SERIAL","params":{}}'`

Always call list devices first to get the serial number.
```

**Option C: Native plugin (deepest integration)**

See `docs/integrations/openclaw-plugin/` for a TypeScript plugin that registers all tools natively with `api.registerTool()`.

### ChatGPT / GPT Actions (OpenAPI REST) — Via Flask server

ChatGPT uses OpenAPI specs, not MCP. Our Flask server on port 5055 already has all the REST endpoints. To create a GPT Action:

1. Expose port 5055 publicly (ngrok, Cloudflare Tunnel, or deploy):
   ```bash
   ngrok http 5055
   ```

2. Create a Custom GPT in ChatGPT → Actions → Import OpenAPI schema:

```yaml
openapi: "3.1.0"
info:
  title: Android Agent
  version: "1.0"
  description: Control Android phones via ADB
servers:
  - url: https://YOUR-NGROK-URL.ngrok-free.app
paths:
  /api/phone/devices:
    get:
      operationId: listDevices
      summary: List connected Android devices
      responses:
        "200":
          description: Device list
          content:
            application/json:
              schema:
                type: object
                properties:
                  devices:
                    type: array
                    items:
                      type: object
                      properties:
                        serial: { type: string }
                        model: { type: string }
                        nickname: { type: string }
  /api/phone/elements/{device}:
    get:
      operationId: getElements
      summary: Get interactive UI elements on device screen
      parameters:
        - name: device
          in: path
          required: true
          schema: { type: string }
      responses:
        "200":
          description: Element list
  /api/phone/screenshot/{device}:
    get:
      operationId: screenshot
      summary: Take a screenshot (returns base64 PNG)
      parameters:
        - name: device
          in: path
          required: true
          schema: { type: string }
      responses:
        "200":
          description: Screenshot
  /api/phone/tap:
    post:
      operationId: tap
      summary: Tap at coordinates on device
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [device, x, y]
              properties:
                device: { type: string }
                x: { type: integer }
                y: { type: integer }
      responses:
        "200":
          description: Tap result
  /api/phone/type:
    post:
      operationId: typeText
      summary: Type text on device
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [device, text]
              properties:
                device: { type: string }
                text: { type: string }
      responses:
        "200":
          description: Type result
  /api/phone/swipe:
    post:
      operationId: swipe
      summary: Swipe gesture on device
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [device, x1, y1, x2, y2]
              properties:
                device: { type: string }
                x1: { type: integer }
                y1: { type: integer }
                x2: { type: integer }
                y2: { type: integer }
      responses:
        "200":
          description: Swipe result
  /api/phone/back:
    post:
      operationId: pressBack
      summary: Press Back button
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                device: { type: string }
      responses:
        "200":
          description: OK
  /api/phone/launch:
    post:
      operationId: launchApp
      summary: Launch app by package name
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [device, package]
              properties:
                device: { type: string }
                package: { type: string }
      responses:
        "200":
          description: Launch result
  /api/phone/key:
    post:
      operationId: pressKey
      summary: Send key event (POWER, VOLUME_UP, HOME, etc.)
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [device, key]
              properties:
                device: { type: string }
                key: { type: string, description: "Key name without KEYCODE_ prefix" }
      responses:
        "200":
          description: Key result
  /api/skills:
    get:
      operationId: listSkills
      summary: List all installed automation skills
      responses:
        "200":
          description: Skills list
  /api/skills/{name}/run:
    post:
      operationId: runWorkflow
      summary: Run a skill workflow on a device
      parameters:
        - name: name
          in: path
          required: true
          schema: { type: string }
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [workflow, device]
              properties:
                workflow: { type: string }
                device: { type: string }
                params: { type: object }
      responses:
        "200":
          description: Workflow result
```

3. Set authentication to "None" (for local/tunnel use) or add API key auth header.

4. In the GPT's instructions, add:
   ```
   You control Android phones. Always call listDevices first to get the serial.
   Use listSkills to check for existing automations before using raw tap/swipe.
   ```

### Windsurf / Continue.dev (MCP stdio) — Ready

Same `.mcp.json` format. No changes needed.

---

## Dependencies

```bash
pip install "mcp[cli]"
```

## Testing

```bash
# Verify tools load
python3 -c "from gitd.mcp_server import mcp; print(f'{len(mcp._tool_manager._tools)} tools')"

# Test directly
python3 -c "from gitd.mcp_server import list_devices; print(list_devices())"

# HTTP mode
python3 -m gitd.mcp_server &
curl -s http://localhost:8002/mcp -X POST \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "method": "tools/list", "id": 1}'
```

## Typical Agent Flow

1. `list_devices()` → get device serial
2. `list_skills()` → check if a skill exists for the task
3. If skill exists: `run_workflow(device, skill, workflow, params)`
4. If not: `get_elements(device)` → understand screen → `tap`/`type`/`swipe` raw
5. After building a new flow: `create_skill(name, package, steps)` to save it
