# Skill System — Feature Summary

## What It Does

Formal abstraction for Android automation. A Skill is a reusable, shareable package of Actions (atomic ADB operations with pre/post-condition validation and retry logic) and Workflows (composed action sequences that stop on first failure) for a specific app. Each skill includes YAML metadata, UI element definitions with fallback locator chains, and a directory structure that can be loaded dynamically by the server and executed via the job scheduler.

## Skill Kinds: Hard vs Soft

Every skill declares a `kind` in `skill.yaml` (absent ⇒ `hard`, so existing skills are unaffected):

- **HARD skill** — deterministic, zero-LLM replay. Has `workflows/recorded.json` (a flat step list) run by `RecordedWorkflow`/`RecordedStepAction`, or coded `Action`/`Workflow` classes. This is the classic skill above. Recorded steps support `launch`, `tap` (by `x,y`, `element_idx`, or a `text`/`resource_id`/`content_desc` locator that re-finds the element each run), `type`, `key`, `back`, `home`, `swipe`, `long_press`, `open_url`, `launch_intent`, and `wait`.
- **SOFT skill** — LLM-facing guidance, not replay. Has a `guidance.md` (markdown "what to watch out for") and **no steps**. It is surfaced to an agent **on demand**: `list_skills` advertises `kind` + `guidance_available`; calling `run_skill`/`run_workflow` on a soft skill returns its guidance text (no device execution). Soft guidance is never auto-injected into the prompt.

Both kinds share the same `skill.yaml` metadata (`app_package`, `platforms`, `popup_detectors`) and both flow through the same **compatibility matrix** (`SkillRun`/`SkillCompat`, now carrying `kind`). A soft skill's `--verify` is a **smoke check** (guidance present + target app installed on the device), so the tested/untested matrix stays meaningful for both.

Writers: `create_recorded_skill(kind="hard", ...)` and `create_soft_skill(...)` in `services/skill_creation.py`.

## Creating Skills from a Chat

An agent chat's action trace can be crystallized into a skill mid-conversation — the agent (or the user) says *"summarize what we did into a skill"*:

- **Agent tools** `draft_skill` (distils the session's tool-call trace into draft recorded steps — correct coords/args, noise like screenshots/OCR dropped) and `save_skill` (`kind="hard"` commits the reviewed steps; `kind="soft"` stores guidance). Available on every provider (native + on-device in the chat loop; `claude-code` via the MCP tools of the same name).
- **REST**: `POST /api/skills/draft-from-chat {conversation_id}` (preview, no write) and `POST /api/skills/save-from-chat {conversation_id, kind, name, ...}` — power the "Save as skill" button in the chat UI.

The distiller lives in `skills/trace_to_steps.py`; the orchestration in `services/skills_from_chat.py`. The flow is **draft → review → commit**: the distiller guarantees correct captured values, and the LLM/user prunes, renames, parameterizes (`{placeholder}`), or upgrades brittle coordinate taps to locator taps before saving.

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
├── skill.yaml           # metadata: name, version, platforms, packages/bundle ids, exports
├── elements.yaml        # Android UI elements with fallback locator chains
├── elements_ios.yaml    # optional iOS UI elements for the same named locators
├── __init__.py          # load() function — registers all actions + workflows
├── actions/
│   ├── __init__.py      # re-exports all action classes
│   └── core.py          # OpenApp, NavigateToProfile, TapSearch, TypeAndSearch, DismissPopup
└── workflows/
    ├── __init__.py
    ├── upload_video.py
    └── publish_draft.py
```

## Base Classes (skills/base.py)

| Class | Key Fields / Methods |
|-------|---------------------|
| `ActionResult` | `success: bool`, `data: dict`, `error: str`, `duration_ms: float`. Truthy = success. |
| `Element` | Locator chain: `content_desc → text → resource_id → class_name → (x, y)`. `find(device, xml) → (cx, cy)` |
| `Action` (abstract) | `precondition()`, `execute() → ActionResult` (must implement), `postcondition()`, `rollback()`. `run()` orchestrates with retry (max_retries=2, retry_delay=1.0s). |
| `Workflow` | `steps() → list[Action]` (override). `run()` executes all steps, stops on first failure. |
| `Skill` | Loads `skill.yaml`, `elements.yaml`, and `elements_ios.yaml` when needed. `register_action/workflow()`, `get_action/workflow(name, device)`, `list_actions/workflows()`. Properties: `name`, `app_package`, `android_package`, `ios_bundle_id`, `platforms`, `version`. |

## Platform Metadata

Skills can declare platform compatibility explicitly:

```yaml
platforms:
  - android
app_package: com.zhiliaoapp.musically
android_package: com.zhiliaoapp.musically
ios_bundle_id: com.google.chrome.ios
```

Legacy skills without `platforms` are treated as Android skills unless they
declare `ios_bundle_id`. REST, MCP, scheduler jobs, and direct skill runner
execution reject unsupported device refs with a stable `unsupported_platform`
error before starting device automation.

## TikTok Actions (13)

| Action | File | Description | Has Postcondition |
|--------|------|-------------|-------------------|
| `open_app` | core.py | Force-stop + relaunch TikTok | Yes (checks TIKTOK_PKG in dumpsys) |
| `navigate_to_profile` | core.py | Tap Profile tab in bottom nav | Yes (checks followers/Following in XML) |
| `tap_search` | core.py | Open search screen | Yes (checks search box RID) |
| `type_and_search` | core.py | Type query + press Enter | No |
| `dismiss_popup` | core.py | Dismiss known TikTok popups | No |

## TikTok Workflows (2)

| Workflow | File | Wraps Script |
|----------|------|-------------|
| `upload_video` | upload_video.py | `bots/tiktok/upload.py` (43-step upload flow) |
| `publish_draft` | publish_draft.py | `bots/tiktok/upload.py --publish-draft` |

## Files

| File | Purpose |
|------|---------|
| `gitd/skills/base.py` | Base classes: Skill, Action, Workflow, Element, ActionResult (262 lines) |
| `gitd/skills/tiktok/` | TikTok skill (5 actions, 2 workflows, 41 elements) |
| `gitd/skills/tiktok/skill.yaml` | Metadata: name, version, app_package, exports |
| `gitd/skills/tiktok/elements.yaml` | 41 UI elements with fallback locator chains |
| `gitd/skills/tiktok/actions/core.py` | 5 core actions (open, navigate, search, dismiss) |
| `gitd/skills/tiktok/workflows/` | 2 workflow files (upload_video, publish_draft) |
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
print(skill.list_workflows())  # ['upload_video', 'publish_draft']

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
- [ ] Most TikTok actions lack postconditions (no verification after tap)
- [ ] Workflows wrap existing bot scripts (subprocess) rather than composing Actions directly
- [ ] No parameterized workflows (params passed via kwargs, not validated against schema)
- [ ] Element fallback to class_name uses `find_bounds(resource_id=class_name)` which is incorrect
- [ ] No skill testing framework (run actions with assertions in CI)
