# MCP Server & Multi-Platform Integration — Feature Summary

## What It Does

Exposes Ghost in the Droid's Android and iOS automation system as tools that
LLM agents can use. Supports MCP (Model Context Protocol) for Claude Code,
Cursor, Codex CLI, and OpenClaw, plus OpenAPI-compatible REST endpoints for
ChatGPT/GPT Actions.

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
MCP tools and skills.

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


This is a process-local accident guard, not an Android permission boundary or a
sandbox for arbitrary shell/Python code. Checks observe foreground snapshots;
brief or delayed app switches between checks can escape observation. Deny app
stores and other sensitive apps explicitly for filmed sessions. For isolation
from an owner's accounts, use a dedicated device/profile without those accounts.
The variable must also be present in any separately started agent/skill process.

## Current State

**Working:**
- 66 MCP tools across raw device control, observation, browser automation,
  skills, app lifecycle, streaming/recording, and discovery
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
│ 66 tools            │  │ /api/phone/* endpoints│
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

### Google Antigravity CLI (`agy`, stdio) — Ready

One step: `ghost mcp install --client agy`

Or add manually to the global `~/.gemini/config/mcp_config.json`:
```json
{
  "mcpServers": {
    "android-agent": {
      "command": "android-agent-mcp"
    }
  }
}
```

Tools are discovered on the next `agy` session; inspect them with `/mcp` inside
the CLI. Existing entries in the file are preserved (merge, not clobber).

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
