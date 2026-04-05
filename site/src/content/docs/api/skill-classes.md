---
title: "🧬 Skill Classes"
description: Full API reference for ActionResult, Element, Action, Workflow, and Skill classes from skills/base.py.
---

All skill system classes are defined in `gitd/skills/base.py` (262 lines).

## ActionResult

Return value from action execution.

```python
@dataclass
class ActionResult:
    success: bool
    data: dict = field(default_factory=dict)
    error: str = ""
    duration_ms: float = 0.0
```

**Truthiness:** `ActionResult` is truthy when `success=True`:

```python
result = action.run()
if result:
    print("Success:", result.data)
else:
    print("Failed:", result.error)
```

## Element

UI locator with fallback chain.

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `content_desc` | str | Accessibility content description (highest priority) |
| `text` | str | Visible text label |
| `resource_id` | str | Android resource ID |
| `class_name` | str | Widget class name |
| `x` | int | Absolute X coordinate (lowest priority) |
| `y` | int | Absolute Y coordinate |
| `description` | str | Human-readable description (not used for finding) |

### Methods

#### find(device, xml) -> tuple[int, int] | None

Try each locator in priority order, return center coordinates of the first match.

```python
element = skill.elements["search_icon"]
coords = element.find(dev, xml)
if coords:
    dev.tap(*coords)
```

Priority: `content_desc` -> `text` -> `resource_id` -> `class_name` -> `(x, y)`

## Action (Abstract Base Class)

Atomic operation with pre/post-condition validation and retry logic.

### Class Attributes

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | str | required | Action identifier |
| `description` | str | "" | Human-readable description |
| `max_retries` | int | 2 | Number of retry attempts |
| `retry_delay` | float | 1.0 | Seconds between retries |

### Methods

#### precondition(dev, xml) -> bool

Verify device is in expected state before executing. Override to add validation. Default returns True.

```python
def precondition(self, dev, xml):
    return dev.find_bounds(xml, resource_id="com.app:id/search") is not None
```

#### execute(dev, **kwargs) -> ActionResult

Perform the ADB operation. **Must be implemented** by subclasses.

```python
def execute(self, dev, text="Hello", **kwargs):
    dev.type_text(text)
    return ActionResult(success=True, data={"typed": text})
```

#### postcondition(dev, xml) -> bool

Verify action succeeded. Override to add verification. Default returns True.

```python
def postcondition(self, dev, xml):
    return "success" in dev.node_text(dev.nodes(xml)[0]).lower()
```

#### rollback(dev) -> None

Undo action on failure. Override if your action needs cleanup. Default is no-op.

```python
def rollback(self, dev):
    dev.back()  # go back if action failed
```

#### run(dev, **kwargs) -> ActionResult

Orchestrator method. Do not override.

Execution flow:
1. `precondition()` -- if False, return failure
2. `execute()` -- retry up to `max_retries` times
3. After each execute: check `postcondition()` -- if True, return success
4. On failure: call `rollback()`, wait `retry_delay`, retry
5. All retries exhausted: return failure with last error

## Workflow

Composed action sequence.

### Class Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `name` | str | Workflow identifier |
| `description` | str | Human-readable description |
| `params` | dict | Runtime parameters passed at instantiation |

### Methods

#### steps() -> list

Return list of (action_name, params) tuples. **Must be overridden.**

```python
def steps(self):
    return [
        ("open_app", {}),
        ("search_contact", {"query": self.params["contact"]}),
        ("send_message", {"text": self.params["message"]}),
    ]
```

#### run(dev) -> ActionResult

Execute all steps in order. Stops on first failure.

Returns `ActionResult` with:
- `success=True` + `data={"completed_steps": N}` on success
- `success=False` + `data={"completed_steps": N, "failed_step": "step_name"}` on failure

## Skill

Top-level container loaded from YAML.

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `name` | str | Skill identifier (directory name) |
| `app_package` | str | Android package name |
| `version` | str | Skill version |
| `elements` | dict[str, Element] | Loaded from elements.yaml |

### Class Methods

#### Skill.from_yaml(path) -> Skill

Load a skill from a directory containing `skill.yaml` and optionally `elements.yaml`.

```python
skill = Skill.from_yaml("gitd/skills/whatsapp")
```

### Instance Methods

#### register_action(action_cls)

Register an Action subclass with the skill.

```python
from .actions.core import OpenApp
skill.register_action(OpenApp)
```

#### register_workflow(workflow_cls)

Register a Workflow subclass with the skill.

#### get_action(name, device) -> Action

Get an instantiated action by name, bound to the given device.

```python
action = skill.get_action("open_app", dev)
result = action.run()
```

#### get_workflow(name, device, **params) -> Workflow

Get an instantiated workflow by name with parameters.

```python
wf = skill.get_workflow("upload_video", dev, video_path="/tmp/video.mp4")
result = wf.run()
```

#### list_actions() -> list[str]

Return names of all registered actions.

#### list_workflows() -> list[str]

Return names of all registered workflows.

## Complete Example

```python
from gitd.skills.base import Skill, Action, Workflow, ActionResult

# Define an action
class Greet(Action):
    name = "greet"
    description = "Open app and greet"

    def execute(self, dev, name="World", **kwargs):
        dev.adb("shell", "am", "start", "-n", "com.example/.Main")
        import time; time.sleep(2)
        dev.type_text(f"Hello {name}!")
        return ActionResult(success=True, data={"greeted": name})

# Define a workflow
class GreetAll(Workflow):
    name = "greet_all"
    description = "Greet multiple people"

    def steps(self):
        return [("greet", {"name": n}) for n in self.params.get("names", [])]

# Load and register
skill = Skill.from_yaml("gitd/skills/my_app")
skill.register_action(Greet)
skill.register_workflow(GreetAll)

# Run
dev = Device()
wf = skill.get_workflow("greet_all", dev, names=["Alice", "Bob"])
result = wf.run()
```

## Related

- [Skill System Feature](/features/skill-system/) -- architecture and execution flow
- [Skills Overview](/skills/overview/) -- concepts and quick start
- [API: Device Methods](/api/device-methods/) -- Device class methods used by actions
