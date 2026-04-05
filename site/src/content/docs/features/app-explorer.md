---
title: "⛏️ App Explorer"
description: BFS exploration of Android app UI — state graphs, screenshots, transition discovery, and dashboard integration.
---

The App Explorer autonomously discovers an app's UI structure by tapping every interactive element, recording state transitions, and building a navigable state graph with screenshots.

## How It Works

```
Launch app
    |
    v
BFS loop:
  1. Dump XML -> extract interactive elements
  2. Screenshot current state
  3. Hash XML structure -> check if new state
  4. For each clickable element:
     a. Tap element
     b. Wait for settle (1.5s)
     c. Dump new XML -> hash -> new state?
     d. If new: record transition, add to queue
     e. Press Back to return
  5. Write progress.json after each discovery
  6. Write state_graph.json on completion
```

## CLI Usage

```bash
python3 -m gitd.skills.auto_creator \
  --package com.zhiliaoapp.musically \
  --device YOUR_DEVICE_SERIAL \
  --max-depth 3 \
  --max-states 20 \
  --settle 1.5 \
  --output data/app_explorer/tiktok_custom
```

| Flag | Default | Description |
|------|---------|-------------|
| `--package` | required | Android package name |
| `--device` | required | ADB device serial |
| `--max-depth` | 3 | Maximum BFS depth |
| `--max-states` | 20 | Stop after N unique states |
| `--settle` | 1.5 | Seconds to wait after each tap |
| `--output` | auto | Output directory |

## REST API

```bash
# Start exploration
curl -X POST http://localhost:5055/api/explorer/start \
  -H "Content-Type: application/json" \
  -d '{
    "device": "YOUR_DEVICE_SERIAL",
    "package": "com.whatsapp",
    "max_depth": 3,
    "max_states": 50
  }'

# Check progress
curl -s http://localhost:5055/api/explorer/status | python3 -m json.tool

# Get completed state graph
curl -s http://localhost:5055/api/explorer/run/com.whatsapp | python3 -m json.tool

# List all previous explorations
curl -s http://localhost:5055/api/explorer/runs | python3 -m json.tool

# View state screenshot
curl http://localhost:5055/api/explorer/screenshot/com.whatsapp/a1b2c3 -o state.png

# Delete an exploration
curl -X DELETE http://localhost:5055/api/explorer/delete/com.whatsapp

# List installed packages (for app selection)
curl -s http://localhost:5055/api/phone/packages/YOUR_DEVICE_SERIAL | python3 -m json.tool
```

## State Graph JSON Format

```json
{
  "package": "com.zhiliaoapp.musically",
  "total_states": 4,
  "total_transitions": 3,
  "states": {
    "a1b2c3": {
      "state_id": "a1b2c3",
      "screenshot_path": "screenshots/a1b2c3.png",
      "xml_path": "xml_dumps/a1b2c3.xml",
      "activity": "com.ss.android.ugc.aweme.main.MainActivity",
      "depth": 0,
      "elements": [
        {"idx": 1, "text": "Home", "class": "TextView", "clickable": true, "bounds": {}},
        {"idx": 2, "text": "", "class": "ImageView", "clickable": true, "bounds": {}}
      ],
      "transitions": {
        "5": "d4e5f6"
      }
    }
  }
}
```

## Output Files

```
data/app_explorer/<name>/
  state_graph.json          # Full state graph
  progress.json             # Live progress (deleted after completion)
  screenshots/
    a1b2c3.png              # PNG screenshot per state
    d4e5f6.png
  xml_dumps/
    a1b2c3.xml              # Raw XML hierarchy per state
    d4e5f6.xml
```

## Dashboard Integration

The **Explorer** tab in the dashboard provides:

1. **Launch Panel** -- searchable package dropdown (130+ installed apps), device selector, depth/states/settle parameters, start/stop buttons
2. **Live Progress** -- progress bar, states/transitions/depth counters, scrolling timestamped log
3. **State Graph** -- table showing State -> Element -> Target State transitions
4. **State Browser** -- clickable state tabs showing screenshot, activity, element count, element list with transition links
5. **Previous Explorations** -- table of all runs with view/delete/re-explore buttons

## Existing Explorations

Three explorations ship pre-built:

| Name | App | States | Transitions |
|------|-----|--------|-------------|
| `tiktok` | TikTok | Shallow | Few |
| `tiktok_deep` | TikTok | Deep exploration | Many |
| `settings` | Android Settings | Medium | Several |

## Known Limitations

- **Dynamic content** -- apps like TikTok's FYP generate different XML hashes for the same logical screen (video content changes the hash)
- **Back-navigation drift** -- pressing Back sometimes lands on an unexpected screen
- **No resume** -- explorations always start fresh; no way to continue a previous run
- **No skill generation** -- the state graph is not yet automatically converted into skill actions/workflows

## Related

- [Skill Creator](/features/skill-creator/) -- use state graphs to inform LLM skill generation
- [Skill System](/features/skill-system/) -- actions and workflows that explorer could generate
- [ADB Device](/features/adb-device/) -- dump_xml and tap methods used by explorer
