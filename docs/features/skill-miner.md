# Skill Miner — Feature Summary

## What It Does

BFS/DFS exploration of any Android app's UI. Launches an app, discovers screens by tapping every interactive element, records state transitions, captures screenshots, and builds a state graph. Results are browsable in the dashboard.

## Current State

**Working:**
- CLI tool (`gitd/skills/auto_creator.py`)
- Dashboard tab (🔍 Skill Miner)
- 6 API endpoints
- Searchable package dropdown (130+ installed apps)
- Previous explorations browser
- 3 completed explorations: TikTok, TikTok (deep), Settings

**Needs work:**
- State graph visualization (currently a table, could be mermaid/d3)
- Exploration tends to get stuck on dynamic content (FYP videos change state hashes)
- Back-navigation drift detection could be smarter
- No LLM skill generation from state graph yet (Phase 5 step 3 from roadmap)

## Architecture

```
User clicks "Start Exploration"
        │
        ▼
POST /api/explorer/start
        │
        ▼
Enqueues job_type='app_explore' to job_queue
        │
        ▼
Scheduler picks up → spawns auto_creator.py as subprocess
        │
        ▼
auto_creator.py BFS loop:
  1. Dump XML → extract interactive elements
  2. Screenshot current state
  3. Hash XML structure → check if new state
  4. For each clickable element:
     a. Tap element
     b. Wait for settle (1.5s default)
     c. Dump new XML → hash → new state?
     d. If new: record transition, add to queue
     e. Press Back to return
  5. Write progress.json after each discovery
  6. Write state_graph.json on completion
        │
        ▼
Dashboard polls GET /api/explorer/status every 2s
Shows live progress bar + scrolling log
        │
        ▼
On completion: state browser with screenshots + element lists
```

## Files

| File | Purpose |
|------|---------|
| `gitd/skills/auto_creator.py` | Core BFS explorer engine |
| `gitd/server.py` | API endpoints (search for `explorer`) |
| `gitd/static/dashboard.html` | Dashboard tab (search for `explorer`) |
| `data/skill.miner/<name>/` | Output directory per exploration |
| `data/skill.miner/<name>/state_graph.json` | Full state graph with elements + transitions |
| `data/skill.miner/<name>/progress.json` | Live progress (deleted after completion) |
| `data/skill.miner/<name>/screenshots/` | PNG screenshots per state |
| `data/skill.miner/<name>/xml_dumps/` | Raw XML per state |
| `docs/TASK_APP_EXPLORER_TAB.md` | Original task spec |

## API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/explorer/start` | Start exploration (enqueues to job queue) |
| POST | `/api/explorer/stop` | Kill running exploration |
| GET | `/api/explorer/status` | Poll progress (states, transitions, log) |
| GET | `/api/explorer/runs` | List all previous explorations |
| GET | `/api/explorer/run/<name>` | Get full state graph for a run |
| GET | `/api/explorer/screenshot/<name>/<state_id>` | Serve state screenshot |
| DELETE | `/api/explorer/delete/<name>` | Delete an exploration |
| GET | `/api/phone/packages/<device>` | List installed apps (for dropdown) |

## auto_creator.py CLI

```bash
python3 -m gitd.skills.auto_creator \
    --package com.zhiliaoapp.musically \
    --device YOUR_DEVICE_SERIAL \
    --max-depth 3 \
    --max-states 20 \
    --settle 1.5 \
    --output data/skill.miner/tiktok_custom
```

| Flag | Default | Description |
|------|---------|-------------|
| `--package` | required | Android package name |
| `--device` | required | ADB device serial |
| `--max-depth` | 3 | Max BFS depth |
| `--max-states` | 20 | Stop after N unique states |
| `--settle` | 1.5 | Seconds to wait after each tap |
| `--output` | auto | Output directory |

## State Graph JSON Format

```json
{
  "package": "com.zhiliaoapp.musically",
  "total_states": 4,
  "total_transitions": 3,
  "states": {
    "a1b2c3": {
      "state_id": "a1b2c3",
      "screenshot_path": "screenshots/a1b2c3.png",
      "xml_path": "xml_dumps/a1b2c3.xml",
      "activity": "com.ss.android.ugc.aweme.main.MainActivity",
      "depth": 0,
      "elements": [
        {"idx": 1, "text": "Home", "class": "TextView", "clickable": true, "bounds": {...}},
        ...
      ],
      "transitions": {
        "5": "d4e5f6"  // tapping element #5 leads to state d4e5f6
      }
    },
    ...
  }
}
```

## Dashboard UI Sections

1. **Launch Panel** — package dropdown (searchable, 130+ apps), device selector, depth/states/settle params, start/stop buttons
2. **Live Progress** — progress bar, states/transitions/depth counters, scrolling timestamped log
3. **State Graph** — table showing State → Element → Target State transitions
4. **State Browser** — clickable state tabs, each showing: screenshot, activity, element count, element list with transition links
5. **Previous Explorations** — table of all runs with view/delete/re-explore buttons

## Known Issues & TODOs

- [ ] Dynamic apps (TikTok FYP) generate different XML hashes for same logical screen — needs content-invariant hashing
- [ ] Back-navigation sometimes lands on wrong screen (drift) — double-back recovery exists but not perfect
- [ ] Portal XML (via Droidrun Portal) doesn't set `clickable=true` — heuristic fallback works but less precise
- [ ] State graph visualization is a plain table — upgrade to mermaid.js or d3 force graph
- [ ] LLM skill generation from state graph (feed graph + screenshots → LLM generates skill.yaml + actions)
- [ ] No "resume exploration" — always starts fresh
- [ ] Package dropdown should reload when switching devices
