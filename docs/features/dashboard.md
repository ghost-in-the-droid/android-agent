# Dashboard — Feature Summary

## What It Does

Single-page web application at `http://localhost:5055` serving as the unified control center for the automation platform. A monolithic HTML file (~400K) with tabs covering device management, skill ecosystem, scheduling, app exploration, and live device streaming. All state is fetched from the Flask API; no build step required.

## Current State

**Working:**
- Multiple feature tabs with full CRUD functionality
- ~400K single HTML file, vanilla JS + Tailwind CSS via CDN
- Tabulator.js for data grids (filterable, sortable, paginated)
- Chart.js for analytics visualizations
- WebRTC for live device streaming
- Server-Sent Events for live log streaming
- REST API routes powering all tabs
- localStorage persistence for user preferences (selected tab, LLM backend, device)

**Limitations:**
- Single monolithic HTML file — no component architecture, hard to maintain
- No authentication/authorization
- No responsive/mobile layout (desktop only)
- No dark/light theme toggle (dark only)

## Architecture

```
Browser (dashboard.html)
    │
    │  Tab system: lazy-loaded content
    │  Each tab has its own init function + API polling
    ▼
Flask server (server.py, port 5055)
    │
    ├── Static file serving (dashboard.html, metrics_dashboard.html)
    ├── REST API endpoints (JSON)
    ├── SSE endpoints for live log streaming
    └── WebRTC signaling relay
    │
    ▼
SQLite DB (data/gitd.db) + filesystem (data/, /tmp/)
```

## Tabs

| # | Tab | Icon | What It Does |
|---|-----|------|-------------|
| 1 | **Bot** | robot | Quick-launch controls for crawl and post jobs. Live log viewer via SSE, queue controls |
| 2 | **Tests** | flask | Per-phone pytest runner with screen recordings. Video+log overlay viewer for debugging |
| 3 | **Scheduler** | clock | 24h visual timeline (color-coded job bars), schedule CRUD, recent runs table, phone queue status |
| 4 | **Phone Agent** | phone | Multi-device management: status, nickname, WebRTC live streaming, element overlay, tap/type/back controls |
| 5 | **Skill Hub** | puzzle | Browse/run/export skills. Card grid with detail view, device selector, workflow/action execution |
| 6 | **Skill Creator** | wrench | Split-screen: LLM chat assistant (left) + live device stream with interactive element overlay (right) |
| 7 | **Explorer** | compass | App explorer: launch BFS exploration, live progress, browse state graphs with screenshots and XML dumps |

## Files

| File | Purpose |
|------|---------|
| `gitd/static/dashboard.html` | The entire SPA (~400K, single file) |
| `gitd/static/metrics_dashboard.html` | Standalone metrics page (legacy) |
| `gitd/server.py` | Flask server, 132+ API routes, scheduler, WebRTC relay |
| `gitd/db.py` | SQLite schema (20+ tables), CRUD helpers |

## Tech Stack

| Layer | Technology |
|-------|-----------|
| HTML/JS | Vanilla JavaScript (no framework), single file |
| CSS | Tailwind CSS via CDN |
| Tables | Tabulator.js 6.x (filterable, sortable, editable) |
| Charts | Chart.js 4.x |
| Video | WebRTC (native browser API) + MJPEG fallback |
| Live Logs | Server-Sent Events (EventSource) |
| Icons | Lucide icons via CDN |
| Modals | Custom overlay divs (no library) |

## Key UI Patterns

```javascript
// Tab switching — all tabs use this pattern
function showTab(tabId) {
    document.querySelectorAll('.tab-content').forEach(t => t.classList.add('hidden'));
    document.getElementById(tabId).classList.remove('hidden');
    // Lazy-init tab if first visit
    if (!tabInited[tabId]) { initFunctions[tabId](); tabInited[tabId] = true; }
}

// API polling — most tabs poll their data endpoint
setInterval(async () => {
    const resp = await fetch('/api/scheduler/status');
    const data = await resp.json();
    updateSchedulerUI(data);
}, 5000);

// SSE live logs — Bot tab and others
const evtSource = new EventSource('/api/bot/logs/stream');
evtSource.onmessage = (e) => appendLogLine(JSON.parse(e.data));
```

## How to Access

```bash
# Start server
python3 run.py

# Open in browser
open http://localhost:5055

# Or access from another machine on the network
open http://<server-ip>:5055
```

## Known Issues & TODOs

- [ ] 400K single HTML file is unwieldy — split into per-tab modules with a bundler
- [ ] No authentication — anyone on the network can access all controls
- [ ] No mobile/responsive layout
- [ ] Tabulator instances leak memory on tab switch (grids not destroyed)
- [ ] Some tabs poll on fixed intervals even when not visible — should pause when hidden
- [ ] Phone Agent WebRTC viewer does not clean up peer connections on tab switch
- [ ] Chart.js instances not destroyed before re-creation (memory leak on refresh)
