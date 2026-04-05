# Skill System — Feature Summary

## What It Does

Formal abstraction for Android automation. A Skill is a reusable, shareable package of Actions (atomic ADB operations with pre/post-condition validation and retry logic) and Workflows (composed action sequences that stop on first failure) for a specific app. Each skill includes YAML metadata, UI element definitions with fallback locator chains, and a directory structure that can be loaded dynamically by the server and executed via the job scheduler.

## Current State

**Working:**
- Base classes: `Action`, `Workflow`, `Skill`, `Element`, `ActionResult` in `skills/base.py` (262 lines)
- TikTok skill: 13 actions + 3 workflows + 41 UI elements (fully implemented)
- Base skill: 9 shared actions (any app — tap, swipe, type, wait, launch, screenshot, etc.)
- Instagram skill: skeleton only (skill.yaml exists, no implemented actions/workflows)
- Element fallback chain: `content_desc → text → resource_id → class_name → absolute coords`
- All skills loadable via Python API and executable via `_run_skill.py` subprocess
- Integration with Skill Hub (API + dashboard) and job scheduler

## Architecture

```
Skill (skill.yaml + elements.yaml)
 ├── Elements (elements.yaml)
 │   └── Element: name → {content_desc, text, resource_id, class_name, x, y}
 │       └── find(device, xml) → (cx, cy) | None  (tries locators in priority order)
 │
 ├── Actions (actions/*.py) — atomic operations
 │   ├── precondition()  — verify device is in expected state (default: True)
 │   ├── execute()       — perform ADB operation → ActionResult
 │   ├── postcondition() — verify action succeeded (default: True)
 │   ├── rollback()      — undo on failure (optional, default: no-op)
 │   └── run()           — orchestrator: pre → execute (retry up to max_retries) → post
 │
 └── Workflows (workflows/*.py) — composed sequences
     └── steps() → [Action, Action, ...]
         └── run() — execute all steps in order, stop on first failure
```

### Execution Flow (Action.run)

```
precondition() → False? → return failure immediately
        │ True
        ▼
execute() → loop up to max_retries (default 2):
    │  success + postcondition() True? → return success
    │  failure? → rollback(), retry after retry_delay (default 1.0s)
    ▼
All retries exhausted → return failure with last error
```

### Execution Flow (Workflow.run)

```
for action in steps():
    result = action.run()
    if not result:
        return failure (with completed_steps count + failed_step name)
return success (with total completed_steps)
```

## Skill Directory Structure

```
skills/tiktok/
├── skill.yaml           # metadata: name, version, app_package, description, exports
├── elements.yaml        # 41 UI elements with fallback locator chains
├── __init__.py          # load() function — registers all actions + workflows
├── actions/
│   ├── __init__.py      # re-exports all action classes
│   ├── core.py          # OpenApp, NavigateToProfile, TapSearch, TypeAndSearch, DismissPopup
│   └── engagement.py    # LikePost, CommentOnPost, FollowUser, ScrollFeed, TapUser, TapMessageButton, TypeMessage, TapSend
└── workflows/
    ├── __init__.py
    ├── upload_video.py
    ├── crawl_users.py
    └── publish_draft.py
```

## Base Classes (skills/base.py)

| Class | Key Fields / Methods |
|-------|---------------------|
| `ActionResult` | `success: bool`, `data: dict`, `error: str`, `duration_ms: float`. Truthy = success. |
| `Element` | Locator chain: `content_desc → text → resource_id → class_name → (x, y)`. `find(device, xml) → (cx, cy)` |
| `Action` (abstract) | `precondition()`, `execute() → ActionResult` (must implement), `postcondition()`, `rollback()`. `run()` orchestrates with retry (max_retries=2, retry_delay=1.0s). |
| `Workflow` | `steps() → list[Action]` (override). `run()` executes all steps, stops on first failure. |
| `Skill` | Loads `skill.yaml` + `elements.yaml`. `register_action/workflow()`, `get_action/workflow(name, device)`, `list_actions/workflows()`. Properties: `name`, `app_package`, `version`. |

## TikTok Actions (13)

