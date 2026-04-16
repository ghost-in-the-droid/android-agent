# Setup Guide

Get from zero to running automation in 10 minutes. Works on Linux, macOS, and Windows.

---

## Prerequisites

| Requirement | Version | Check |
|------------|---------|-------|
| Python | 3.10+ | `python3 --version` |
| Node.js | 18+ | `node --version` |
| ADB | Any recent | `adb --version` |
| Android phone | USB debugging enabled | Physical device with data-capable USB cable |
| Git | Any | `git --version` |
| ffmpeg | Any (for MJPEG streaming) | `ffmpeg -version` |

### Install Dependencies by OS

**macOS:**
```bash
brew install python@3.12 node android-platform-tools ffmpeg git
```

**Ubuntu/Debian:**
```bash
sudo apt install python3 python3-pip nodejs npm android-tools-adb ffmpeg git
```

**Windows:** Download Python, Node, ADB platform-tools, and ffmpeg from their official sites.

---

## Phone Setup

1. **Settings > About Phone** — tap **Build Number** 7 times to enable Developer Options
2. **Settings > Developer Options** — enable **USB Debugging**
3. Plug in USB, run `adb devices`, tap **Allow** on the authorization prompt

```bash
# Should show your device with "device" status
adb devices
# XXXXXXXXXXXXXXX    device
```

---

## Repository

The project lives in a single repo. The public skill registry is at `registry/` inside it.

| Repo | Purpose | Clone? |
|------|---------|--------|
| [ghost-in-the-droid](https://github.com/ghost-in-the-droid/android-agent) | Main project — backend, frontend, bots, skills, registry | **Yes** (required) |

---

## Install

```bash
# 1. Clone the repo
git clone https://github.com/ghost-in-the-droid/android-agent.git
cd ghost-in-the-droid

# 2. Install Python package (includes all dependencies)
pip install -e ".[all]"

# 3. Copy environment config
cp .env.example .env
# Edit .env — add your device serial and any API keys (optional for core ADB)

# 4. Install frontend dependencies
cd frontend && npm install && cd ..
```

---

## Start

```bash
# Terminal 1: Backend (FastAPI on :5055)
python3 run.py

# Terminal 2: Frontend (Vue on :6175)
cd frontend && npx vite --host 0.0.0.0 --port 6175
```

Verify:
```bash
# Backend
curl http://localhost:5055/api/health
# {"status": "ok", "server": "fastapi"}

# Frontend
open http://localhost:6175
```

API docs auto-generated at http://localhost:5055/docs

---

## Environment Variables

Core ADB automation works without any API keys. For AI-powered phone control, either use Ollama (free, local, no keys) or add API keys in `.env`:

| Variable | Purpose | Required? |
|----------|---------|-----------|
| `DEFAULT_DEVICE` | ADB serial of primary phone (auto-detect if empty) | Recommended |
| `OPENAI_API_KEY` | LLM features (Skill Creator, Content Agent) | For AI features |
| `ANTHROPIC_API_KEY` | Alternative LLM provider | Optional |
| `OPENROUTER_API_KEY` | LLM routing (content planning) | For content pipeline |

---

## Ollama (Local LLM — No API Keys)

Run a tool-using Android agent entirely on your machine:

```bash
# Install Ollama
brew install ollama       # macOS
# or: curl -fsSL https://ollama.com/install.sh | sh  # Linux

# Start server + pull a model
ollama serve &
ollama pull llama3.2:3b   # 2GB, fast, good tool-use

# Other good options:
# ollama pull gemma3:4b    # Google, multilingual
# ollama pull qwen3:4b     # strong reasoning
# ollama pull phi4-mini:3.8b  # Microsoft, efficient
```

In the dashboard: Phone Agent tab > Provider: Ollama > pick a model > chat. The agent can see the screen, tap elements, type, navigate — multi-turn with tool execution.

---

## Database

SQLite with WAL mode. Created automatically on first `python3 run.py`. Schema managed by Alembic:

```bash
alembic upgrade head        # apply pending migrations
alembic check               # check for schema drift
```

---

## Skill Hub CLI

```bash
# Search the public registry
android-agent skill search tiktok

# Install a skill
android-agent skill install tiktok

# List installed skills
android-agent skill list
```

---

## Multiple Devices

```bash
# List connected devices
adb devices

# Set default in .env
DEFAULT_DEVICE=your_serial_here

# Or pass per-command
DEVICE=SERIAL python3 -m pytest tests/ -v
```

---

## macOS-Specific Notes

- USB: just plug in and trust the device — no udev rules needed
- If `adb devices` shows nothing: try a different USB cable (some charge-only cables don't support data)
- If `brew install android-platform-tools` fails: `brew tap homebrew/cask && brew install --cask android-platform-tools`
- Port 5055 conflict: check with `lsof -i :5055` and kill any existing process

---

## MCP Server (AI Agent Tools)

The project includes an MCP server that exposes 35 Android automation tools to any AI client. If you cloned this repo, the `.mcp.json` is already configured.

**Claude Code / Codex** (if not using the repo's `.mcp.json`):
```bash
claude mcp add android-agent -- uvx --from ghost-in-the-droid android-agent-mcp
codex mcp add android-agent -- uvx --from ghost-in-the-droid android-agent-mcp
```

**Claude Desktop / Cursor / VS Code / Windsurf** — see the [MCP section in README.md](../README.md#mcp-server--give-any-ai-agent-an-android-body) for config snippets.

Verify it works:
```bash
# List available tools
python3 -c "from gitd.mcp_server import mcp; print(len(mcp._tool_manager.list_tools()), 'tools')"
```

---

## Emulators (Optional)

Run Android emulators alongside physical devices. Requires Android SDK:

```bash
# macOS (Homebrew)
brew install --cask android-commandlinetools
sdkmanager "platform-tools" "emulator"
sdkmanager "system-images;android-35;google_apis_playstore;arm64-v8a"

# Create an AVD
echo "no" | avdmanager create avd -n test_api35 \
  -k "system-images;android-35;google_apis_playstore;arm64-v8a" -d medium_phone

# Or use the API/dashboard after starting the server
```

The Emulators tab in the dashboard handles creation, boot, snapshots, and pool management.

---

## Next Steps

1. Open `http://localhost:6175` and explore the dashboard
2. Navigate to **Phone Agent** to verify your device appears
3. Try the live MJPEG stream to see your phone screen
4. Browse **Skill Hub** to see installed skills and run them
5. Open Claude Code in this project — the MCP tools are ready to use
6. Read [ARCHITECTURE.md](ARCHITECTURE.md) for how the system fits together
