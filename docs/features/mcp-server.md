# MCP Server & Multi-Platform Integration — Feature Summary

## What It Does

Exposes Ghost in the Droid's Android and iOS automation system as tools that
LLM agents can use. Supports MCP (Model Context Protocol) for Claude Code,
Cursor, Codex CLI, and OpenClaw, plus OpenAPI-compatible REST endpoints for
ChatGPT/GPT Actions.

## Current State

**Working:**
- 61 MCP tools across raw device control, observation, browser automation,
  skills, app lifecycle, streaming/recording, marketing data, and discovery
- stdio transport (Claude Code, Cursor, Codex CLI)
- HTTP transport on port 8002 (Claude Desktop, OpenClaw, web agents)
- REST API on port 5055 (ChatGPT/GPT Actions via FastAPI)
- Dynamic skill loading (auto-discovers all installed skills including recorded ones)
- Platform-aware device interaction: tap, swipe, type, screenshot, normalized
  elements, app launch/state, browser tools, health checks, and stream metadata
- Workflow execution via `_run_skill.py` subprocess (same pipeline as Skill Hub)
- Platform support registry: 55 cross-platform tools, 2 iOS-only workflow
  tools, and 4 intentionally Android-only escape hatches

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
│ mcp_server.py       │  │ run.py / FastAPI      │
│ port 8002           │  │ port 5055             │
│ 61 tools            │  │ /api/phone/* endpoints│
└────────┬────────────┘  └────────┬──────────────┘
         │ Python (Device + Skills)              │
         └────────────┬──────────────────────────┘
                      ▼
          Android via ADB · iOS via Appium/WDA
```

## File

`gitd/mcp_server.py` — thin MCP wrappers over shared service modules.

## Tool Tiers

### Tier 1: Device Control And Observation

Work with any supported app. The agent figures out what to do by looking at
normalized elements, screen trees, screenshots, OCR, and device health.

| Tool | Description |
|------|-------------|
| `list_devices` | List connected Android ADB refs and configured iOS Appium refs |
| `device_health` / `fix_device_health` | Android Portal/device checks or iOS Appium/WDA checks with recovery steps |
| `screenshot` / `screenshot_annotated` / `screenshot_cropped` | Base64 screenshots and annotated/cropped variants |
| `get_elements` / `get_screen_tree` / `get_screen_xml` | Normalized Android UIAutomator or iOS WDA accessibility trees |
| `get_phone_state` | Current app/activity on Android or active app/window on iOS |
| `find_on_screen` / `ocr_screen` / `ocr_region` | Text search and OCR fallback |
| `tap` | Tap at (x, y) coordinates |
| `tap_element` | Tap element by idx from `get_elements()` |
| `swipe` | Swipe from (x1,y1) to (x2,y2) with duration |
| `type_text` / `type_unicode` / `paste_text` | Enter text through ADB/Portal or WDA/clipboard helpers |
| `press_back` / `press_home` / `press_key` | Platform navigation controls |
| `launch_app` / `force_stop` / `app_state` | Launch, terminate, and inspect Android packages or iOS bundle IDs |
| `long_press` | Long press at coordinates |
| `open_notifications` / `get_notifications` / `clear_notifications` | Android notification shade or iOS Notification Center UI extraction |

### Tier 2: Browser, Stream, And Recording

Browser tools are the first iOS release-quality workflow surface. Android uses
intents and normalized screen extraction; iOS uses Appium/WebDriverAgent,
WebView contexts where available, then accessibility/OCR fallback.

| Tool | Description |
|------|-------------|
| `open_url` / `web_search` | Open URLs/search results in the platform browser |
| `browser_back` / `get_current_url` / `wait_for_text` | Browser navigation and readiness checks |
| `extract_visible_text` / `extract_articles` / `read_news` | Page text/headline/article extraction, including the iOS Chrome news workflow |
| `get_stream_info` | Android Portal/H264/screencap or iOS WDA MJPEG stream metadata |
| `start_screen_recording` / `stop_screen_recording` / `screen_recording_status` | Android screenrecord or iOS MJPEG captured through ffmpeg |

### Tier 3: Skills, Discovery, And Escape Hatches

Let the agent discover capabilities, run platform-aware skills, and create new
ones. Android-only escape hatches return stable platform errors for iOS.

| Tool | Description |
|------|-------------|
| `list_skills` | List installed skills with Android/iOS metadata |
| `run_skill` / `run_workflow` / `run_action` | Run platform-compatible skills and actions |
| `explore_app` | BFS explore an app UI, using Android or iOS state identity |
| `create_skill` | Create recorded skills with `elements.yaml` / `elements_ios.yaml` support |
| `list_apps` / `search_apps` / `list_packages` | Android package discovery or configured iOS bundle inventory |
| `launch_intent` / `shell` / `toggle_overlay` / `speak_text` | Android-only escape hatches with stable iOS errors |

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

Usage: tools appear automatically in Claude Code. Ask "list connected devices"
and it calls `list_devices()`, returning Android serials and configured
`ios:<udid>` refs.

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
description: Control Android phones via ADB and iOS devices via Appium/WDA
tools: [exec]
---

You can control connected Android phones and configured iOS devices. To interact:

1. List devices: `curl -s http://localhost:5055/api/phone/devices`
2. Screenshot: `curl -s http://localhost:5055/api/phone/screenshot/DEVICE_REF`
3. Get elements: `curl -s http://localhost:5055/api/phone/elements/DEVICE_REF`
4. Tap: `curl -X POST http://localhost:5055/api/phone/tap -H 'Content-Type: application/json' -d '{"device":"DEVICE_REF","x":540,"y":1200}'`
5. Type: `curl -X POST http://localhost:5055/api/phone/type -H 'Content-Type: application/json' -d '{"device":"DEVICE_REF","text":"hello"}'`
6. Run skill: `curl -X POST http://localhost:5055/api/skills/SKILL/run -H 'Content-Type: application/json' -d '{"workflow":"recorded","device":"DEVICE_REF","params":{}}'`

Always call list devices first to get the Android serial number or `ios:<udid>` ref.
```

**Option C: Native plugin (deepest integration)**

See `docs/integrations/openclaw-plugin/` for a TypeScript plugin that registers all tools natively with `api.registerTool()`.

### ChatGPT / GPT Actions (OpenAPI REST) — Via FastAPI server

ChatGPT uses OpenAPI specs, not MCP. The FastAPI server on port 5055 already has the REST endpoints. To create a GPT Action:

1. Expose port 5055 publicly (ngrok, Cloudflare Tunnel, or deploy):
   ```bash
   ngrok http 5055
   ```

2. Create a Custom GPT in ChatGPT → Actions → Import OpenAPI schema:

```yaml
openapi: "3.1.0"
info:
  title: Ghost in the Droid
  version: "1.0"
  description: Control Android phones via ADB and iOS devices via Appium/WDA
servers:
  - url: https://YOUR-NGROK-URL.ngrok-free.app
paths:
  /api/phone/devices:
    get:
      operationId: listDevices
      summary: List connected Android devices and configured iOS refs
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
      summary: Launch app by Android package name or iOS bundle id
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
   You control Android phones via ADB and iOS devices via Appium/WDA. Always call listDevices first to get the serial or ios:<udid> ref.
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
python3 -c "from gitd.mcp_server import mcp; print(f'{len(mcp._tool_manager.list_tools())} tools')"

# Test directly
python3 -c "from gitd.mcp_server import list_devices; print(list_devices())"

# HTTP mode
python3 -m gitd.mcp_server &
curl -s http://localhost:8002/mcp -X POST \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "method": "tools/list", "id": 1}'
```

## Typical Agent Flow

1. `list_devices()` → get an Android serial or `ios:<udid>` ref
2. `list_skills()` → check if a skill exists for the task
3. If skill exists: `run_workflow(device, skill, workflow, params)`
4. If not: `get_elements(device)` → understand screen → `tap`/`type`/`swipe` raw
5. After building a new flow: `create_skill(name, package, steps)` to save it
