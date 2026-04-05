# System Architecture

> Last updated: 2026-04-02

## Overview

Android Agent is an ADB-powered automation platform with a skill ecosystem, phone farm management, and a Vue 3 dashboard. The backend is FastAPI + SQLAlchemy, the frontend is Vue 3 + Vite + Tailwind, and device control happens via ADB over USB.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI + Uvicorn (Python 3.10+) |
| ORM | SQLAlchemy 2.0 (`Mapped` types, `mapped_column`) |
| Migrations | Alembic |
| Validation | Pydantic v2 (request/response schemas) |
| Config | `pydantic_settings.BaseSettings` from `.env` |
| Database | SQLite (WAL mode, `data/gitd.db`) |
| Frontend | Vue 3 (Composition API), TypeScript, Vite 8, Tailwind CSS 4 |
| Charts | Chart.js 4, Plotly.js (loaded via CDN) |
| Device Control | ADB (Android Debug Bridge) |
| Streaming | MJPEG fallback + WebRTC (via droidrun Portal) |
| LLM | OpenAI, Anthropic, OpenRouter, Ollama (optional) |
| Linting | Ruff |
| Testing | pytest (API smoke tests + device integration tests) |

---

## Directory Structure

```
android-agent/
  run.py                          # Entry point: Uvicorn on :5055
  alembic.ini                     # Alembic config
  gitd/
    app.py                        # FastAPI factory, CORS, lifespan, 21 routers
    config.py                     # Pydantic settings from .env
    models/           (11 files)  # SQLAlchemy 2.0 ORM (23 tables)
    schemas/           (9 files)  # Pydantic v2 request/response validation
    routers/          (21 files)  # FastAPI route handlers
    services/                     # Business logic (scheduler_service, etc.)
    skills/                       # Skill packages per app
      _base/                      #   Shared actions (tap, swipe, type, wait, etc.)
      tiktok/                     #   TikTok skill (elements, actions, workflows)
      instagram/                  #   Instagram skill
    bots/                         # ADB bot scripts (run as subprocesses)
      common/
        adb.py                    #   Device class: tap, swipe, dump XML, wait_for
      tiktok/                     #   TikTok-specific bots
      instagram/                  #   Instagram-specific bots
    agent/                        # LLM-powered content planning agent
    alembic/                      # Database migration versions
    _deprecated/                  # Old Flask server + raw sqlite3 (preserved, not used)
  frontend/                       # Vue 3 + Vite + TypeScript + Tailwind CSS
    src/
      App.vue                     # Tab shell (15 tabs, v-show for state preservation)
      views/                      # One view per tab
      composables/useApi.ts       # Typed fetch wrapper for /api/* calls
    vite.config.ts                # Vite config + API proxy to :5055
  tests/
    api/test_smoke.py             # 32 API smoke tests (no device needed)
    test_0*.py                    # Device integration tests (phone required)
  docs/                           # Architecture docs, task lists
```

---

## Request Flow

```
Client (Vue SPA or curl)
  |
  |  HTTP  /api/*
  v
FastAPI (:5055)
  |
  |-- Router (routers/*.py) handles the request
  |     |
  |     |-- Pydantic schema validates input (schemas/*.py)
  |     |-- SQLAlchemy session via Depends(get_db) (models/base.py)
  |     |-- Query/mutate the database (models/*.py)
  |     |-- Return Pydantic response model
  |
  |-- For bot/skill jobs: spawns subprocess (bots/, skills/)
  |     |-- Subprocess uses Device class (bots/common/adb.py)
  |     |-- Subprocess talks to phone via ADB over USB
  |
  v
SQLite (data/gitd.db) via SQLAlchemy 2.0
```

---

## Background Services

### Scheduler Tick Thread
Started in `app.py` lifespan. Runs every 30 seconds. Checks for due scheduled jobs, launches them as subprocesses (one active job per phone, priority-based preemption).

### Bot Subprocesses
Bots (`bots/tiktok/*.py`, `bots/instagram/*.py`) and skill runs (`skills/_run_skill.py`) execute as separate Python processes. The backend spawns and monitors them. They import from `bots/common/adb.py` for device control and from `_deprecated/db_raw_sqlite.py` (via `db.py` shim) for database access.

---

## Frontend Architecture

- **Vue 3** with `<script setup lang="ts">` (Composition API)
- **No Vue Router** -- tabs are managed with `v-show` in `App.vue` to preserve state across tab switches
- **API calls** via typed `useApi.ts` composable (`api('/api/...')`)
- **Vite proxy** forwards `/api/*` requests to the backend at `:5055`
- **15 tabs**: Phone Agent, Skill Hub, Skill Creator, Explorer, Influencers, Strategies, Bot, Content, Generate, Content Plan, Metrics, Analytics, Scheduler, Tests, Inbox

---

## Skill System

```
Skill (skill.yaml + elements.yaml)
 |-- Actions (atomic operations with pre/post conditions)
 |     precondition() -> verify device state
 |     execute() -> perform ADB operation
 |     postcondition() -> verify success
 |     rollback() -> undo on failure
 |
 |-- Workflows (composed action sequences)
       run() -> execute actions in order with retry/error handling
```

Skills are YAML-defined UI element maps + Python action/workflow classes. Built-in skills for TikTok (13 actions, 9 workflows, 41 elements) and Instagram. Community skills installable via CLI (`android-agent skill install <name>`) from the public registry.

---

## Key Design Decisions

1. **One job per phone** -- ADB can only automate one app at a time per device
2. **Subprocess execution** -- bots/skills run as subprocesses to keep the server responsive
3. **Pre/post conditions** -- every skill action validates device state before and after
4. **Draft-then-publish** -- videos upload as drafts first, publish at scheduled time
5. **Element fallback chains** -- resilient to app updates (content_desc -> text -> resource_id -> coords)
6. **WAL mode SQLite** -- concurrent reads from dashboard while scheduler writes
7. **db.py shim** -- `gitd/db.py` re-exports from `_deprecated/` so bots/agent scripts keep working without refactoring
