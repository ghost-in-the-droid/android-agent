# Control Fossify Paint on Android with an AI agent — draw and paint

**Control Fossify Paint on Android with an AI agent.** Draw on your phone: an agent picks a colour, draws lines, fills shapes and checks what is on the canvas.

Target search phrase: _AI agent draws on Android_

Demo shows: `set_color (color=red)`

> Ghost in the Droid seed skill for Fossify Paint (`org.fossify.paint`), an offline drawing app. The canvas has no accessibility nodes, so the skill draws by percent coordinates and reads the result back from a screenshot (ink coverage and colour mix). Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `new_drawing` | Clear the canvas (needs confirm=yes) | `confirm` |
| `set_color` | Pick red, blue, green, yellow or orange | `color` |
| `draw_path` | Draw connected segments through percent points (x,y;x,y) | `points` |
| `fill` | Flood-fill the area at a percent point with the current colour | `x`, `y` |
| `get_canvas` | Read ink coverage and colour mix | none |

## Toolkit

An agent can drive the whole app with these; compose them.

| Role | Action |
|---|---|
| Entry | new_drawing |
| Primitives | set_color, draw_path, fill |
| Read state | get_canvas (ink coverage and colour mix, from a screenshot) |

## Install

The app: F-Droid, or `https://f-droid.org/packages/org.fossify.paint/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/paint
```

## Use

```bash
ghost skill run ghost/paint set_color --param color=red --device <serial>
ghost skill run ghost/paint draw_path --param 'points=20,70;50,20;80,70;20,70' --device <serial>
```

```python
run_skill(name="ghost/paint", action="draw_path", params={"points": "20,70;50,20;80,70;20,70"})
# {"result": {"segments": 3, "canvas": {"ink_pct": 6.5, "colours": {"red": 6.4}}}}
```

Try asking: "Draw a red triangle and fill it with blue."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), Fossify Paint 1.4.0. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 1.4.0 | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.0 | 2026-11-02 |

### Recorded failures

- Colour names are limited to the 5 presets; the hex field is not used (it reformats while typing).
- fill on an unclosed shape floods the whole canvas.
- The state is read from a screenshot, so the screen must be on and unlocked.
- Strokes are straight segments; curves need many short segments.
- new_drawing wipes the canvas, so it needs confirm=yes; get_canvas is the non-destructive way in.

### Popups and first-run screens handled

- None.
