---
title: "📎 Device Context"
description: 19 shared screen understanding tools — screenshots, OCR, UI trees, clipboard, notifications, and more. Used by MCP tools, REST API, and Skill Creator.
---

Shared context extraction layer that powers every way agents interact with device screens. Single source of truth — MCP tools, REST endpoints, and the Skill Creator all call the same functions.

## Screen Understanding

| Tool | What it does | Speed |
|------|-------------|-------|
| `get_phone_state` | Current app, activity, keyboard, focused element | Fast |
| `get_screen_tree` | LLM-readable indented UI hierarchy with element indices | Fast |
| `get_interactive_elements` | Clickable/text elements as JSON with bounds + centers | Fast |
| `get_screen_xml` | Raw uiautomator XML dump | Fast |
| `classify_screen` | Detect screen type: home, search, dialog, error, loading | Fast |
| `find_on_screen` | Find specific text, return location (XML first, OCR fallback) | Fast-Medium |

### get_screen_tree — LLM-optimized

The most important tool for LLM agents. Converts the raw XML dump into an indented, readable format:

```
[1] FrameLayout [0,0][1080,2340]
  [2] ViewGroup "ehr" [0,80][1080,2205]
    [3] FrameLayout "Bottom sheet" [clickable] [0,861][1080,2205]
    [4] TextView "Following" [clickable] [40,200][200,240]
    [5] TextView "10" [100,200][160,240]
    [6] ImageView "profile_image" [clickable] [440,80][640,280]
```

Agents can read this and decide "I need to tap element [4] to see Following list" — no vision model needed.

### classify_screen — Quick state check

Heuristic screen type detection without LLM:

```json
{
  "app": "TikTok",
  "package": "com.zhiliaoapp.musically",
  "screen_type": "profile",
  "has_keyboard": false,
  "activity": "X.0sWc"
}
```

Screen types: `launcher`, `feed`, `search`, `profile`, `settings`, `dialog`, `error`, `loading`, `unknown`.

## Visual Capture

| Tool | What it does |
|------|-------------|
| `screenshot` | Standard screencap (half-res JPEG, ~200ms) |
| `screenshot_annotated` | Screenshot with Portal's numbered element overlay — each interactive element gets a visible number badge |
| `screenshot_cropped` | Crop a specific region (x1, y1, x2, y2 in device pixels) |

### Annotated screenshots

When `screenshot_annotated` is called, the Portal app draws numbered labels on every interactive element. The numbers match `get_interactive_elements()` indices. This is ideal for vision-capable LLMs that can look at the image and say "tap element 5."

## OCR

For content rendered as images — analytics dashboards, games, WebViews, canvas-drawn text — where `get_elements()` returns nothing.

| Tool | What it does |
|------|-------------|
| `ocr_screen` | Full screen OCR via RapidOCR (CPU, no GPU) |
| `ocr_region(x1, y1, x2, y2)` | OCR a cropped region — more accurate for targeted extraction |

Returns `[{text, conf, x, y, w, h}]` sorted top-to-bottom.

**Used in production** for TikTok analytics scraping (post views, likes, shares from the Insights screen) and Instagram reel engagement stats.

## Device Interaction Tools

| Tool | What it does | Example |
|------|-------------|---------|
| `clipboard_get` | Read clipboard | Check copied text |
| `clipboard_set` | Set clipboard | Prepare text for paste |
| `get_notifications` | List active notifications | Check for new messages |
| `open_notifications` | Pull down notification shade | Access notification panel |
| `clear_notifications` | Dismiss all | Clean up |
| `launch_intent` | Full Android intent API | Open URLs, share text, launch specific activities |
| `toggle_overlay` | Portal numbered element overlay | Visual debugging |
| `find_on_screen` | Find text → get location | "Is the Login button visible?" |

### launch_intent — Full Android Intent API

More powerful than `launch_app()`:

```python
# Open a URL in browser
launch_intent(device, action="android.intent.action.VIEW", data="https://google.com")

# Open Settings
launch_intent(device, package="com.android.settings")

# Share text to any app
launch_intent(device, action="android.intent.action.SEND",
              extras={"android.intent.extra.TEXT": "Check this out!"})
```

## Agent Convenience

`build_llm_context(device)` returns everything an agent needs in one call:

```python
{
    "phone_state": {...},        # app, activity, keyboard
    "screen_type": {...},        # classification
    "elements": [...],           # interactive elements (max 40)
    "screen_tree": "...",        # indented hierarchy
    "screenshot": {...},         # base64 JPEG (optional)
    "ocr": [...]                 # OCR results (optional)
}
```

## Architecture

All 19 functions live in one file: `gitd/services/device_context.py`. Three consumers, zero duplication:

- **MCP Server** — exposes as tools for Claude Code, Cursor, Codex CLI, OpenClaw
- **FastAPI Router** — REST endpoints for the dashboard and external integrations
- **Skill Creator** — builds LLM system prompts with live device context
