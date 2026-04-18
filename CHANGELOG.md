# Changelog

All notable changes to Ghost in the Droid are documented here.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) · Versioning: [Semantic](https://semver.org/)

## [Unreleased]

## [1.2.0] — 2026-04-17

### Added
- **Ghost Bench** — in-dashboard benchmark system with 14 built-in tasks (settings + navigation). Runner with SSE live streaming. New `Benchmarks` tab in the dashboard. Foundation for Phase 2 (real AndroidWorld integration).
- **7 benchmark API endpoints** (`/api/benchmarks/*`) — list suites, start run, stream events, past runs, stop.
- **Live Ollama model discovery** — new `GET /api/agent-chat/providers` endpoint queries `localhost:11434/api/tags` so the dropdown shows actually-installed models, not a hardcoded list.
- **Background Ollama model pull** — endpoint to pull new models without blocking the UI, with live status tracking.

### Changed
- Frontend model selector fetches providers on mount instead of relying on hardcoded constants.
- Better errors when Ollama isn't running or a requested model isn't installed.

### Fixed
- Confusing "connection error" when user selected a model not installed locally — now says "model X not found, pull it first" with a pull button.

## [1.1.0] — 2026-04-16

### Added
- **Ollama support** — multi-turn tool-using loop for local models. Zero API keys needed. Pre-filled dropdown: `llama3.2:3b`, `llama3.2:1b`, `gemma3:4b`, `qwen3:4b`, `phi4-mini:3.8b`, `mistral:7b`.
- **`_parse_tool_calls()`** — robust tool-call extractor handling common LLM JSON quirks (doubled braces from gemma/qwen, trailing commas, etc.).
- **Ollama unload button** — free GPU memory between chats.
- **Emulator support (full stack)** — FastAPI router, Pool management, 4 Vue components, 21 REST endpoints. See `gitd/services/emulator_service.py`.
- **Mac / Apple Silicon support** — HVF hardware acceleration, arm64-v8a auto-detection, Homebrew SDK path detection.
- **MCP distribution** — `.mcp.json` ships with the repo; 35 tools available on first clone.
- **PyPI package** — `uvx --from ghost-in-the-droid android-agent-mcp` runs the MCP server without cloning.
- **CI/CD release pipeline** — push a `v*` tag → auto-publish to PyPI.

### Changed
- **Flask → FastAPI** — emulator router fully migrated to `APIRouter` + Pydantic models.
- **README & SETUP.md** — MCP install docs, emulator install docs, multi-client install snippets (Claude Code, Claude Desktop, Cursor, VS Code Copilot, Windsurf).

### Fixed
- `pyproject.toml` — `dependencies` was mis-nested under `[project.urls]`.
- Import sort in `gitd/app.py` (ruff I001).

## [1.0.0] — 2026-04-08

Initial open-source release of Ghost in the Droid.

### Added
- FastAPI backend (`gitd/` package), Vue 3 frontend
- Skills framework (Action / Workflow / Skill with YAML element locators)
- ADB automation primitives (`Device` class: tap, swipe, type, XML dump, screen classification)
- Portal companion APK for on-device streaming & notifications
- MCP server with 35 tools for Android control
- WebRTC screen streaming
- Skill Hub (registry of reusable skills)
- Agent Chat (LLM-driven device control via Claude / Claude Code / OpenRouter / Ollama)

[Unreleased]: https://github.com/ghost-in-the-droid/android-agent/compare/v1.2.0...HEAD
[1.2.0]: https://github.com/ghost-in-the-droid/android-agent/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/ghost-in-the-droid/android-agent/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/ghost-in-the-droid/android-agent/releases/tag/v1.0.0
