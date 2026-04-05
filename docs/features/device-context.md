# Device Context Extraction — Feature Summary

Shared context extraction layer that powers MCP tools, REST API endpoints, and the Skill Creator. Single source of truth in `gitd/services/device_context.py` — no duplicate code across consumers.

## Tools (19 functions, all available as MCP tools + REST endpoints)

### Screen Understanding

| Tool | What it does | Speed |
|------|-------------|-------|
| `get_phone_state` | Current app, activity, keyboard, focused element | Fast (Portal HTTP) |
| `get_screen_tree` | LLM-readable indented UI hierarchy with element indices | Fast (XML parse) |
| `get_interactive_elements` | Clickable/text elements as JSON with bounds + centers | Fast (XML parse) |
| `get_screen_xml` | Raw uiautomator XML dump | Fast (ADB) |
| `classify_screen` | Detect screen type: home, search, dialog, error, loading | Fast (heuristic) |
| `find_on_screen` | Find specific text → return location (XML first, OCR fallback) | Fast/Medium |

### Visual Capture

| Tool | What it does | Speed |
|------|-------------|-------|
| `screenshot` | ADB screencap → base64 JPEG (half-res) | Fast (~200ms) |
| `screenshot_annotated` | Screenshot with Portal's numbered element overlay | Fast (~300ms) |
| `screenshot_cropped` | Cropped region of screen | Fast (~200ms) |

### OCR (for canvas/image content invisible to XML)

| Tool | What it does | Speed |
|------|-------------|-------|
| `ocr_screen` | RapidOCR full screen → [{text, conf, x, y, w, h}] | ~1-2s |
| `ocr_region` | RapidOCR cropped region → [{text, conf, x, y, w, h}] | ~0.5-1s |

### Device Interaction

| Tool | What it does |
|------|-------------|
| `clipboard_get` | Read clipboard text |
| `clipboard_set` | Set clipboard text |
| `get_notifications` | List active notifications |
| `open_notifications` | Pull down notification shade |
| `clear_notifications` | Dismiss all notifications |
| `launch_intent` | Full Android intent API (action, data, extras) |
| `toggle_overlay` | Toggle Portal numbered element overlay on/off |

### Agent Convenience

| Tool | What it does |
|------|-------------|
| `build_llm_context` | All-in-one context snapshot (state + elements + tree + screenshot + optional OCR) |

## When to use what

| Situation | Best tool |
|-----------|----------|
| "What app am I in?" | `get_phone_state` |
| "What can I tap?" | `get_interactive_elements` |
| "Help me understand this screen" | `get_screen_tree` (for LLM) or `screenshot_annotated` (for vision) |
| "Is there a Login button?" | `find_on_screen("Login")` |
| "Read the analytics numbers" | `ocr_screen` or `ocr_region` (canvas-rendered) |
| "What type of screen is this?" | `classify_screen` |
| "Zoom into this area" | `screenshot_cropped` |
| "Copy this text" | `clipboard_get` / `clipboard_set` |
| "Check my messages" | `get_notifications` |
| "Open a URL" | `launch_intent(action="VIEW", data="https://...")` |

## Architecture

```
services/device_context.py (19 shared functions)
         |
    +----+----+----+
    |         |         |
MCP Server   FastAPI    Skill Creator
(mcp_server.py)  (routers/phone.py)  (routers/creator.py)
    |         |         |
  Agents    Dashboard   LLM Chat
```

## REST API Endpoints

| Method | Endpoint | Maps to |
|--------|----------|---------|
| GET | `/api/phone/elements/{device}` | `get_interactive_elements()` |
| GET | `/api/phone/screenshot/{device}` | `screenshot()` |
| GET | `/api/phone/screenshot-annotated/{device}` | `screenshot_annotated()` |
| GET | `/api/phone/screenshot-crop/{device}?x1=&y1=&x2=&y2=` | `screenshot_cropped()` |
| GET | `/api/phone/xml/{device}` | `get_screen_xml()` |
| GET | `/api/phone/screen-tree/{device}` | `get_screen_tree()` |
| GET | `/api/phone/ocr/{device}?x1=&y1=&x2=&y2=` | `ocr_screen()` / `ocr_region()` |
| GET | `/api/phone/classify/{device}` | `classify_screen()` |

## File

`gitd/services/device_context.py` — single file, all 19 functions.
