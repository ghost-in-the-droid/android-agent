---
title: "📥 Installation"
description: Install Python, ADB, and Ghost in the Droid. Configure environment variables for AI features.
---

Get from zero to running automation in 10 minutes. No API keys required for core features.

## Prerequisites

| Requirement | Version | How to Check |
|------------|---------|--------------|
| Python | 3.10+ | `python3 --version` |
| ADB | Any recent | `adb --version` |
| Android phone | 5.0+ (API 21+) | Physical device or emulator |
| USB cable | Data-capable | Not a charge-only cable |

## Install ADB

**Ubuntu/Debian:**

```bash
sudo apt install android-tools-adb
```

**macOS:**

```bash
brew install android-platform-tools
```

**Windows:**

Download from [Android SDK Platform-Tools](https://developer.android.com/tools/releases/platform-tools), extract, and add the folder to your PATH.

Verify ADB is installed:

```bash
adb --version
# Android Debug Bridge version 1.0.41
```

## Install Ghost in the Droid

```bash
git clone https://github.com/ghost-in-the-droid/android-agent.git
cd ghost-in-the-droid

# Install in development mode (recommended)
pip install -e .

# Or install dependencies manually
pip install flask requests pyyaml openai
```

The `-e` flag installs in editable mode so changes to the source take effect immediately.

## Configuration

### Environment Variables

Create a `.env` file by copying the example:

```bash
cp .env.example .env
```

**No API keys are needed for core automation.** The following work out of the box:

- ADB device control (tap, swipe, type, screenshots)
- Skill system (load, run, create skills)
- Macro recording and replay
- Dashboard (all 9 tabs)
- Job scheduler
- App Explorer

### Optional: AI Features

Add these to `.env` only if you need AI-powered features:

```bash
# LLM features: Skill Creator, Content Agent (pick one or more)
OPENAI_API_KEY=your_key_here
ANTHROPIC_API_KEY=your_key_here
OPENROUTER_API_KEY=your_key_here
```

### Optional: Skill Creator LLM Backends

The Skill Creator supports 4 LLM backends. Configure whichever you want to use:

| Backend | Config | Default Model |
|---------|--------|---------------|
| OpenRouter | `OPENROUTER_API_KEY` env var | `anthropic/claude-sonnet-4` |
| Claude API | `ANTHROPIC_API_KEY` env var | `claude-sonnet-4-20250514` |
| Ollama | Auto-detect at `localhost:11434` | `llama3` |
| Claude Code | `claude` CLI installed | `sonnet` |

## Verify Installation

```bash
# Start the server
python3 run.py
```

Open http://localhost:5055 in your browser. You should see the dashboard with 9 tabs.

```bash
# Quick Python verification
python3 -c "
from gitd.bots.common.adb import Device
from gitd.skills.tiktok import load
s = load()
print(f'Skill: {s.name} | Actions: {len(s.list_actions())} | Workflows: {len(s.list_workflows())}')
"
# Expected: Skill: tiktok | Actions: 13 | Workflows: 9
```

## Device Selection

If you have multiple phones connected, set the default device:

```bash
# List connected devices
adb devices

# Set default via environment variable
export DEVICE=YOUR_DEVICE_SERIAL

# Or pass per-command
DEVICE=YOUR_DEVICE_SERIAL_2 python3 -m pytest tests/ -v
```

## Project Structure

```
android-agent/
  run.py                          # Entry point (port 5055)
  pyproject.toml                  # Package config
  .env                            # Your API keys (gitignored)
  gitd/               # All application code
    server.py                     # Flask API (113+ routes)
    db.py                         # SQLite ORM (20+ tables)
    bots/common/adb.py            # Device class
    skills/                       # Skill packages
    agent/                        # LLM content planner
    static/dashboard.html         # SPA dashboard
  data/                           # Runtime data
    gitd.db                  # SQLite database
  tests/                          # Pytest suite (19 files)
  config/                         # Credentials (gitignored)
```

## Next Steps

- [Connect Your Phone](/getting-started/connect-phone/) -- enable USB debugging and authorize
- [Hello World](/getting-started/hello-world/) -- run your first automation
