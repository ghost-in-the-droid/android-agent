# Roadmap

> Last updated: 2026-04-02

---

## Done

- **FastAPI Migration** -- all 148 Flask routes migrated to FastAPI + SQLAlchemy + Pydantic. Auto-generated docs at `/docs` and `/redoc`.
- **Vue 3 Frontend** -- 15-tab dashboard replaces the 9800-line monolithic HTML. Vue 3 + Vite + TypeScript + Tailwind CSS.
- **Skill Hub + Public Registry** -- REST API, CLI (`android-agent skill install`), community skills via GitHub topic tag.
- **Skill Creator** -- split-screen LLM chat + live device stream, 4 backends (OpenRouter, Claude, OpenAI, Ollama).
- **WebRTC Streaming** -- live 720x1280 via Portal MediaProjection, MJPEG fallback, multi-device viewer.
- **Auto Skill Miner** -- BFS state discovery, state graphs, screenshots. Dashboard tab + CLI.
- **ADB Core Expansion** -- 47 Device methods (stealth, multi-touch, unicode, notifications).
- **Macro Record/Replay** -- programmatic recording, JSON save/load, configurable replay speed.
- **Alembic Migrations** -- DB schema versioned, `alembic upgrade head` for deployments.
- **CI Pipeline** -- GitHub Actions: lint (ruff), API smoke tests, frontend build, type-check.

---

## Next

### MCP Server
Expose Device + Skills as MCP tools so external LLM agents (Claude, Cursor, etc.) can control phones programmatically.
- Standard MCP protocol for tool discovery and invocation
- Any MCP-compatible client can tap, swipe, screenshot, run skills
- See `docs/tasks/TASK_MCP_SERVER.md`

### Emulator Support
Run skills on Android emulators (AVD) in addition to physical phones.
- Auto-detect emulator instances alongside physical devices
- EmulatorTab in the Vue frontend for creating/managing AVDs
- See `docs/tasks/TASK_EMULATOR_SUPPORT.md`

### Skill Miner Dashboard Tab
Full UI for launching BFS explorations, watching progress live, browsing state graphs with screenshots.
- 6 new API endpoints for exploration management
- Launch panel, live progress view, interactive state browser
- Job queue integration for background exploration
- See `docs/tasks/TASK_APP_EXPLORER_TAB.md`

### More App Skills
Run auto-explorer + manual refinement for Twitter/X, WhatsApp, YouTube, Telegram, Reddit.
- Each: explore -> LLM generate skeleton -> human refine -> test -> publish to Skill Hub
- Community contributions welcome via GitHub topic tag `android-agent-skill`

### Docs Site + Skill Hub Merge
Consolidate the Starlight docs site with the Skill Hub browsing experience.
- Unified search across docs and skills
- See `docs/tasks/TASK_MERGE_DOCS_AND_SKILLHUB.md`

### Cleanup: Remove db.py Shim Imports from Routers
Several routers still lazy-import from the deprecated `gitd.db` shim. These need to be rewritten as SQLAlchemy operations. Tracked in `docs/refactor/backend-cutover.md`.

---

## Future

- **Multi-user auth** -- dashboard auth, user accounts, role-based access
- **Cloud deployment** -- remote backend with USB/IP device forwarding or cloud emulators
- **Semantic skill search** -- vector-based skill discovery across the registry
- **WebRTC 30 FPS** -- upgrade streaming to scrcpy 2.x or H.264 passthrough
- **Vision model support** -- send screenshots to LLMs in Skill Creator for visual understanding
- **Bezier curve swipe paths** -- more human-like gesture simulation
- **Per-skill test framework** -- run actions with assertions, integrated into CI
- **Skill versioning + dependency management** -- semver, compatible app version ranges
- **Retry-on-failure in scheduler** -- automatic retry with backoff for failed jobs
