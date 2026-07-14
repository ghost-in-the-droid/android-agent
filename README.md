# Ghost in the Droid

<p align="center">
  <img src="docs/assets/mascot/12-the-tap.png" alt="Ghost tapping a phone" width="200" />
</p>

<p align="center">
  <strong>Summon a ghost into your phone.</strong><br/>
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

Open-source Python framework for controlling Android and iOS devices from one agent harness. Android runs through ADB. iOS runs through Appium XCUITest and WebDriverAgent, with real iPhones as the target path and simulators for development and CI.

Define **skills** for any app, run them from the dashboard or API, scale across a phone farm.

**The ghost taps what you'd tap**
- Android control through ADB — tap, swipe, type, clipboard, shell, intents, and stealth variants
- iOS control through WebDriverAgent — screenshot, accessibility tree, tap, swipe, type, app launch, clipboard, browser actions
- Live phone screen streaming: Android MJPEG/WebRTC, iOS WDA MJPEG with screenshot fallback
- Interactive touch-to-tap on the streamed screen
- Multi-device phone farm with per-device job queues

**Forge reusable skills for any app**
- YAML-based UI element definitions per app
- Platform-specific selectors with `elements.yaml` for Android and `elements_ios.yaml` for iOS
- Python action classes with precondition checks
- Multi-step workflows that chain actions together
- Built-in skills for TikTok and Play Store
- iOS browser/news demo skill and smoke-level TikTok iOS workflows
- **Skill Hub** — browse, search, and install skills from the community registry
- Install from CLI: `android-agent skill install tiktok`

**Teach the ghost new tricks**
- BFS-based auto app explorer — discovers every screen and transition
- LLM-assisted Skill Creator — chat with AI while viewing the live device stream
- The AI identifies UI elements and generates action/workflow code

**Scale the haunting**
- Multi-device phone farm with per-device job queues
- Bot runner: queue, schedule, and monitor automation jobs
- Per-device integration tests with Android screen recording or iOS WDA MJPEG recording

### Platform Support

| Surface | Android | iOS |
|---------|---------|-----|
| Device ref | ADB serial, e.g. `emulator-5554` | `ios:<udid>` |
| Backend | ADB + optional Portal companion app | Appium XCUITest + WebDriverAgent |
| Real device support | Yes | Yes, with Mac/Xcode/WDA signing |
| Simulator/emulator support | Android emulator tooling | Booted iOS simulators via Appium/WDA |
| Live stream | Portal WebRTC, MJPEG, screencap | WDA MJPEG, screenshot polling fallback |
| Screen tree | Android UIAutomator XML | Normalized XCTest accessibility tree |
| Skills | `elements.yaml`, Android packages | `elements_ios.yaml`, iOS bundle IDs |
| Android-only today | ADB shell, intents, wireless ADB, Play Store helpers, Portal overlay | Unsupported with stable platform errors |

---

## Requirements

- **Python 3.10+**
- **Android**: Android phone with USB debugging enabled and **ADB** on PATH (`adb devices` should list your phone)
- **iOS**: macOS with Xcode, Appium 2 + XCUITest driver, and a trusted iPhone or booted simulator
- **Node.js 18+** (for the frontend dev server)

---

## iOS Support (Experimental)

Ghost can also drive iPhones through Appium/WebDriverAgent with the same tool
surface: `ios:<udid>` device refs route tap/swipe/type/screenshot to WDA, and
iOS-aware browser primitives (`open_url`, `read_news`, `extract_visible_text`)
cover web tasks. Android-only tools (`shell`, `launch_intent`, Portal overlay)
return a clear platform error instead of failing silently.

iOS support is **feature-gated and OFF by default** while device testing
matures — enable it with `GITD_ENABLE_IOS=1` (or `ios_platform_enabled=true`
in `.env`). See [docs/SETUP_IOS.md](docs/SETUP_IOS.md) for Appium/WDA setup.

---

## Quick Start

