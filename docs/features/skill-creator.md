# Skill Creator — Feature Summary

## What It Does

Visual tool for building new Android automation skills through LLM-assisted interaction. Split-screen interface: LLM chat on the left, live device screen with hardware controls on the right. Users describe what they want in natural language, the LLM proposes structured action plans, and the user executes them on the device with one click.

## Current State

**Working:**
- Split-screen layout in Vue frontend (Skill Creator tab)
- LLM chat with 4 backend options: OpenRouter, Claude API, Ollama, Claude Code CLI
- Model selector per backend (auto-populates from Ollama)
- Live device screenshot stream (polling `/api/phone/screenshot/{device}` at ~5fps)
- Hardware key buttons: Back, Home, Recents, Power, Vol+, Vol-
- Interactive tap: click on stream image to tap at coordinates on device
- Element overlay with numbered labels on interactive elements
- LLM context injection: current screen elements (up to 40), action history (last 15), active plan progress, error context
- Vision support: screenshot sent as base64 to Claude and OpenRouter backends
- Claude Code backend: full tool access (Read, Grep, Glob, Bash) with sandbox rules
- SSE streaming chat endpoint for real-time token output
- "Execute" button runs proposed actions on device sequentially
- Autopilot mode: auto-approve all steps without confirmation
- Record mode: capture manual actions as a recorded skill
- Create skill from recorded steps API (`POST /api/skills/create-from-recording`)
- Backend/model selection persisted in localStorage
- Device selector with refresh button and auto-retry on load failure

## Architecture

```
User types natural language instruction
        |
        v
Vue frontend collects context:
  - Current screen elements (GET /api/phone/elements/{device})
  - Screenshot as base64 (GET /api/phone/screenshot/{device})
  - Action history (local array, last 15 entries)
  - Active plan state + error context
  - Selected backend + model
        |
        v
POST /api/creator/chat (or /api/creator/chat-stream for SSE)
  {backend, model, message, context: {elements, action_history, screenshot_b64, device, plan, error_context}}
        |
        v
Server builds system prompt (_build_creator_system_prompt):
  - Capability list (tap, swipe, type, launch, screenshot, dump_xml, etc.)
  - Current screen UI hierarchy (for Claude Code: full XML tree)
  - Interactive elements with bounds + labels
  - Active plan progress (completed/failed steps)
  - Action history
  - JSON skill spec format with parameters
        |
        v
Routes to selected backend:
  +- OpenRouter -> OpenAI SDK (base_url=openrouter.ai) + vision
  +- Claude -> Anthropic SDK (messages API) + vision
  +- Ollama -> HTTP POST to localhost:11434/api/chat
  +- Claude Code -> CLI subprocess with tool access + sandbox
        |
        v
LLM returns skill spec + action plan as JSON
        |
        v
Vue frontend renders:
  - Natural language explanation
  - Structured skill spec (name, description, parameters, usage_example)
  - Step-by-step plan with "Execute" button
        |
        v
Execute -> POST /api/phone/tap, /api/phone/type, /api/phone/back, etc.
```

## Files

| File | Purpose |
|------|---------|
| `frontend/src/views/SkillCreatorView.vue` | Split-screen UI: chat, device stream, controls |
| `gitd/routers/creator.py` | `/api/creator/chat`, `/api/creator/chat-stream`, `/api/creator/ollama-models` |
| `gitd/routers/phone.py` | `/api/phone/screenshot/{device}`, `/api/phone/elements/{device}`, `/api/phone/tap`, etc. |
| `gitd/routers/skills.py` | `/api/skills/create-from-recording` |
| `frontend/src/composables/useMermaid.ts` | Mermaid diagram rendering in chat messages |

## API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/creator/chat` | Send message to LLM with screen context, get action plan |
| POST | `/api/creator/chat-stream` | SSE streaming version of chat |
| GET | `/api/creator/ollama-models` | List available Ollama models |
| GET | `/api/phone/screenshot/{device}` | Take screenshot (base64 JPEG, used for stream + vision) |
| GET | `/api/phone/elements/{device}` | Get interactive UI elements (overlay + LLM context) |
| POST | `/api/phone/tap` | Execute tap on device |
| POST | `/api/phone/type` | Type text on device |
| POST | `/api/phone/back` | Press back button |
| POST | `/api/phone/key` | Send hardware key event |
| POST | `/api/phone/input` | Send keycode event |
| POST | `/api/skills/create-from-recording` | Create skill directory from recorded steps |

## LLM Backends

| Backend | Config | Default Model | Vision | Timeout |
|---------|--------|---------------|--------|---------|
| OpenRouter | `OPENROUTER_API_KEY` env var | `anthropic/claude-sonnet-4` | Yes | 60s |
| Claude | `ANTHROPIC_API_KEY` env var | `claude-sonnet-4-20250514` | Yes | 60s |
| Ollama | Auto-detect at `localhost:11434` | First available model | No | 60s |
| Claude Code | `claude` CLI installed | `sonnet` | No (reads XML) | 120s |

### Claude Code Backend

The Claude Code backend is unique — it spawns a `claude` CLI subprocess with restricted tool access:
- **Allowed tools:** Read, Grep, Glob, Bash (cat, head, tail, ls, wc only)
- **Sandbox:** Writes restricted to `/tmp/creator_state/`
- **Context:** Server dumps screen XML to `/tmp/creator_state/screen.xml` before each call
- **Streaming:** Uses `--output-format stream-json --verbose` for SSE token output

## Device Controls

The device panel includes:
- **Device selector** with refresh button
- **Stream toggle** (screenshot polling at ~5fps)
- **Element overlay** (shows numbered labels on interactive elements)
- **Record mode** (capture manual actions for skill recording)
- **Hardware keys:** Back, Home, Recents, Power, Vol+, Vol-
- **Tap on stream:** Click the device image to send tap at coordinates
- **Autopilot checkbox:** Auto-approve all LLM-proposed steps

## LLM Skill Spec Format

The LLM is instructed to produce structured JSON skill specs:

```json
{
  "name": "send_gmail",
  "display_name": "Send Gmail Email",
  "description": "Compose and send an email via the Gmail app",
  "app_package": "com.google.android.gm",
  "parameters": [
    {"name": "recipient", "type": "string", "description": "Email address", "required": true}
  ],
  "steps": [
    {"action": "launch", "package": "com.google.android.gm", "description": "Launch Gmail"},
    {"action": "tap", "element_idx": 5, "description": "Tap Compose FAB"}
  ]
}
```

Parameters use `{param_name}` placeholders in step text fields, filled at runtime by `_run_skill.py`.
