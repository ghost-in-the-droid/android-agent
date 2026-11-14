# paint - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `org.fossify.paint` (Fossify Paint, GPL-3.0, version 1.4.0 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- Toolbar: Save, Clear (trash), Share, More options; tool column on the right: Bucket fill, Eraser, Eyedropper, Change colour (a square showing the active colour), Undo.
- The colour dialog shows 5 preset swatches (red, blue, green, yellow, orange) plus a hex field (live-validating, unreliable to type into, so the skill uses the swatches).
- The canvas and the brush-size slider are plain views: no nodes. Safe drawing area is the middle band of the screen, clear of the toolbar overlay and the slider.

## Actions

### `new_drawing(confirm)`

Taps Clear and confirms if asked. Success: ink coverage 0.

### `set_color(color)`

Opens the colour dialog, taps the preset swatch, OK. Verified by sampling the colour square.

### `draw_path(points)`

One swipe per segment. Success: ink coverage grew.

### `fill(x, y)`

Taps the bucket, then the point. Success: ink coverage grew.

### `get_canvas()`

Screenshot analysis with Pillow: ink_pct and a named colour histogram.

## Adapting

Coordinates are percent of the safe canvas band, so the same drawing works on other screens. A closed outline is needed before fill, otherwise the colour floods the whole canvas. Brush size and eraser are not driven by this version.
