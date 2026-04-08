# Feature Summary

> Last updated: 2026-04-02

---

## Core Platform

### FastAPI Backend
- 21 routers, 113+ routes, auto-generated API docs at `/docs` (Swagger) and `/redoc` (ReDoc)
- SQLAlchemy 2.0 ORM with 23 tables, Alembic migrations
- Pydantic v2 request/response validation
- Configuration via `pydantic_settings.BaseSettings` from `.env`

### Vue 3 Frontend
- 9-tab dashboard (Vue 3 + Vite 8 + TypeScript + Tailwind CSS 4)
- Tabs use `v-show` for state preservation across switches
- Dark theme with CSS variables
- Chart.js + Plotly.js for analytics visualization

---

## Device Control

### ADB Core (47 Device methods)
- **Basic**: tap, swipe, back, press_enter, type_text, dump_xml, screenshot
- **Navigation**: restart app, go_to_profile, search, screen_type detection
- **Advanced**: long_press, pinch_in, pinch_out, type_unicode, clipboard get/set
- **Notifications**: open/close/read/clear notifications, open_settings
- **Stealth**: stealth_tap (Gaussian jitter), stealth_swipe (variable speed), stealth_type (char-by-char delays)

### Phone Streaming
- **MJPEG** -- reliable fallback, works on any device with ADB
- **WebRTC** -- low-latency via droidrun Portal app, 720x1280
- Interactive tap/swipe on the streamed screen (coordinates scaled to device resolution)
- Multi-device simultaneous viewing
- FPS counter overlay (color-coded: green 20+, yellow 10-19, red <10)

---

## Skill System

### Architecture
- YAML-based UI element definitions per app (resource IDs, content descriptions, fallback chains)
- Python action classes with precondition/execute/postcondition/rollback
- Multi-step workflows that chain actions with retry and error handling
- Version-resilient element resolution: content_desc -> text -> resource_id -> coords

### Built-in Skills
- **TikTok**: 13 actions, 3 workflows, 41 UI elements
- **Instagram**: skill skeleton (skill.yaml only)
- **Base**: 9 shared actions (tap, swipe, type, wait, etc.)

### Skill Hub + Public Registry
- Browse, search, and install skills from the public registry
- CLI: `android-agent skill install tiktok`, `skill search`, `skill update`, `skill remove`
- REST API: list, detail, run, export (ZIP), import
- Community contributions via GitHub repos tagged `android-agent-skill`
- Registry at [`registry/`](https://github.com/ghost-in-the-droid/android-agent/tree/main/registry) inside the main repo

### Skill Creator (LLM-powered)
- Split-screen: chat panel (left) + live device stream with numbered element overlay (right)
- 4 LLM backends: OpenRouter, Claude API, OpenAI, Ollama
- LLM sees current screen elements + action history
- Proposes JSON action plans, user clicks Execute to run on device

### Auto Skill Miner
- BFS-based UI state discovery -- automatically navigates an app and screenshots every screen
- Builds a graph of reachable states and transitions
- Outputs: `data/skill.miner/<package>/state_graph.json` + screenshots + XML dumps
- Runnable from CLI or via Explorer API/dashboard tab

### Macro Record/Replay
- Record action sequences programmatically
- Save/load as JSON
- Replay at configurable speed

---

## Content Pipeline

### Content Calendar
- LLM-powered content planning agent (OpenRouter/OpenAI)
- Markdown strategy editor
- Status tracking: planned -> generating -> generated -> scheduled -> posted

### Upload Automation
- Push video to device, fill captions/hashtags, post or save as draft
- 43-step TikTok upload with draft-tag matching
- Draft-then-publish workflow with scheduled posting time

### Post Analytics
- OCR-based scraping of post performance (views, likes, comments, shares, watch time)
- Continuous metrics collection as time-series data

---

## Bot Automation

### Crawling
- Hashtag crawling with configurable passes and tab filters
- Profile discovery and data collection

### Content Upload
- Video upload as draft or direct post
- Draft-to-publish workflow

---

## Scheduling & Job Queue

- Per-phone job queue with priority-based preemption
- 6 job types: crawl, post, publish_draft, skill_workflow, skill_action, app_explore
- 30-second scheduler tick, one active job per phone
- Dashboard with 24h timeline, job CRUD, queue status

---

## Testing

- **API smoke tests**: 32 tests in `tests/api/test_smoke.py` (no device needed)
- **Device integration tests**: 19 test files with per-phone screen recording
- **Dashboard test runner**: GUI for launching tests, viewing live logs and recordings
- **CI**: GitHub Actions runs lint + API tests + frontend build + type-check on every push

---

## Analytics

- **TikTok Metrics**: per-account performance charts (views, likes, comments, shares, watch time)

---

## Key File Reference

```
gitd/
  app.py                      # FastAPI factory, router registration
  config.py                   # Pydantic settings from .env
  models/                     # SQLAlchemy 2.0 table definitions (23 tables)
  schemas/                    # Pydantic v2 request/response models
  routers/                    # FastAPI route handlers (21 files)
  services/                   # Business logic (scheduler, etc.)
  skills/                     # Skill packages (base, tiktok, instagram)
  bots/common/adb.py          # Device class (47 methods)
  agent/agent_core.py         # LLM content planning agent
  _deprecated/                # Old Flask server + raw sqlite3 (preserved for bots/ shim)
frontend/
  src/App.vue                 # 9-tab shell
  src/views/                  # One view per tab
  src/composables/useApi.ts   # Typed API fetch wrapper
```
