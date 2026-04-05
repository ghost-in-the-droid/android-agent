---
title: "🎬 Record Macros"
description: Record, save, load, edit, and replay ADB action sequences with configurable speed control.
---

The macro system lets you record sequences of ADB actions, save them as JSON, and replay them later at any speed. Useful for repetitive flows that don't need the full skill system.

## Core Concepts

| Class | Purpose |
|-------|---------|
| `MacroStep` | Single recorded action (tap, swipe, type, back, home, wait) with timestamp |
| `Macro` | Sequence of steps with metadata (name, device, duration, recorded_at) |
| `MacroRecorder` | Records actions on a device and replays macros |

## Recording a Macro

Each method on the recorder both **executes** the action on the device and **records** it with a timestamp.

```python
from gitd.skills.macro_recorder import MacroRecorder, Macro
from gitd.bots.common.adb import Device

dev = Device()
rec = MacroRecorder(dev)

rec.start()                               # Begin recording
rec.tap(540, 1200)                        # Tap + record
rec.wait(1.0)                             # Explicit pause
rec.swipe(540, 1400, 540, 800)            # Swipe + record
rec.type_text("search query")             # Type + record
rec.back()                                # Back + record
rec.home()                                # Home + record
macro = rec.stop()                        # Stop, get Macro object

print(f"Recorded {len(macro.steps)} steps in {macro.duration_s:.1f}s")
```

### Available Actions

| Action | Method | Parameters |
|--------|--------|-----------|
| Tap | `rec.tap(x, y)` | Screen coordinates |
| Swipe | `rec.swipe(x1, y1, x2, y2)` | Start and end coordinates |
| Type | `rec.type_text(text)` | ASCII text string |
| Back | `rec.back()` | None |
| Home | `rec.home()` | None |
| Wait | `rec.wait(seconds)` | Duration in seconds |

## Saving and Loading

Macros serialize to human-readable JSON:

```python
# Save
macro.name = "my_flow"
macro.save("data/macros/my_flow.json")

# Load
loaded = Macro.load("data/macros/my_flow.json")
print(f"Loaded: {loaded.name}, {len(loaded.steps)} steps")
```

### JSON Format

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

Since the format is plain JSON, you can edit macros in any text editor -- adjust coordinates, change timing, add or remove steps.

## Replaying

Replay preserves relative timing between steps, scaled by the speed parameter.

```python
# Replay at original speed
rec.replay(loaded, speed=1.0)

# Replay at 2x speed (waits halved)
rec.replay(loaded, speed=2.0)

# Replay at half speed (waits doubled)
rec.replay(loaded, speed=0.5)
```

### Timing Example

With `speed=2.0`:

```
Step 1: timestamp=0.0  -> execute immediately
Step 2: timestamp=1.5  -> wait (1.5 - 0.0) / 2.0 = 0.75s, then execute
Step 3: timestamp=3.0  -> wait (3.0 - 1.5) / 2.0 = 0.75s, then execute
```

Minimum wait threshold: 0.05 seconds. Waits smaller than this are skipped.

## Editing Macros Programmatically

```python
from gitd.skills.macro_recorder import MacroStep

# Insert a wait at the beginning
loaded.steps.insert(0, MacroStep(
    action="wait",
    timestamp=0,
    params={"seconds": 2.0}
))

# Remove the last step
loaded.steps.pop()

# Modify a step's coordinates
loaded.steps[1].params["x"] = 600
loaded.steps[1].params["y"] = 1300

# Save the modified macro
loaded.save("data/macros/modified.json")
```

## Converting Macros to Skills

Recorded macro steps can be converted into a skill directory structure via the API:

```bash
curl -X POST http://localhost:5055/api/skills/create-from-recording \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my_skill",
    "app_package": "com.example.app",
    "steps": [
      {"action": "tap", "params": {"x": 540, "y": 1200}},
      {"action": "wait", "params": {"seconds": 1.0}},
      {"action": "swipe", "params": {"x1": 540, "y1": 1400, "x2": 540, "y2": 800}}
    ]
  }'
```

This creates `skills/<name>/skill.yaml` + `workflows/recorded.json` + `__init__.py`.

## Limitations

- **Coordinate-based** -- macros record pixel coordinates, not element identifiers. If the app layout changes, macros break.
- **No conditional logic** -- cannot branch based on screen state (use the skill system for that).
- **ASCII only** -- `type_text` uses `adb shell input text`, which does not support emoji or unicode.
- **No error handling** -- if a step fails during replay, the macro continues to the next step.
- **Manual recording** -- you call `rec.tap()` explicitly; there is no auto-capture from device touch events.

## Related

- [Skill System](/features/skill-system/) -- for more robust automation with pre/post conditions
- [Skill Creator](/features/skill-creator/) -- visual tool for building skills with LLM assistance
- [Stealth Mode](/guides/stealth/) -- add randomization to replayed macros
