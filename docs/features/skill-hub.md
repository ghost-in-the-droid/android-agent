# Skill Hub — Feature Summary

## What It Does

Dashboard tab and REST API for browsing, running, and sharing installed automation skills. The central interface for managing the skill library: see what skills are installed (with action/workflow counts and element definitions), run workflows or individual actions on any connected device via the job queue, and export/import skills as shareable ZIP packages. Skills are loaded dynamically from the `gitd/skills/` directory.

## Current State

**Working:**
- REST API: 10 endpoints for skill listing, detail, execution, creation, and export/import
- Dashboard tab: card grid with expandable detail views
- Workflow execution via job queue (respects per-phone scheduling and priority)
- Individual action execution via job queue
- Device selector dropdown (lists all connected phones)
- ZIP export (downloads full skill directory) and import (uploads + installs)
- Create-from-recording endpoint (generates skill directory from recorded steps)
- Dynamic skill loading from `skills/` directory (reads `skill.yaml` + `elements.yaml`)

**Installed skills:**
- `tiktok`: 13 actions + 3 workflows + 41 UI elements (fully implemented)
- `_base`: 9 shared actions (any app — tap, swipe, type, wait, launch, etc.)
- `instagram`: skeleton only (skill.yaml exists, no actions/workflows)

**Limitations:**
- Local only — no remote skill marketplace/registry
- No skill search/filter in the dashboard UI
- No skill ratings, reviews, or versioning
- Import only handles ZIP files (no Git-based skill install)
- Only tiktok and _base skills are loadable at runtime (hardcoded in server.py)

## Architecture

```
Dashboard (Skill Hub tab)
    │
    │  GET /api/skills → card grid
    │  GET /api/skills/<name> → detail view (actions, workflows, elements)
    ▼
Server loads skills:
    _load_all_skills() → scan skills/ directory → read skill.yaml per subdirectory
    load() function per skill → registers Action + Workflow classes
    │
    │  POST /api/skills/<name>/run → enqueue_job(job_type='skill_workflow')
    ▼
Job Queue → Scheduler picks up
    │
    │  _build_cmd() → python3 skills/_run_skill.py --skill <name> --workflow <wf> --device <serial>
    ▼
_run_skill.py subprocess:
    1. Load skill (imports Action/Workflow classes)
    2. Instantiate with Device + Elements
    3. Call workflow.run() or action.run()
    4. Print result, exit 0 (success) or 1 (failure)
```

## Files

| File | Purpose |
|------|---------|
| `gitd/server.py` | API endpoints (lines ~3663-4025): `_load_all_skills()`, skill CRUD, run, export |
| `gitd/skills/_run_skill.py` | Subprocess runner — loads skill, runs action/workflow, reports result |
| `gitd/skills/base.py` | Base classes: `Skill`, `Action`, `Workflow`, `Element`, `ActionResult` |
| `gitd/skills/tiktok/` | TikTok skill (skill.yaml, elements.yaml, actions/, workflows/) |
| `gitd/skills/_base/` | Base skill (shared actions for any app) |
| `gitd/skills/instagram/` | Instagram skeleton (skill.yaml only) |
| `gitd/static/dashboard.html` | Skill Hub tab UI (card grid, detail view, device selector) |

## API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/skills` | List all installed skills with action/workflow counts |
| GET | `/api/skills/<name>` | Full skill detail (metadata, actions, workflows, elements) |
| GET | `/api/skills/<name>/actions` | List actions with descriptions |
| GET | `/api/skills/<name>/workflows` | List workflows with descriptions |
| POST | `/api/skills/<name>/run` | Run workflow → enqueues `skill_workflow` to job queue |
| POST | `/api/skills/<name>/run-action` | Run single action → enqueues `skill_action` to job queue |
| GET | `/api/skills/export/<name>` | Download skill as ZIP (all files except `__pycache__`) |
| POST | `/api/skills/import` | Upload + install skill ZIP |
| POST | `/api/skills/create-from-recording` | Create skill from recorded steps (generates skill.yaml + workflow JSON) |

## How to Use

```bash
# List all installed skills
curl -s http://localhost:5055/api/skills | python3 -m json.tool

# Get skill detail
curl -s http://localhost:5055/api/skills/tiktok | python3 -m json.tool

# Run a workflow (enqueues to job queue)
curl -X POST http://localhost:5055/api/skills/tiktok/run \
  -H "Content-Type: application/json" \
  -d '{"workflow": "upload_video", "params": {"video_path": "/tmp/video.mp4"}, "device": "YOUR_DEVICE_SERIAL"}'

# Run a single action
curl -X POST http://localhost:5055/api/skills/tiktok/run-action \
  -H "Content-Type: application/json" \
  -d '{"action": "tap_search", "params": {}, "device": "YOUR_DEVICE_SERIAL"}'

# Export skill as ZIP
curl http://localhost:5055/api/skills/export/tiktok -o tiktok_skill.zip

# Create skill from recorded steps
curl -X POST http://localhost:5055/api/skills/create-from-recording \
  -H "Content-Type: application/json" \
  -d '{"name": "my_skill", "app_package": "com.example.app", "steps": [{"action": "tap", "params": {"x": 540, "y": 1200}}]}'

# Dashboard: http://localhost:5055 → Skill Hub tab
```

## Skill Loading Internals

```python
# _load_all_skills() scans the skills/ directory
for subdir in skills_dir.iterdir():
    if subdir.is_dir() and (subdir / 'skill.yaml').exists():
        meta = yaml.safe_load((subdir / 'skill.yaml').read_text())
        # Store in results dict keyed by directory name

# Runtime loading is hardcoded per skill name:
if name == 'tiktok':
    from gitd.skills.tiktok import load
elif name == '_base':
    from gitd.skills._base import load
# Instagram and custom skills fall through to metadata-only
```

## Dashboard UI

1. **Card Grid** — one card per skill showing name, version, app package, action/workflow counts
2. **Detail View** — click a card to expand: full metadata, action list with descriptions, workflow list, element definitions from elements.yaml
3. **Run Controls** — device selector dropdown, workflow/action selector, params input, Run button
4. **Export Button** — download skill as ZIP
5. **Status Feedback** — shows job queue ID after enqueuing, links to Scheduler tab for monitoring

## Known Issues & TODOs

- [ ] Remote skill marketplace (browse/publish/install from community registry)
- [ ] Skill search and filtering in the dashboard UI
- [ ] Only tiktok and _base skills are dynamically loadable — need generic plugin loader
- [ ] No skill versioning or dependency management
- [ ] Auto-update skills when app version changes (detect new RIDs)
- [ ] Import endpoint needs validation (malicious ZIP protection)
- [ ] No skill testing framework (run actions with assertions)
- [ ] Skill ratings, reviews, and usage statistics
