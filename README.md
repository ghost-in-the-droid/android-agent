# Ghost in the Droid

<p align="center">
  <img src="docs/assets/mascot/12-the-tap.png" alt="Ghost tapping a phone" width="200" />
</p>

<p align="center">
  <strong>Summon a ghost into your Android.</strong><br/>
  It sees the screen. It taps the buttons. It never sleeps.
</p>

<p align="center">
  <a href="https://ghostinthedroid.com">Website</a> &middot;
  <a href="https://ghostinthedroid.com/getting-started/installation/">Docs</a> &middot;
  <a href="https://ghostinthedroid.com/skills/">Skill Hub</a>
</p>

![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-teal)

---

## What It Does

Open-source Python framework for controlling real Android phones via ADB. No app installed. No footprint. Pure automation.

Define **skills** for any app, run them from the dashboard or API, scale across a phone farm.

**The ghost taps what you'd tap**
- 50+ ADB methods — tap, swipe, type, clipboard, stealth variants
- Live phone screen streaming (MJPEG and WebRTC)
- Interactive touch-to-tap on the streamed screen
- Multi-device phone farm with per-device job queues

**Forge reusable skills for any app**
- YAML-based UI element definitions per app
- Python action classes with precondition checks
- Multi-step workflows that chain actions together
- Built-in skills for TikTok and Play Store
- **Skill Hub** — browse, search, and install skills from the community registry
- Install from CLI: `android-agent skill install tiktok`

**Teach the ghost new tricks**
- BFS-based auto app explorer — discovers every screen and transition
- LLM-assisted Skill Creator — chat with AI while viewing the live device stream
- The AI identifies UI elements and generates action/workflow code

**Scale the haunting**
- Multi-device phone farm with per-device job queues
- Bot runner: queue, schedule, and monitor automation jobs
- Per-device integration tests with ADB screen recording

---

## Requirements

- **Python 3.10+**
- **Android phone** with USB debugging enabled (Settings > Developer Options > USB Debugging)
- **ADB** installed and on PATH (`adb devices` should list your phone)
- **Node.js 18+** (for the frontend dev server)

---

## Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/ghost-in-the-droid/android-agent.git
cd ghost-in-the-droid

# 2. Install Python dependencies
pip install -e ".[all]"

# 3. Verify ADB sees your device
adb devices

# 4. Start the backend
python3 run.py
# API running at http://localhost:5055
# Interactive API docs at http://localhost:5055/docs

# 5. Start the frontend (separate terminal)
cd frontend
npm install
npx vite --host 0.0.0.0 --port 6175
# Dashboard at http://localhost:6175
```

### Environment Variables

Copy `.env.example` to `.env` (if provided) or create a `.env` file in the project root. The server reads configuration via Pydantic Settings. Optional variables include:

| Variable | Purpose |
|----------|---------|
| `OPENAI_API_KEY` | LLM features (Skill Creator, Agent Chat) |
| `ANTHROPIC_API_KEY` | Alternative LLM provider |
| `OPENROUTER_API_KEY` | OpenRouter LLM provider |
| `DEFAULT_DEVICE` | ADB serial (auto-detected if empty) |

---

## Architecture

```
android-agent/
  run.py                        # Entry point: Uvicorn on :5055
  gitd/
    app.py                      # FastAPI app factory + plugin hook
    config.py                   # Pydantic settings from .env
    models/                     # SQLAlchemy 2.0 ORM
    schemas/                    # Pydantic v2 request/response validation
    routers/                    # FastAPI route handlers
    services/                   # Business logic helpers
    skills/                     # Skill packages per app
      _base/                    #   Base classes (Skill, Action, Workflow)
      tiktok/                   #   TikTok skill (elements, actions, workflows)
      play_store/               #   Play Store skill (install, update, search)
    bots/
      common/
        adb.py                  #   Device class: tap, swipe, dump XML, wait_for
    mcp_server.py               # MCP server — expose tools for any LLM agent
    alembic/                    # Database migrations
  frontend/                     # Vue 3 + Vite + TypeScript + Tailwind CSS
    src/
      App.vue                   # Tab shell (9 tabs)
      views/                    # One view per tab
      composables/              # Typed API fetch wrapper
  portal/                       # Kotlin companion app (WebRTC, accessibility)
  site/                         # Docs site (Astro + Starlight)
  tests/                        # Integration tests (require a connected phone)
  docs/                         # Architecture docs
