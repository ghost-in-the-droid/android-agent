---
title: "🏗️ Development Setup"
description: Prerequisites, install from source, project structure, and how to run the test suite.
---

This guide covers setting up a development environment for contributing to Ghost in the Droid.

## Prerequisites

- Python 3.10+
- Android phone with USB debugging enabled (or Android emulator)
- ADB installed and on PATH (`adb devices` shows your device)

## Install from Source

```bash
git clone https://github.com/[org]/android-agent.git
cd android-agent

# Install with dev dependencies
pip install -e ".[dev]"
```

## Verify Setup

```bash
# Check ADB sees your device
adb devices

# Run the test suite
DEVICE=<your_serial> python3 -m pytest tests/ -v --tb=short

# Start the dashboard
python3 run.py
# Open http://localhost:5055
```

## Project Structure

```
android-agent/
  run.py                              # Entry point -> http://localhost:5055
  pyproject.toml                      # Package config (pip install -e .)
  gitd/                   # All application code (54 Python files)
    server.py                         # Flask API + scheduler (132 routes, ~4500 LoC)
    db.py                             # SQLite ORM (~2000 LoC, 20+ tables)
    bots/
      common/
        adb.py                        # Device class (47+ methods)
        elements.py                   # Version-resilient UI element resolution
        discover_rids.py              # RID extraction tool
        rid_maps/                     # JSON RID maps per app version
      tiktok/                         # 9 TikTok bot scripts
      instagram/                      # 3 Instagram bot scripts
    skills/
      base.py                         # Action, Workflow, Skill base classes
      auto_creator.py                 # BFS app explorer
      macro_recorder.py               # Record/replay
      _run_skill.py                   # Subprocess runner
      app_cards/                      # Per-app knowledge files
      _base/                          # 9 shared actions
      tiktok/                         # 13 actions + 9 workflows + 41 elements
      instagram/                      # Skill skeleton
    agent/
      agent_core.py                   # LLM content planner (~730 LoC)
      tt/ yt/ ig/                     # Platform workspaces
    services/
      emulator_service.py             # EmulatorManager + EmulatorPool
    routers/
      emulators.py                    # Emulator Flask Blueprint
    tools/                            # TTS, overlay, export, dashboard check
    static/
      dashboard.html                  # Main SPA (14 tabs, ~400K)
  data/                               # Runtime data
    gitd.db                      # SQLite database (WAL mode)
    profile_screenshots/              # Crawled profile images
    app_explorer/                     # State graphs + screenshots
  tests/                              # Pytest suite (19 files)
  docs/                               # Documentation
  config/                             # Credentials (gitignored)
```

## Key Files

| File | LoC | What It Does |
|------|-----|-------------|
| `server.py` | ~4500 | Flask app, 132+ routes, scheduler daemon, WebRTC relay |
| `db.py` | ~2000 | SQLite schema (20+ tables), all CRUD operations |
| `adb.py` | ~700 | Device class, 47+ ADB wrapper methods |
| `base.py` | 262 | Skill system base classes |
| `dashboard.html` | ~7800 | Entire SPA frontend (vanilla JS + Tailwind) |
| `agent_core.py` | ~730 | LLM content planner |

## Running Tests

Tests require a physical phone (or emulator) with TikTok installed.

```bash
# All tests
DEVICE=YOUR_DEVICE_SERIAL python3 -m pytest tests/ -v --tb=short

# Single test file
python3 -m pytest tests/test_04_crawl.py -v

# Single test function
python3 -m pytest tests/test_04_crawl.py::test_crawl_top -v
```

### Test Files

| File | What It Tests |
|------|--------------|
| `test_00_baseline` | Correct TikTok account is active |
| `test_01_accounts` | Account switching round-trip |
| `test_02_draft` | Video upload as draft |
| `test_03_post` | Live post (skipped by default) |
| `test_04_crawl` | Hashtag profile crawling |
| `test_08_draft_publish` | Draft-to-public publish |

## Database

The SQLite database at `data/gitd.db` uses WAL mode for concurrent access. Schema migrations are applied automatically on server startup.

Key tables: `scheduled_jobs`, `job_queue`, `job_runs`, `phones`, `chat_history`, `skill_runs`, `skill_compat`.

## Next Steps

- [Adding Skills](/contributing/skills/) -- the highest-impact contribution
- [Code Contributions](/contributing/code/) -- PR process and code style
