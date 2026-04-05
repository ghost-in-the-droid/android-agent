---
title: "🎬 Macro Recorder"
description: MacroStep, Macro, and MacroRecorder classes — record, save, load, edit, and replay ADB action sequences.
---

The macro recorder captures sequences of ADB actions with timestamps and replays them with configurable speed. It is defined in `gitd/skills/macro_recorder.py` (197 lines).

## Classes

### MacroStep

A single recorded action:

```python
@dataclass
class MacroStep:
    action: str          # tap, swipe, type, back, home, wait
    timestamp: float     # seconds since recording started
    params: dict         # action-specific parameters
    element_info: dict   # optional element metadata (not used for replay)
```

### Macro

A sequence of steps with metadata:

```python
class Macro:
    name: str
    steps: list[MacroStep]
    device_serial: str
    recorded_at: str
    duration_s: float

    def save(self, path: str): ...
    @classmethod
    def load(cls, path: str) -> Macro: ...
    def to_dict(self) -> dict: ...
    @classmethod
    def from_dict(cls, d: dict) -> Macro: ...
```

### MacroRecorder

Records actions on a device and replays macros:

```python
class MacroRecorder:
    def __init__(self, device: Device): ...

    # Recording
    def start(self): ...
    def stop(self) -> Macro: ...
    def record_step(self, action: str, **params): ...

    # Action wrappers (record + execute)
    def tap(self, x, y): ...
    def swipe(self, x1, y1, x2, y2): ...
    def type_text(self, text): ...
    def back(self): ...
    def home(self): ...
    def wait(self, seconds): ...

    # Replay
    def replay(self, macro: Macro, speed: float = 1.0): ...
```

## Recording

Each method on the recorder simultaneously executes the action on the device and records it:

```python
from gitd.skills.macro_recorder import MacroRecorder
from gitd.bots.common.adb import Device

dev = Device()
rec = MacroRecorder(dev)

rec.start()                            # _recording = True, _start_time = now
rec.tap(540, 1200)                     # executes tap + records MacroStep
rec.wait(1.0)                          # sleeps 1s + records wait step
rec.swipe(540, 1400, 540, 800)         # executes swipe + records step
rec.type_text("hello")                 # types text + records step
rec.back()                             # presses back + records step
macro = rec.stop()                     # returns Macro with all steps
```

### 6 Recordable Actions

| Action | Method | Parameters |
|--------|--------|-----------|
| `tap` | `rec.tap(x, y)` | `{x, y}` |
| `swipe` | `rec.swipe(x1, y1, x2, y2)` | `{x1, y1, x2, y2, ms}` |
| `type` | `rec.type_text(text)` | `{text}` |
| `back` | `rec.back()` | `{}` |
| `home` | `rec.home()` | `{}` |
| `wait` | `rec.wait(seconds)` | `{seconds}` |

## JSON Format

```json
{
  "name": "search_and_type",
  "device_serial": "YOUR_DEVICE_SERIAL",
  "recorded_at": "2026-03-23 15:45:00 UTC",
  "duration_s": 8.5,
  "step_count": 5,
  "steps": [
    {"action": "tap", "timestamp": 0.0, "params": {"x": 540, "y": 1200}, "element_info": null},
    {"action": "wait", "timestamp": 0.5, "params": {"seconds": 1.0}, "element_info": null},
    {"action": "swipe", "timestamp": 1.8, "params": {"x1": 540, "y1": 1400, "x2": 540, "y2": 800, "ms": 500}, "element_info": null},
    {"action": "type", "timestamp": 3.2, "params": {"text": "hello world"}, "element_info": null},
    {"action": "back", "timestamp": 4.1, "params": {}, "element_info": null}
  ]
}
```

## Replay Timing

Replay preserves relative timing between steps, scaled by the `speed` parameter:

```
Step 1: timestamp=0.0  -> execute immediately
Step 2: timestamp=1.5  -> wait (1.5 - 0.0) / speed seconds
Step 3: timestamp=3.0  -> wait (3.0 - 1.5) / speed seconds
```

| Speed | Effect |
|-------|--------|
| `0.5` | Half speed (waits doubled) |
| `1.0` | Original speed |
| `2.0` | Double speed (waits halved) |
| `5.0` | 5x speed |

Minimum wait threshold: 0.05s -- waits shorter than this are skipped.

## Programmatic Editing

```python
from gitd.skills.macro_recorder import MacroStep, Macro

macro = Macro.load("data/macros/my_flow.json")

# Insert a 2-second wait at the beginning
macro.steps.insert(0, MacroStep(action="wait", timestamp=0, params={"seconds": 2.0}))

# Change tap coordinates
macro.steps[2].params["x"] = 600

# Remove the last step
macro.steps.pop()

# Save modified macro
macro.save("data/macros/modified.json")
```

## Convert to Skill

The create-from-recording API endpoint generates a skill directory from macro steps:

```bash
curl -X POST http://localhost:5055/api/skills/create-from-recording \
  -H "Content-Type: application/json" \
  -d '{"name": "my_skill", "app_package": "com.example", "steps": [...]}'
```

Creates `skills/<name>/skill.yaml` + `workflows/recorded.json` + `__init__.py`.

## Limitations

- **Coordinate-based** -- records pixel positions, not UI element identifiers
- **No conditional logic** -- no if/else branching during replay
- **ASCII only** -- `type_text` does not support emoji or unicode
- **No error handling** -- if a step fails, replay continues with the next step
- **Manual recording** -- you call `rec.tap()` explicitly; no auto-capture from device events

## Related

- [Macros Guide](/guides/macros/) -- practical usage patterns
- [Skill System](/features/skill-system/) -- for automation with pre/post conditions
- [Skill Creator](/features/skill-creator/) -- visual LLM-powered skill building