```

### How It Fits Together

1. **Backend** (`run.py`) starts a FastAPI server on port 5055 with routers covering device control, skills, bots, scheduling, and streaming.
2. **Frontend** (`frontend/`) is a Vue 3 SPA that talks to the backend via `/api/*`. Vite proxies API calls to the backend during development.
3. **Skills** define how to interact with a specific app. Each skill has a `elements.yaml` (UI elements), Python actions (atomic operations), and workflows (multi-step sequences).
4. **Bots** are long-running subprocess scripts that use the `Device` class from `bots/common/adb.py` to control the phone. The backend spawns and manages them.
5. **Database** is SQLite with SQLAlchemy 2.0 ORM and Alembic migrations.

---

## API Documentation

The backend auto-generates interactive API docs via FastAPI:

- **Swagger UI**: [http://localhost:5055/docs](http://localhost:5055/docs)
- **ReDoc**: [http://localhost:5055/redoc](http://localhost:5055/redoc)

API domains: phone, streaming, skills, creator, explorer, agent-chat, bot, scheduler, tests, tools, misc.

---

## Dashboard Tabs

| Tab | What It Does |
|-----|-------------|
| Phone Agent | Live device stream (MJPEG/WebRTC), tap/swipe on screen, multi-device view |
| Scheduler | Cron-style job scheduling with queue management |
| Skill Hub | Browse installed skills, run actions and workflows, export/delete |
| Skill Creator | LLM-assisted skill builder with live device stream |
| Skill Miner | Auto app explorer — BFS state discovery with screenshots |
| Tools | Utility tools hub |
| Manual Run | Start/stop bot jobs, queue management, logs |
| Tests | Per-device test runner with screen recording playback |
| Emulators | Create, boot, snapshot, and manage Android emulators |

---

## MCP Server — Give Any AI Agent an Android Body

The project ships an [MCP](https://modelcontextprotocol.io) server with 35 tools for Android control. Any MCP-compatible AI client (Claude Code, Claude Desktop, Cursor, VS Code Copilot, Windsurf) can use them.

### Install

One command — works with Claude Code, Codex, Cursor, VS Code Copilot, Windsurf:

```bash
claude mcp add android-agent -- uvx --from ghost-in-the-droid android-agent-mcp
```

That's it. `uvx` installs the package, creates an isolated env, and runs the MCP server. No clone, no venv, no manual setup.

**Other clients** — same command, different registration:

```bash
# Codex (OpenAI)
codex mcp add android-agent -- uvx --from ghost-in-the-droid android-agent-mcp
```

**Claude Desktop** (`~/Library/Application Support/Claude/claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "android-agent": {
      "command": "uvx",
      "args": ["--from", "ghost-in-the-droid", "android-agent-mcp"]
    }
  }
}
```

**VS Code Copilot** (`.vscode/mcp.json`):
```json
{
  "servers": {
    "android-agent": {
      "command": "uvx",
      "args": ["--from", "ghost-in-the-droid", "android-agent-mcp"]
    }
  }
}
```

**Cursor** (`.cursor/mcp.json`) / **Windsurf** (`~/.codeium/windsurf/mcp_config.json`):
```json
{
  "mcpServers": {
    "android-agent": {
      "command": "uvx",
      "args": ["--from", "ghost-in-the-droid", "android-agent-mcp"]
    }
  }
}
```

**For contributors** who clone the repo: the `.mcp.json` is already there — 35 tools available on first `claude` launch.

### Available tools

| Category | Tools |
|----------|-------|
| Screen | `screenshot`, `get_elements`, `get_screen_tree`, `get_screen_xml`, `screenshot_annotated`, `screenshot_cropped` |
| Interaction | `tap`, `tap_element`, `swipe`, `long_press`, `type_text`, `type_unicode`, `press_back`, `press_home`, `press_key` |
| Apps | `launch_app`, `search_apps`, `list_apps`, `launch_intent` |
| Context | `get_phone_state`, `classify_screen`, `find_on_screen`, `ocr_screen`, `ocr_region` |
| Device | `list_devices`, `clipboard_get`, `clipboard_set`, `get_notifications`, `open_notifications`, `toggle_overlay` |
| Skills | `list_skills`, `run_workflow`, `run_action`, `create_skill`, `explore_app` |

---

## Skill Hub CLI

```bash
# Search the public registry
android-agent skill search tiktok

# Install a skill
android-agent skill install tiktok

# Install from any GitHub repo
android-agent skill install github.com/someone/their-skill

# List installed skills
android-agent skill list

# Update a skill
android-agent skill update tiktok

# Remove a skill
android-agent skill remove tiktok

# Validate before publishing
android-agent skill validate ./my-skill/
```

The skill registry lives in [`registry/`](registry/) in this repo. Community skills are auto-discovered nightly from repos tagged `android-agent-skill`.

## Teach the Ghost a New App

Two ways to forge a skill:

**Community skill** (your own repo):
1. Create a new repo with `skill.yaml`, `elements.yaml`, actions, workflows
2. Tag your repo with the `android-agent-skill` topic
3. It appears on the hub automatically (nightly scraper)

**Official skill** (PR to this repo):
1. Build and test as a community skill first
2. Open a PR adding your skill to [`registry/`](registry/)
3. CI validates, maintainer reviews, gets "Official" badge

Each skill needs:
- `skill.yaml` — metadata (name, version, app package, actions, workflows)
- `elements.yaml` — UI element resource IDs and descriptions
- `actions/` — Python classes extending `Action` with `precondition()` and `execute()`
- `workflows/` — Python classes extending `Workflow` with `steps()`

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full guide.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI, Uvicorn, Python 3.10+ |
| ORM | SQLAlchemy 2.0 (Mapped types) |
| Migrations | Alembic |
| Validation | Pydantic v2 |
| Database | SQLite (WAL mode) |
| Frontend | Vue 3 (Composition API), TypeScript, Vite, Tailwind CSS 4 |
| Charts | Chart.js 4, Plotly.js |
| Device Control | ADB (Android Debug Bridge) |
| Streaming | MJPEG, WebRTC (via Ghost Portal companion app) |
| LLM | OpenAI, Anthropic (optional) |
| Linting | Ruff |
| Testing | pytest, Playwright (optional) |

---

## Running Tests

Tests are integration tests that require a connected Android phone:

```bash
# Run all tests on a specific device
DEVICE=<serial> python3 -m pytest tests/ -v --tb=short

# Run a single test file
DEVICE=<serial> python3 -m pytest tests/test_00_baseline.py -v
```

Get your device serial from `adb devices`.

---

## Database Migrations

The project uses Alembic for schema migrations:

```bash
# Generate a migration after editing a model
alembic revision --autogenerate -m "add new_field to my_table"

# Apply pending migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1
```

---

## Contributing

The ghost gets stronger with every skill. See [CONTRIBUTING.md](CONTRIBUTING.md) for:

- Adding skills for new apps (highest impact)
- Writing actions and workflows
- Backend architecture and code style
- PR process

---

## License

[MIT](LICENSE) — The ghost is free. The ghost is open source. The ghost is yours.
