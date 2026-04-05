---
title: "🧩 Skills Overview"
description: What Skills, Actions, Workflows, and Elements are — the core abstractions for Android automation.
---

The skill system is the formal abstraction layer for Android automation. A Skill packages everything needed to automate a specific app into a reusable, shareable unit.

## Core Concepts

### Elements

UI locators defined in `elements.yaml`. Each element has a fallback chain of locator strategies tried in order:

```
content_desc -> text -> resource_id -> class_name -> absolute coordinates (x, y)
```

If the first locator fails (e.g., a resource_id changed after an app update), the system falls back to the next one. This makes skills resilient to minor app updates.

### Actions

Atomic operations that perform a single ADB interaction. Each action has:

- **precondition()** -- verify the device is in the expected state before executing
- **execute()** -- perform the ADB operation (tap, swipe, type, etc.)
- **postcondition()** -- verify the action succeeded
- **rollback()** -- undo the action on failure (optional)
- **run()** -- orchestrates: precondition -> execute (with retry) -> postcondition

Actions retry up to `max_retries` times (default 2) with `retry_delay` (default 1.0s) between attempts.

### Workflows

Composed sequences of actions that execute in order. If any action fails, the workflow stops immediately and reports which step failed.

### Skills

The top-level container. A skill loads from a directory containing `skill.yaml` (metadata), `elements.yaml` (UI locators), and Python files for actions and workflows.

## Architecture

```
Skill (skill.yaml + elements.yaml)
  |-- Elements (elements.yaml)
  |     \-- Element: name -> {content_desc, text, resource_id, class_name, x, y}
  |         \-- find(device, xml) -> (cx, cy) | None
  |
  |-- Actions (actions/*.py)
  |     |-- precondition()  -> verify device state
  |     |-- execute()       -> perform ADB operation -> ActionResult
  |     |-- postcondition() -> verify success
  |     \-- rollback()      -> undo on failure
  |
  \-- Workflows (workflows/*.py)
      \-- steps() -> [Action, Action, ...]
          \-- run() -> execute all, stop on first failure
```

## Installed Skills

| Skill | App | Actions | Workflows | Elements | Status |
|-------|-----|---------|-----------|----------|--------|
| `tiktok` | TikTok (v44.3.3) | 13 | 9 | 41 | Fully implemented |
| `_base` | Any app | 9 | 0 | 0 | Shared utilities |
| `instagram` | Instagram | 0 | 0 | 0 | Skeleton only |

### TikTok Actions

| Action | Description |
|--------|-------------|
| `open_app` | Force-stop + relaunch TikTok |
| `navigate_to_profile` | Tap Profile tab in bottom nav |
| `tap_search` | Open search screen |
| `type_and_search` | Type query + press Enter |
| `dismiss_popup` | Dismiss known TikTok popups |
| `like_post` | Double-tap center to like |
| `comment_on_post` | Open comments, type, send |
| `follow_user` | Tap Follow button |
| `scroll_feed` | Swipe up to next video |
| `tap_user` | Tap user row in search results |
| `tap_message_button` | Tap Message on profile |
| `type_message` | Type text in DM input |
| `tap_send` | Send the DM |

### TikTok Workflows

| Workflow | Description |
|----------|-------------|
| `upload_video` | 43-step video upload flow |
| `crawl_users` | Search users tab, scrape profiles |
| `publish_draft` | Find and publish a saved draft |

### Base Actions

The `_base` skill provides 9 shared actions usable by any app: tap, swipe, type, wait, back, home, launch app, take screenshot, and press enter.

## Quick Usage

```python
from gitd.skills.tiktok import load
from gitd.bots.common.adb import Device

dev = Device()
skill = load()

# Inspect
print(skill.name)              # 'tiktok'
print(skill.app_package)       # 'com.zhiliaoapp.musically'
print(skill.list_actions())    # ['open_app', 'navigate_to_profile', ...]
print(skill.list_workflows())  # ['upload_video', 'crawl_users', 'publish_draft']

# Run an action
action = skill.get_action("open_app", dev)
result = action.run()
print(result.success, result.duration_ms)

# Run a workflow
wf = skill.get_workflow("upload_video", dev, video_path="/tmp/video.mp4")
result = wf.run()
```

## Next Steps

- [Using Skills](/skills/using-skills/) -- install, browse, run from Python/dashboard/API
- [Creating Skills](/skills/creating-skills/) -- build a skill for a new app
- [Elements](/skills/elements/) -- deep dive into UI locator chains
