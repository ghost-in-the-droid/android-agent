# Changelog

All notable changes to Ghost in the Droid are documented here.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) · Versioning: [Semantic](https://semver.org/)

## [Unreleased]

## [1.3.0] — TBD

_Ghost 1.3 turns Ghost in the Droid into a full agent harness for Android. See [release notes](docs/release-notes/v1.3.0.md) for the full story._

### Added
- **iOS support (experimental, feature-gated)** — control iPhones via Appium/WebDriverAgent with the same tool surface: `ios:<udid>` device refs, platform-routed tap/swipe/type/screenshot, iOS browser primitives (`open_url`, `read_news`, `extract_visible_text`, …), device health + recovery, WDA MJPEG screen recording. OFF by default — enable with `GITD_ENABLE_IOS=1`. Thanks [@blah-mad](https://github.com/blah-mad) ([#8](https://github.com/ghost-in-the-droid/android-agent/pull/8)).
- **6 LLM backends** — Claude Code (CLI), Anthropic API, OpenRouter, Ollama, on-device Gemma, vLLM.
- **On-device inference** — Gemma runs on the phone via MediaPipe (`.task`) or llama.cpp (`.gguf`), Chaquopy Python-in-APK bridge.
- **LangChain + LlamaIndex integrations** — `GhostToolkit` (LangChain `BaseTool`) + `GhostAndroidToolSpec` (LlamaIndex `ToolSpec`), device auto-bound, shared `SAFE_DEVICE_TOOLS` allow-list.
- **`android-agent up` / `doctor` / `login` CLI** — one-command boot, preflight, and Claude subscription sign-in (wraps sanctioned `claude` CLI).
- **`run_flow` MCP tool** — batched execution with fail-closed allow-list + injection blocklist. One round-trip for multi-step workflows.
- **`chain` action** — ordered sub-actions in one call, settle between each, whole batch pre-validated against `SAFE_DEVICE_TOOLS`, single-fail abort ([#39](https://github.com/ghost-in-the-droid/android-agent/pull/39)).
- **`screenshot_sequence` + `sub_agent`** — frame-burst capture to a per-device cache, then a stateless vision sub-call over those frames (60-frame cap; needs `ANTHROPIC_API_KEY`, degrades gracefully without) ([#42](https://github.com/ghost-in-the-droid/android-agent/pull/42)).
- **Differential a11y** — post-action diff of appeared/disappeared elements appended to tool results. On by default, fail-open; `A11Y_DIFF_ENABLED=false` to disable ([#40](https://github.com/ghost-in-the-droid/android-agent/pull/40)).
- **ASCII transliteration for `type_text`** — non-ASCII input NFKD-folded to ASCII before `adb input text` (which is ASCII-only), so accented text no longer blanks the field; use `type_unicode` for full fidelity ([#38](https://github.com/ghost-in-the-droid/android-agent/pull/38)).
- **LLM rate-limit backoff + effort-scaled timeouts** — exponential backoff on 429/overload with SSE keepalive events; per-call timeouts scaled to model tier (opus 420s / sonnet 300s / haiku 240s / 600s default) ([#37](https://github.com/ghost-in-the-droid/android-agent/pull/37)).
- **Unified task-first `ghost` CLI** — `ghost "check reddit" --device asus`; the task is the argument. First-run wizard, `ghost config/setup/devices/doctor`, `ghost mcp install --client claude-code|cursor|codex|opencode`. `gitd` / `android-agent` / `ghost-in-the-droid` keep working (deprecation notice) ([#47](https://github.com/ghost-in-the-droid/android-agent/pull/47)).
- **`list_crashes` / `get_crash` MCP tools** — no-root crash + ANR reports (widened to `-b crash -b events`).
- **Docker+KVM emulator backend** — replaces broken native `avdmanager` path (Linux fix).
- **Tracing tab** — per-turn traces, token accounting, tool-call visibility.
- **Web search tool** — agent-callable mid-conversation.
- **Marketing jobs seam** — `POST /api/marketing-jobs/enqueue` external orchestrator hook.
- **`crm_lookup_contact` + `crm_list_unread_messages` MCP tools** — read-only local CRM lookup primitives.
- **Sitemap + Google Search Console verification** — canonical `site:` URL, `robots.txt`, auto-generated `sitemap-index.xml`.
- **Vercel Web Analytics** — wired into landing + Skill Hub pages.
- **`GITD_CORS_ORIGINS` env override** — comma-separated allowlist for reverse-proxy deploys.

### Changed
- `android-agent up` now defaults to `127.0.0.1`; passing `--host 0.0.0.0` prints an explicit network-exposure warning.
- `create_session` default provider path: `""` → `settings.default_provider`; explicit provider still wins.
- Allow-listed tool set shared as one frozenset across `run_flow` + LangChain toolkit + LlamaIndex toolspec — cannot drift.
- Concurrent-pytest DB isolation: per-worktree path (`/tmp/gitd_pytest_<hash>.db`).

### Fixed
- **Screenshot tool result downscaled to fit the token cap** — large screenshots no longer blow the MCP response budget ([#44](https://github.com/ghost-in-the-droid/android-agent/pull/44)).
- **Security (CWE-352 / community fix)** — CORS `allow_origins=["*"]` + `allow_credentials=True` caused Starlette to reflect any Origin. Fixed to a localhost allowlist. [#10](https://github.com/ghost-in-the-droid/android-agent/pull/10) — thanks [@sebastiondev](https://github.com/sebastiondev) via [Sebastion AI](https://github.com/apps/sebastionai).
- **On-device tool arg normalization** — accepts both flat and nested tool-call shapes (was silently dropping args from Gemma's trained shape).
- **`Device.adb` raises `ADBError` on failure** — was returning stdout with `check=False`, letting ~38 MCP tools inherit phantom-success.
- **Batch-flow allow-list is fail-closed** — new/unknown tools refused, not auto-allowed.
- **`stop_agent` respects session boundaries** — no longer kills every claude subprocess.
- **`doctor` handles macOS Keychain-stored Claude creds** — Linux keeps the fast file-path; macOS falls back to `claude auth status` probe.
- **`list_crashes` / `get_crash` surface ADB failure** — was silently returning "no crashes" on an offline device.
- **Three `tap-element` code paths consolidated** — indexes now shared across surfaces.
- **OpenRouter provider** — full multi-turn tool-use loop.
- **Test suite is honest** — removed fixtures that wiped the real dev DB; per-worktree DB path prevents cross-branch races.

### Deprecated / Removed
- Native `avdmanager` emulator path removed on Linux (Docker required).
- `_chat_claude_code` duplicate code path deleted (~180 LOC).
- Premium DB schema moved out of `gitd/db.py` into private `ghost_premium.db`. Public users won't have it and shouldn't have been calling it.

### Security
See [SECURITY.md](SECURITY.md) for reporting policy. Known open surface (tracked for v1.3.1): unauthenticated `POST /api/skills/install` remains reachable via non-browser clients. Run behind a reverse proxy with auth for any non-loopback exposure.

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
