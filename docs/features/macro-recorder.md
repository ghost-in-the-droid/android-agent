# Macro Record/Replay — Feature Summary

## What It Does

Records a sequence of ADB actions (tap, swipe, type, back, home, wait) with precise timestamps and replays them at configurable speed. Provides three classes: `MacroStep` (single recorded action), `Macro` (sequence of steps with metadata), and `MacroRecorder` (records actions on a device and replays macros). Macros are saved/loaded as JSON files for sharing and reuse.

## Current State

**Working:**
- `MacroRecorder` class: start, stop, record individual actions, replay with speed control
- `Macro` class: save to JSON, load from JSON, serialize/deserialize
- `MacroStep` dataclass: action type, timestamp (relative to recording start), params, optional element info
- 6 recordable actions: tap, swipe, type_text, back, home, wait
- Configurable replay speed (0.5x slow, 1x normal, 2x fast, etc.)
- Relative timing preserved: replay waits the exact time delta between steps (scaled by speed)
- JSON format is human-readable and editable
- Logging throughout (start, stop, each replay step)

**Limitations:**
- No dashboard UI integration — Python API and CLI only
- Recording is manual (call `rec.tap()` etc.) — not auto-captured from device events
- No screen recording alongside macro recording
- No conditional logic (if element exists → do X, else → do Y)
- No element-aware recording (records coordinates only, not element identifiers)
- `type_text` uses `adb shell input text` (ASCII only, no unicode)
- No error handling during replay (if an action fails, replay continues)

## Architecture

```
MacroRecorder(device)
    │
    │  .start() → sets _recording=True, _start_time=now
    ▼
User calls rec.tap(x, y), rec.swipe(...), rec.type_text(...), etc.
    │
    │  Each call:
    │    1. record_step() → append MacroStep(action, timestamp=now-start, params)
    │    2. Execute actual ADB command on device
    ▼
rec.stop() → returns Macro(steps, duration, device_serial, recorded_at)
    │
    │  macro.save('/path/to/file.json') → JSON file
    ▼
Later: macro = Macro.load('/path/to/file.json')
    │
    │  rec.replay(macro, speed=2.0)
    ▼
For each step:
    1. Wait (step.timestamp - prev_timestamp) / speed
    2. Execute action (tap, swipe, type, back, home, wait)
    3. No delay after action (timing comes from step timestamps)
```

## Files

| File | Purpose |
|------|---------|
| `gitd/skills/macro_recorder.py` | `MacroRecorder`, `Macro`, `MacroStep` classes (197 lines) |
| `gitd/bots/common/adb.py` | `Device` class used by recorder for ADB commands |

## Classes

| Class | Key Fields / Methods |
|-------|---------------------|
| `MacroStep` | `action: str` (tap/swipe/type/back/home/wait), `timestamp: float` (seconds since start), `params: dict`, `element_info: dict` (optional) |
| `Macro` | `name`, `steps: list[MacroStep]`, `device_serial`, `recorded_at`, `duration_s`. Methods: `save(path)`, `load(path)`, `to_dict()`, `from_dict(d)` |
| `MacroRecorder` | `__init__(dev)`, `start()`, `stop() → Macro`, `record_step(action, **params)`. Action wrappers: `tap(x,y)`, `swipe(...)`, `type_text(text)`, `back()`, `home()`, `wait(s)`. Replay: `replay(macro, speed=1.0)` |

## Macro JSON Format

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

## How to Use

```python
from gitd.skills.macro_recorder import MacroRecorder, Macro
from gitd.bots.common.adb import Device

d = Device('YOUR_DEVICE_SERIAL')
rec = MacroRecorder(d)

# Record a sequence
rec.start()
rec.tap(540, 1200)           # tap + record
rec.wait(1.0)                # explicit pause
rec.swipe(540, 1400, 540, 800)  # swipe + record
rec.type_text("hello world")    # type + record
rec.back()                   # back + record
macro = rec.stop()           # stop recording, get Macro

# Save to file
macro.save('/tmp/my_macro.json')
print(f'Recorded {len(macro.steps)} steps in {macro.duration_s:.1f}s')

# Load and replay at 2x speed
loaded = Macro.load('/tmp/my_macro.json')
rec.replay(loaded, speed=2.0)

# Edit macro programmatically
loaded.steps.insert(0, MacroStep(action='wait', timestamp=0, params={'seconds': 2.0}))
loaded.save('/tmp/modified_macro.json')
```

## Replay Timing

Replay preserves relative timing between steps. With `speed=1.0`, actions execute at the same pace as recorded. With `speed=2.0`, waits are halved:

```
Step 1: timestamp=0.0  → execute immediately
Step 2: timestamp=1.5  → wait (1.5 - 0.0) / 2.0 = 0.75s, then execute
Step 3: timestamp=3.0  → wait (3.0 - 1.5) / 2.0 = 0.75s, then execute
```

Minimum wait threshold: 0.05s (skipped if delta is smaller).

## Integration with Skill System

The `create-from-recording` API endpoint (`POST /api/skills/create-from-recording`) can convert recorded steps into a skill directory:

```bash
curl -X POST http://localhost:5055/api/skills/create-from-recording \
  -H "Content-Type: application/json" \
  -d '{"name": "my_skill", "app_package": "com.example", "steps": [...]}'
```

This creates `skills/<name>/skill.yaml` + `workflows/recorded.json` + `__init__.py`.

## Known Issues & TODOs

- [ ] Dashboard UI for recording (click Record → interact via WebRTC → Stop → save)
- [ ] Auto-capture from ADB event monitoring (no manual `rec.tap()` calls needed)
- [ ] Conditional steps (wait for element, if/else branching, retry on failure)
- [ ] Element-aware recording (store element identifiers, not just coordinates)
- [ ] Convert macro → Skill actions/workflows automatically (smarter than create-from-recording)
- [ ] Error handling during replay (stop, retry, or skip on failure)
- [ ] Screenshot capture during recording (annotated step-by-step documentation)
- [ ] Unicode text support (currently ASCII only via `adb input text`)
