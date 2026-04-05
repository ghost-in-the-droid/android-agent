---
title: "🧠 Skill System"
description: Action, Workflow, Skill, and Element base classes — execution flow, retry logic, and the TikTok reference implementation.
---

The skill system provides formal abstractions for Android automation. It is defined in `gitd/skills/base.py` (262 lines) and includes five core classes.

## Base Classes

### ActionResult

Return value from action execution:

```python
@dataclass
class ActionResult:
    success: bool
    data: dict = field(default_factory=dict)
    error: str = ""
    duration_ms: float = 0.0
```

`ActionResult` is truthy when `success=True`, so you can use it in conditionals: `if result: ...`

### Element

UI locator with fallback chain:

```python
class Element:
    # Locator fields (tried in this order):
    content_desc: str
    text: str
    resource_id: str
    class_name: str
    x: int  # absolute fallback
    y: int

    def find(self, device, xml) -> tuple[int, int] | None:
        """Try each locator in priority order, return center coords."""
```

### Action (Abstract)

Atomic operation with pre/post validation:

```python
class Action:
    name: str
    description: str
    max_retries: int = 2
    retry_delay: float = 1.0

    def precondition(self, dev, xml) -> bool: ...   # Override to validate state
    def execute(self, dev, **kwargs) -> ActionResult: ...  # Must implement
    def postcondition(self, dev, xml) -> bool: ...   # Override to verify success
    def rollback(self, dev) -> None: ...             # Override to undo on failure
    def run(self, dev, **kwargs) -> ActionResult: ...  # Orchestrator
```

### Workflow

Composed action sequence:

```python
class Workflow:
    name: str
    description: str
    params: dict

    def steps(self) -> list: ...   # Override: return [(action_name, params), ...]
    def run(self, dev) -> ActionResult: ...  # Execute all steps in order
```

### Skill

Top-level container that loads from YAML:

```python
class Skill:
    name: str
    app_package: str
    version: str
    elements: dict[str, Element]

    def register_action(self, action_cls): ...
    def register_workflow(self, workflow_cls): ...
    def get_action(self, name, device) -> Action: ...
    def get_workflow(self, name, device, **params) -> Workflow: ...
    def list_actions(self) -> list[str]: ...
    def list_workflows(self) -> list[str]: ...

    @classmethod
    def from_yaml(cls, path) -> Skill: ...  # Load skill.yaml + elements.yaml
```

## Execution Flow

### Action.run()

```
precondition() -> False? -> return failure immediately
      | True
      v
execute() -> loop up to max_retries (default 2):
    |  success + postcondition() True? -> return success
    |  failure? -> rollback(), retry after retry_delay (default 1.0s)
    v
All retries exhausted -> return failure with last error
```

### Workflow.run()

```
for action in steps():
    result = action.run()
    if not result:
        return failure (completed_steps count + failed_step name)
return success (total completed_steps)
```

## Skill Directory Structure

```
skills/tiktok/
  skill.yaml           # metadata: name, version, app_package, description
  elements.yaml        # 41 UI elements with fallback locator chains
  __init__.py          # load() function registers actions + workflows
  actions/
    __init__.py
    core.py            # OpenApp, NavigateToProfile, TapSearch, TypeAndSearch, DismissPopup
    engagement.py      # LikePost, CommentOnPost, FollowUser, ScrollFeed, TapUser, etc.
  workflows/
    __init__.py
    upload_video.py
    crawl_users.py
    publish_draft.py
```

## TikTok Skill Reference

### 13 Actions

| Action | File | Has Postcondition |
|--------|------|-------------------|
| `open_app` | core.py | Yes (checks TIKTOK_PKG in dumpsys) |
| `navigate_to_profile` | core.py | Yes (checks followers/Following) |
| `tap_search` | core.py | Yes (checks search box RID) |
| `type_and_search` | core.py | No |
| `dismiss_popup` | core.py | No |
| `like_post` | engagement.py | No |
| `comment_on_post` | engagement.py | No |
| `follow_user` | engagement.py | No |
| `scroll_feed` | engagement.py | No |
| `tap_user` | engagement.py | No |
| `tap_message_button` | engagement.py | No |
| `type_message` | engagement.py | No |
| `tap_send` | engagement.py | No |

### 3 Workflows

| Workflow | Wraps |
|----------|-------|
| `upload_video` | `bots/tiktok/upload.py` (43-step flow) |
| `crawl_users` | `bots/tiktok/scraper.py --tab users` |
| `publish_draft` | `bots/tiktok/upload.py --publish-draft` |

### Base Skill (9 shared actions)

The `_base` skill provides generic actions usable by any app: tap_element, swipe_direction, type_text, wait, back, home, launch_app, take_screenshot, and press_enter.

## Subprocess Execution

When skills are executed via the scheduler or API, they run as subprocesses:

```bash
python3 skills/_run_skill.py \
  --skill tiktok \
  --workflow upload_video \
  --device YOUR_DEVICE_SERIAL \
  --params '{"video_path": "/tmp/video.mp4"}'
```

This keeps the server responsive and provides process isolation.

## Files

| File | Lines | Purpose |
|------|-------|---------|
| `skills/base.py` | 262 | ActionResult, Element, Action, Workflow, Skill |
| `skills/tiktok/` | -- | 13 actions + 3 workflows + 41 elements |
| `skills/_base/` | -- | 9 shared actions |
| `skills/instagram/` | -- | Skeleton (skill.yaml only) |
| `skills/_run_skill.py` | -- | CLI runner for job queue |

## Related

- [Skills Overview](/skills/overview/) -- concepts and quick start
- [Elements](/skills/elements/) -- locator chains deep dive
- [API: Skill Classes](/api/skill-classes/) -- full class reference
