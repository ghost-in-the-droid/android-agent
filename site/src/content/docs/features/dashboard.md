---
title: "📋 Dashboard"
description: The Vue 3 dashboard — device control, skills, scheduling, and automation in one place.
---

The dashboard is a Vue 3 single-page application served by Vite during development.

## Starting the Dashboard

```bash
# Terminal 1: backend
python3 run.py
# API at http://localhost:5055

# Terminal 2: frontend
cd frontend && npx vite --port 6175
# Dashboard at http://localhost:6175
```

## Tabs

### Phone Agent

Multi-device management:

- Device list with serial, model, nickname, online status
- WebRTC live streaming per device
- Element overlay for interactive exploration
- Remote tap/type/back controls

### Scheduler

24-hour visual timeline:

- Color-coded job bars by type
- Schedule CRUD form (create, edit, delete)
- Recent runs table with status filters
- Per-phone queue status indicators

### Skill Hub

Browse, run, and export skills:

- Card grid with expandable detail views
- Action and workflow lists with descriptions
- Device selector and parameter input
- Run button (enqueues to job scheduler)
- Export as ZIP

### Skill Creator

Split-screen LLM skill builder:

- Left: chat with LLM (OpenRouter, Claude, Ollama, Claude Code)
- Right: live device stream with numbered element overlay
- Execute proposed actions on device

### Skill Miner (Explorer)

App exploration (BFS):

- Searchable package dropdown (130+ installed apps)
- Start/stop controls with depth, states, and settle parameters
- Live progress bar with scrolling log
- State browser with screenshots and element lists

### Tools

Utility tools hub for common operations.

### Manual Run

Quick-launch controls for automation jobs:

- Queue management: add, remove, reorder jobs
- Live log viewer
- Job history with status tracking
- Start/stop controls

### Tests

Per-phone pytest runner:

- Select device and test files
- Screen recording capture during tests
- Video + log overlay viewer for debugging

### Emulators

Headless emulator management (coming soon).

## Plugin Tabs

The dashboard supports dynamic tabs via the plugin system. When premium features are installed, additional tabs appear automatically. The backend exposes `GET /api/features` which the frontend checks on load.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Framework | Vue 3 (Composition API) |
| Build | Vite + TypeScript |
| CSS | Tailwind CSS 4 |
| Video | WebRTC + MJPEG fallback |
| Live Logs | Server-Sent Events (EventSource) |

## Accessing from Another Machine

The backend binds to `0.0.0.0:5055` by default. Access the dashboard from any machine on the same network:

```
http://<server-ip>:6175
```

Note: there is no authentication. Anyone on the network can access all controls.

## Related

- [WebRTC Streaming](/features/webrtc/) — live device stream details
- [Scheduler](/features/scheduler/) — job scheduling system
- [Skill Hub](/skills/using-skills/) — browsing and running skills
