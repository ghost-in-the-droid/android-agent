---
title: "⚡ Using Skills"
description: Browse, install, run, and export skills from Python, the dashboard, and the REST API.
---

Skills can be used from Python code, the REST API, or the dashboard GUI. All three methods ultimately execute the same underlying Action and Workflow classes.

## From Python

### Load a Skill

```python
from gitd.skills.tiktok import load
skill = load()

print(skill.name)              # 'tiktok'
print(skill.app_package)       # 'com.zhiliaoapp.musically'
print(len(skill.elements))     # 41
print(skill.list_actions())    # ['open_app', 'navigate_to_profile', ...]
print(skill.list_workflows())  # ['upload_video', 'crawl_users', 'publish_draft']
```

### Run an Action

```python
from gitd.bots.common.adb import Device

dev = Device()
action = skill.get_action("tap_search", dev)
result = action.run()

print(result.success)       # True/False
print(result.duration_ms)   # execution time
print(result.error)         # error message if failed
print(result.data)          # action-specific return data
```

Actions follow the pre/execute/post pattern:
1. `precondition()` verifies the device is in the right state
2. `execute()` performs the ADB operation (retried up to 2 times)
3. `postcondition()` verifies the action succeeded

### Run a Workflow

```python
wf = skill.get_workflow("upload_video", dev, video_path="/tmp/video.mp4")
result = wf.run()

print(result.success)
print(result.data)  # {'completed_steps': 5}
```

Workflows execute each action step in sequence. If any step fails, the workflow stops and reports the failure.

## From the REST API

### List Skills

```bash
curl -s http://localhost:5055/api/skills | python3 -m json.tool
```

### Get Skill Detail

```bash
curl -s http://localhost:5055/api/skills/tiktok | python3 -m json.tool
```

Returns full metadata, action list with descriptions, workflow list, and element definitions.

### List Actions and Workflows

```bash
curl -s http://localhost:5055/api/skills/tiktok/actions | python3 -m json.tool
curl -s http://localhost:5055/api/skills/tiktok/workflows | python3 -m json.tool
```

### Run a Workflow

```bash
curl -X POST http://localhost:5055/api/skills/tiktok/run \
  -H "Content-Type: application/json" \
  -d '{
    "workflow": "upload_video",
    "params": {"video_path": "/tmp/video.mp4"},
    "device": "YOUR_DEVICE_SERIAL"
  }'
```

This enqueues a `skill_workflow` job in the scheduler queue. The response includes the job queue ID for monitoring.

### Run a Single Action

```bash
curl -X POST http://localhost:5055/api/skills/tiktok/run-action \
  -H "Content-Type: application/json" \
  -d '{
    "action": "tap_search",
    "params": {},
    "device": "YOUR_DEVICE_SERIAL"
  }'
```

### Export a Skill as ZIP

```bash
curl http://localhost:5055/api/skills/export/tiktok -o tiktok_skill.zip
unzip -l tiktok_skill.zip
```

The ZIP contains the full skill directory: `skill.yaml`, `elements.yaml`, actions, and workflows.

### Import a Skill

```bash
curl -X POST http://localhost:5055/api/skills/import \
  -F "file=@whatsapp_skill.zip"
```

Uploads and installs the skill into the `skills/` directory.

## From the Dashboard

### Skill Hub Tab

Navigate to the **Skill Hub** tab in the dashboard at http://localhost:5055:

1. **Card Grid** -- one card per skill showing name, version, app package, and action/workflow counts
2. **Detail View** -- click a card to expand and see all actions, workflows, and elements
3. **Run Controls** -- select a device, pick a workflow or action, set parameters, and click Run
4. **Export** -- download any skill as a ZIP file
5. **Status** -- after running, the UI shows the job queue ID and links to the Scheduler tab

### Device Selection

All execution requires selecting a target device. The dropdown lists all connected phones (both physical and emulators). The selection persists in localStorage.

## Execution Flow

Whether you use Python, API, or dashboard, skill execution follows the same path:

```
User triggers run
    |
    v
POST /api/skills/<name>/run
    |
    v
enqueue_job(type='skill_workflow')
    |
    v
Scheduler picks up job (within 30s)
    |
    v
Spawns: python3 skills/_run_skill.py --skill tiktok --workflow upload_video ...
    |
    v
_run_skill.py loads skill, instantiates workflow with Device, calls run()
    |
    v
Result written to job log, status updated in DB
```

## CLI Execution

Skills can also be run directly via the subprocess runner:

```bash
python3 -m gitd.skills._run_skill \
  --skill tiktok \
  --workflow upload_video \
  --device YOUR_DEVICE_SERIAL \
  --params '{"video_path": "/tmp/video.mp4"}'
```

This is what the scheduler calls internally.

## Next Steps

- [Creating Skills](/skills/creating-skills/) -- build your own skill
- [Elements](/skills/elements/) -- understand UI locator chains
- [Publishing Skills](/skills/publishing/) -- share your skill with others