Zero-install with [`uvx`](https://docs.astral.sh/uv/) (or `pipx`):

```bash
# Check your environment first — Python, adb on PATH, devices, ports, LLM keys
uvx ghost-in-the-droid doctor

# Sign in with your Claude subscription — no API key needed (see below)
uvx ghost-in-the-droid login

# Start the server + dashboard
uvx ghost-in-the-droid up
# → http://localhost:5055  (dashboard + API; docs at /docs)
```

`doctor` prints a green/red checklist with fix hints instead of a stack trace when
something's missing (e.g. `adb` not on PATH). Prefer `pipx`? `pipx install
ghost-in-the-droid` gives you the `ghost-in-the-droid` / `android-agent` commands.

### Sign in with your Claude subscription (no API key)

If you have a **Claude Max/Pro** subscription, you don't need an API key.
`android-agent login` signs you in through the `claude` CLI's own Anthropic
OAuth flow and points Ghost at the `claude-code` provider:

```bash
android-agent login       # opens Anthropic sign-in via the claude CLI
```

Ghost never handles or stores your token — the `claude` CLI owns it, including
refresh. Under the hood this is the sanctioned subscription path (we don't touch
Anthropic's private OAuth endpoints). `doctor` shows a green **Claude
subscription** check once you're signed in. To use an API key instead, set
`ANTHROPIC_API_KEY` (or `OPENAI_API_KEY` / `OPENROUTER_API_KEY`) and pick that
provider.

<details>
<summary>From a clone (for development)</summary>

```bash
git clone https://github.com/ghost-in-the-droid/android-agent.git
cd android-agent

# 2. Install Python dependencies
pip install -e ".[all]"

android-agent doctor        # preflight
android-agent up            # start server + dashboard on :5055

# Frontend (separate terminal)
cd frontend && npm install && npx vite --host 0.0.0.0 --port 6175
# Dashboard at http://localhost:6175
```
</details>

### iOS Quick Start

iOS support requires a Mac because Appium uses Xcode's XCUITest/WebDriverAgent stack. Real iPhones also require trust, Developer Mode, UI Automation permission when prompted, and WDA signing with an Apple development team.

```bash
# 1. Install and run Appium XCUITest
npm install -g appium
appium driver install xcuitest
appium --base-path /

# 2. Find your iPhone or booted simulator UDID
xcrun xctrace list devices
xcrun simctl list devices booted

# 3. Configure the backend for iOS
export IOS_DEVICE_UDID="<udid>"
export IOS_APPIUM_URL="http://127.0.0.1:4723"
export IOS_BUNDLE_ID="com.google.chrome.ios"       # or com.apple.mobilesafari
export IOS_MJPEG_SERVER_PORT="9100"                # use unique ports per iOS device

# 4. Run a product-path smoke workflow
uv run python scripts/ios_chrome_news_smoke.py \
  --device "ios:<udid>" \
  --bundle-id "$IOS_BUNDLE_ID" \
  --url https://text.npr.org/ \
  --max-headlines 5 \
  --max-articles 3 \
  --fix-health \
  --out-dir data/ios_chrome_news_smoke
```

For full real-device signing, simulator, WDA MJPEG, health recovery, scheduler, and MCP setup details, see [`docs/SETUP_IOS.md`](docs/SETUP_IOS.md).

### Environment Variables

Copy `.env.example` to `.env` (if provided) or create a `.env` file in the project root. The server reads configuration via Pydantic Settings. Optional variables include:

| Variable | Purpose |
|----------|---------|
| `OPENAI_API_KEY` | LLM features (Skill Creator, Agent Chat) |
| `ANTHROPIC_API_KEY` | Alternative LLM provider |
| `OPENROUTER_API_KEY` | OpenRouter LLM provider |
| `DEFAULT_DEVICE` | ADB serial (auto-detected if empty) |
| `IOS_DEVICE_UDID` | iPhone or simulator UDID; devices are addressed as `ios:<udid>` |
| `IOS_APPIUM_URL` | Appium server URL, default `http://127.0.0.1:4723` |
| `IOS_BUNDLE_ID` | Default iOS app/browser bundle, e.g. `com.google.chrome.ios` or `com.apple.mobilesafari` |
| `IOS_DEVICES_JSON` | Per-device iOS config for multiple phones/simulators, WDA ports, bundle IDs, and MJPEG ports |
| `IOS_MJPEG_SERVER_PORT` | WDA MJPEG stream port; use one unique port per iOS device |

**No API keys needed for local models:** Select Ollama in the Phone Agent tab — runs entirely on your machine with [Ollama](https://ollama.com). Install, pull a model, go:

```bash
brew install ollama       # or curl -fsSL https://ollama.com/install.sh | sh
ollama serve &
ollama pull llama3.2:3b   # 2GB, fast, good tool-use
```

**No API keys needed for local models:** Select Ollama in the Phone Agent tab — runs entirely on your machine with [Ollama](https://ollama.com). Install, pull a model, go:

```bash
brew install ollama       # or curl -fsSL https://ollama.com/install.sh | sh
ollama serve &
ollama pull llama3.2:3b   # 2GB, fast, good tool-use
```

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
      safari/                   #   iOS browser/news demo skill
      tiktok_ios/               #   iOS TikTok smoke workflows
    bots/
      common/
        adb.py                  #   Device class: tap, swipe, dump XML, wait_for
        ios.py                  #   IOSDevice class: Appium/WDA session, UI tree, gestures
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
4. **Device backends** route by device ref. Bare serials use `bots/common/adb.py`; `ios:<udid>` refs use `bots/common/ios.py` and Appium/WDA.
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

## MCP Server — Give Any AI Agent a Mobile Body

The project ships an [MCP](https://modelcontextprotocol.io) server with 35 tools for mobile control. Any MCP-compatible AI client (Claude Code, Claude Desktop, Cursor, VS Code Copilot, Windsurf) can use them. Android serials receive the Android implementation; `ios:<udid>` refs route to the iOS backend where supported and return stable unsupported-platform errors for Android-only tools.

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

**For contributors** who clone the repo: the `.mcp.json` is already there — the 35 mobile tools are available on first `claude` launch.

### Available tools

| Category | Tools |
|----------|-------|
| Screen | `screenshot`, `get_elements`, `get_screen_tree`, `get_screen_xml`, `screenshot_annotated`, `screenshot_cropped` |
| Interaction | `tap`, `tap_element`, `swipe`, `long_press`, `type_text`, `type_unicode`, `press_back`, `press_home`, `press_key` |
| Apps | `launch_app`, `search_apps`, `list_apps`, `launch_intent` |
| Context | `get_phone_state`, `classify_screen`, `find_on_screen`, `ocr_screen`, `ocr_region` |
| Device | `list_devices`, `clipboard_get`, `clipboard_set`, `get_notifications`, `open_notifications`, `toggle_overlay` |
| Skills | `list_skills`, `run_workflow`, `run_action`, `create_skill`, `explore_app` |
| Browser/iOS | `open_url`, `browser_back`, `get_current_url`, `wait_for_text`, `extract_visible_text`, `extract_articles`, `read_news` |

`toggle_overlay`, `launch_intent`, Android shell helpers, wireless ADB, Play Store helpers, and Portal-specific actions remain Android-only.

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
- `skill.yaml` — metadata (name, version, app package or iOS bundle ID, supported platforms, actions, workflows)
- `elements.yaml` — Android UI element resource IDs and descriptions
- `elements_ios.yaml` — optional iOS selectors for XCTest accessibility trees
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
| Device Control | ADB for Android; Appium XCUITest/WebDriverAgent for iOS |
| Streaming | Android MJPEG/WebRTC via Portal; iOS WDA MJPEG plus screenshot fallback |
| LLM | OpenAI, Anthropic (optional) |
| Linting | Ruff |
| Testing | pytest, Playwright (optional) |

---

## Running Tests

Most tests are unit/API tests and run without a live device. Live Android and iOS integration tests require the relevant device stack.

```bash
# Run all tests on a specific device
DEVICE=<serial> python3 -m pytest tests/ -v --tb=short

# Run a single test file
DEVICE=<serial> python3 -m pytest tests/test_00_baseline.py -v
```

Get your device serial from `adb devices`.

For iOS live smoke tests:

```bash
IOS_LIVE_NEWS_TEST=1 \
IOS_DEVICE_UDID="<udid>" \
IOS_APPIUM_URL="http://127.0.0.1:4723" \
IOS_BUNDLE_ID="com.google.chrome.ios" \
uv run --extra test python -m pytest tests/test_browser_news.py::test_live_ios_chrome_news_workflow
```

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
