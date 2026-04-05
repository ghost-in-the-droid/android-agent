---
title: "🛠️ Skill Creator"
description: Split-screen LLM-powered tool for building skills — chat interface, live device stream, element overlay, and 4 LLM backends.
---

The Skill Creator is a visual tool for building new Android automation skills through LLM-assisted interaction. It provides a split-screen interface in the dashboard.

## Interface Layout

| Panel | Content |
|-------|---------|
| **Left** | LLM chat -- type natural language instructions, view proposed action plans |
| **Right** | Live device screen (WebRTC) with numbered interactive element overlay |

## How It Works

```
User types: "Open Gmail and compose an email to test@example.com"
    |
    v
Dashboard collects context:
  - Current screen elements (via GET /api/phone/elements/<device>)
  - Action history (last 15 entries)
  - Selected backend + model
    |
    v
POST /api/creator/chat -> server builds system prompt with:
  - Capability list (tap, swipe, type, launch, screenshot, etc.)
  - Existing skill references (tiktok: 13 actions, base: 9 actions)
  - Current screen elements with bounds + labels
  - Action history
    |
    v
LLM returns structured skill spec + action plan as JSON
    |
    v
Dashboard renders:
  - Natural language explanation
  - Structured skill spec with parameters
  - Step-by-step plan with "Execute" button
    |
    v
Execute -> sends tap/type/back commands to device -> results feed back to LLM
```

## LLM Backends

| Backend | Config | Default Model | Timeout |
|---------|--------|---------------|---------|
| OpenRouter | `OPENROUTER_API_KEY` env var | `anthropic/claude-sonnet-4` | 60s |
| Claude API | `ANTHROPIC_API_KEY` env var | `claude-sonnet-4-20250514` | 60s |
| Ollama | Auto-detect at `localhost:11434` | `llama3` | 60s |
| Claude Code | `claude` CLI installed | `sonnet` | 120s |

The backend and model selection persist in localStorage across sessions.

## LLM Skill Spec Format

The LLM produces structured JSON action plans:

```json
{
  "name": "send_gmail",
  "display_name": "Send Gmail Email",
  "description": "Compose and send an email via the Gmail app",
  "app_package": "com.google.android.gm",
  "parameters": [
    {
      "name": "recipient",
      "type": "string",
      "description": "Email address",
      "example": "hello@example.com",
      "required": true
    }
  ],
  "usage_example": "Send an email to john@example.com with subject 'Meeting'",
  "steps": [
    {"action": "launch", "package": "com.google.android.gm", "goal": "Open Gmail"},
    {"action": "tap", "element_idx": 5, "goal": "Open composer"},
    {"action": "type", "text": "{recipient}", "goal": "Enter recipient"}
  ]
}
```

Parameters use `{param_name}` placeholders in step text fields, filled at runtime.

## Usage

1. Open the dashboard at http://localhost:5055
2. Navigate to the **Skill Creator** tab
3. Select your LLM backend and model from the dropdowns
4. Start the WebRTC stream for your target device (Phone Agent tab or inline)
5. Type a natural language instruction in the chat input
6. Review the LLM's proposed skill spec and action steps
7. Click **Execute** to run steps on the device, or approve individually
8. Iterate: results feed back to the LLM as context for refinement

## Element Overlay

The right panel shows the live device screen with numbered labels on every interactive element. This helps you:

- Reference elements by index when chatting with the LLM ("tap element #5")
- Identify resource IDs and content descriptions for writing `elements.yaml`
- Verify that the correct element was found

Elements are fetched via `GET /api/phone/elements/<device>`.

## API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/creator/chat` | Send message to LLM with screen context |
| GET | `/api/creator/ollama-models` | List available Ollama models |
| GET | `/api/phone/elements/<device>` | Get interactive UI elements |
| POST | `/api/phone/tap` | Execute tap on device |
| POST | `/api/phone/type` | Type text on device |
| POST | `/api/phone/back` | Press back button |

## Related

- [App Explorer](/features/app-explorer/) -- discover UI states automatically
- [Creating Skills](/skills/creating-skills/) -- write the skill code manually
- [Elements](/skills/elements/) -- understand locator chains found via the overlay
