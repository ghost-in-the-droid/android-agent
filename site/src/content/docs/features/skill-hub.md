---
title: "Skill Hub"
description: Dashboard tab and REST API for browsing, running, exporting, and managing installed automation skills.
---

The Skill Hub is the central interface for managing automation skills. Browse installed skills, run workflows on any connected device, export/import skill packages, and create new skills from recordings.

## What You Can Do

- **Browse** installed skills with action/workflow counts and element definitions
- **Run** workflows or individual actions on any connected device via the job queue
- **Export** skills as shareable ZIP packages
- **Import** skills from ZIP files
- **Create** new skills from recorded macro sessions
- **Install** skills from the community registry or GitHub repos

## REST API

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/skills` | List all installed skills with counts |
| GET | `/api/skills/{name}` | Full skill detail (metadata, actions, workflows, elements) |
| POST | `/api/skills/{name}/run` | Run workflow via job queue |
| POST | `/api/skills/{name}/run-action` | Run single action via job queue |
| POST | `/api/skills/{name}/verify` | Run synchronously and verify result |
| GET | `/api/skills/export/{name}` | Download skill as ZIP |
| POST | `/api/skills/install` | Install from registry or GitHub URL |
| POST | `/api/skills/create-from-recording` | Create skill from recorded steps |
| DELETE | `/api/skills/{name}` | Delete skill (protects built-ins) |
| PUT | `/api/skills/{name}/update` | Update recorded skill steps/metadata |
| GET | `/api/skills/registry` | Browse community registry |
| GET | `/api/skills/community` | Browse community-contributed skills |
| GET | `/api/skills/compat` | Skill compatibility matrix per device |
| GET | `/api/skills/runs` | Skill execution history |

## CLI

```bash
# List installed skills
android-agent skill list

# Install from registry
android-agent skill install whatsapp

# Install from GitHub
android-agent skill install https://github.com/user/my-skill

# Search registry
android-agent skill search "messaging"

# Validate a skill directory
android-agent skill validate ./my-skill/

# Update a skill
android-agent skill update tiktok

# Remove a skill
android-agent skill remove my-skill
```

## Usage Examples

```bash
# List all installed skills
curl -s http://localhost:5055/api/skills | python3 -m json.tool

# Run a workflow
curl -X POST http://localhost:5055/api/skills/tiktok/run \
  -H "Content-Type: application/json" \
  -d '{"workflow": "upload_video", "params": {"video_path": "/sdcard/video.mp4"}, "device": "SERIAL"}'

# Run a single action
curl -X POST http://localhost:5055/api/skills/tiktok/run-action \
  -H "Content-Type: application/json" \
  -d '{"action": "open_app", "params": {}, "device": "SERIAL"}'

# Export skill as ZIP
curl http://localhost:5055/api/skills/export/tiktok -o tiktok_skill.zip

# Install from registry
curl -X POST http://localhost:5055/api/skills/install \
  -H "Content-Type: application/json" \
  -d '{"name": "whatsapp"}'
```

## How Skills Load

Skills are loaded dynamically from the `gitd/skills/` directory. Each subdirectory with a `skill.yaml` is a skill.

```
skills/
  _base/            # Shared actions for any app (tap, swipe, type, wait, launch)
  tiktok/           # Full Python skill (actions + workflows + elements)
  send_gmail_email/ # Recorded skill (JSON step list)
  play_store/       # Play Store automation
```

## Dashboard UI

1. **Card Grid** -- one card per skill showing name, version, app, action/workflow counts
2. **Detail View** -- click to expand: actions, workflows, elements, metadata
3. **Run Controls** -- device selector, workflow/action picker, params, Run button
4. **Compat Matrix** -- color-coded per device: ok / partial / fail / untested
5. **Export/Import** -- download as ZIP or upload from file

## Registry

The skill registry lives in [`registry/`](https://github.com/ghost-in-the-droid/android-agent/tree/main/registry) in the main repo. The Browse tab in the dashboard fetches this registry and shows installable skills with one-click install.

## Related

- [Skill System](/features/skill-system/) -- how skills are structured (Actions, Workflows, Elements)
- [Skill Creator](/features/skill-creator/) -- AI-assisted skill creation with macro recording
- [App Explorer](/features/app-explorer/) -- discover app UI structure for building skills
- [MCP Server](/features/mcp-server/) -- expose skills as tools for LLM agents
- [Scheduler](/features/scheduler/) -- job queue that executes skill runs