| Action | File | Description | Has Postcondition |
|--------|------|-------------|-------------------|
| `open_app` | core.py | Force-stop + relaunch TikTok | Yes (checks TIKTOK_PKG in dumpsys) |
| `navigate_to_profile` | core.py | Tap Profile tab in bottom nav | Yes (checks followers/Following in XML) |
| `tap_search` | core.py | Open search screen | Yes (checks search box RID) |
| `type_and_search` | core.py | Type query + press Enter | No |
| `dismiss_popup` | core.py | Dismiss known TikTok popups | No |
| `like_post` | engagement.py | Double-tap center to like | No |
| `comment_on_post` | engagement.py | Open comments → type → send | No |
| `follow_user` | engagement.py | Tap Follow button | No |
| `scroll_feed` | engagement.py | Swipe up to next video | No |
| `tap_user` | engagement.py | Tap user row in search results | No |
| `tap_message_button` | engagement.py | Tap Message on profile | No |
| `type_message` | engagement.py | Type text in DM input | No |
| `tap_send` | engagement.py | Send the DM | No |

## TikTok Workflows (3)

| Workflow | File | Wraps Script |
|----------|------|-------------|
| `upload_video` | upload_video.py | `bots/tiktok/upload.py` (43-step upload flow) |
| `crawl_users` | crawl_users.py | `bots/tiktok/scraper.py --tab users` |
| `publish_draft` | publish_draft.py | `bots/tiktok/upload.py --publish-draft` |

## Files

| File | Purpose |
|------|---------|
| `gitd/skills/base.py` | Base classes: Skill, Action, Workflow, Element, ActionResult (262 lines) |
| `gitd/skills/tiktok/` | TikTok skill (13 actions, 3 workflows, 41 elements) |
| `gitd/skills/tiktok/skill.yaml` | Metadata: name, version, app_package, exports |
| `gitd/skills/tiktok/elements.yaml` | 41 UI elements with fallback locator chains |
| `gitd/skills/tiktok/actions/core.py` | 5 core actions (open, navigate, search, dismiss) |
| `gitd/skills/tiktok/actions/engagement.py` | 8 engagement actions (like, comment, follow, scroll, DM) |
| `gitd/skills/tiktok/workflows/` | 3 workflow files |
| `gitd/skills/_base/` | Base skill (9 shared actions for any app) |
| `gitd/skills/_base/skill.yaml` | Base skill metadata |
| `gitd/skills/instagram/` | Instagram skeleton (skill.yaml only) |
| `gitd/skills/_run_skill.py` | CLI runner for job queue execution |

## How to Use

```python
# Load a skill
from gitd.skills.tiktok import load
skill = load()
print(skill.name)              # 'tiktok'
print(skill.app_package)       # 'com.zhiliaoapp.musically'
print(skill.list_actions())    # ['open_app', 'navigate_to_profile', ...]
print(skill.list_workflows())  # ['upload_video', 'crawl_users', 'publish_draft']

# Run an action
from gitd.bots.common.adb import Device
dev = Device('YOUR_DEVICE_SERIAL')
action = skill.get_action('tap_search', dev)
result = action.run()
print(result.success, result.duration_ms)

# Run a workflow
wf = skill.get_workflow('upload_video', dev, video_path='/tmp/video.mp4')
result = wf.run()
print(result.data)  # {'completed_steps': 5}

# CLI execution (used by job scheduler)
# python3 skills/_run_skill.py --skill tiktok --workflow upload_video --device YOUR_DEVICE_SERIAL --params '{"video_path": "/tmp/video.mp4"}'
```

## Known Issues & TODOs

- [ ] More app skills needed (Twitter, WhatsApp, YouTube, Settings)
- [ ] LLM-generated skills from Auto Explorer state graphs
- [ ] Skill versioning and dependency management
- [ ] Only tiktok and _base skills have runtime loading — need generic plugin loader
- [ ] Most TikTok engagement actions lack postconditions (no verification after tap)
- [ ] Workflows wrap existing bot scripts (subprocess) rather than composing Actions directly
- [ ] No parameterized workflows (params passed via kwargs, not validated against schema)
- [ ] Element fallback to class_name uses `find_bounds(resource_id=class_name)` which is incorrect
- [ ] No skill testing framework (run actions with assertions in CI)
