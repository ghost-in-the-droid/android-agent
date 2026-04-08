---
title: "🌐 REST Endpoints"
description: All 90+ REST API endpoints organized by category — phone, bot, content, scheduler, skills, and more.
---

The server exposes 90+ REST endpoints at `http://localhost:5055`. All responses are JSON unless noted otherwise.

## Phone and Device

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/phone/devices` | List connected devices (serial, model, nickname, status) |
| GET | `/api/phone/stream/<device>` | MJPEG stream (use as img src) |
| POST | `/api/phone/input` | Send input (tap, swipe, type, keyevent) |
| GET | `/api/phone/elements/<device>` | Interactive UI elements on screen |
| GET | `/api/phone/packages/<device>` | List installed packages |

### Input Actions

```json
{"device": "serial", "action": "tap", "x": 540, "y": 1200}
{"device": "serial", "action": "swipe", "x1": 540, "y1": 1800, "x2": 540, "y2": 600}
{"device": "serial", "action": "type", "text": "hello"}
{"device": "serial", "action": "keyevent", "key": "KEYCODE_BACK"}
```

## Bot Control

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/bot/start` | Start a bot job |
| GET | `/api/bot/status` | Running bots per device |
| GET | `/api/bot/logs/<job_id>` | Log output for a job |
| POST | `/api/bot/stop` | Stop bot on a device |

### Bot Types and Parameters

```json
{
  "type": "crawl",
  "device": "serial",
  "params": {"query": "#Cat", "tab": "top", "passes": 5, "date_filter": "Past 24 hours"}
}
```

| Type | Key Params |
|------|-----------|
| `crawl` | `query`, `tab`, `passes`, `date_filter` |
| `post` | `video_id`, `caption`, `hashtags`, `as_draft` |
| `publish_draft` | `draft_tag` |
| `skill_workflow` | `skill`, `workflow`, `params` |
| `skill_action` | `skill`, `action`, `params` |
| `app_explore` | `package`, `max_depth`, `max_states` |

### Query Parameters for List

```
?page=1&per_page=50&sort=followers&order=desc&label=pet&min_followers=1000&status=not_contacted
```

## Content and Videos

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/content/videos` | List videos (filter by status, type) |
| GET | `/api/content/posts` | Upload history for a video |
| POST | `/api/content/videos/<id>` | Update video status |


## Scheduler

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/schedules` | List all schedules |
| POST | `/api/schedules` | Create schedule |
| PUT | `/api/schedules/<id>` | Update schedule |
| DELETE | `/api/schedules/<id>` | Delete schedule |
| POST | `/api/schedules/<id>/toggle` | Enable/disable |
| POST | `/api/schedules/<id>/run-now` | Trigger immediate run |
| GET | `/api/scheduler/status` | Per-phone status |
| GET | `/api/scheduler/queue` | Current job queue |
| GET | `/api/scheduler/queue/<id>/logs` | Job log stream |
| POST | `/api/scheduler/queue/<id>/kill` | Kill a job |
| POST | `/api/scheduler/runs/<id>/restart` | Re-enqueue job |
| GET | `/api/scheduler/history` | Archived job runs |
| GET | `/api/scheduler/history/<id>/logs` | Archived run logs |
| GET | `/api/scheduler/timeline` | 24h timeline data |

## Skills

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/skills` | List all skills |
| GET | `/api/skills/<name>` | Skill detail |
| GET | `/api/skills/<name>/actions` | List actions |
| GET | `/api/skills/<name>/workflows` | List workflows |
| POST | `/api/skills/<name>/run` | Run workflow |
| POST | `/api/skills/<name>/run-action` | Run single action |
| GET | `/api/skills/export/<name>` | Download skill ZIP |
| POST | `/api/skills/import` | Upload skill ZIP |
| POST | `/api/skills/create-from-recording` | Create skill from macro |

## Skill Creator

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/creator/chat` | Send message to LLM |
| POST | `/api/creator/chat-stream` | Streaming chat response |
| GET | `/api/creator/ollama-models` | List Ollama models |

## App Explorer

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/explorer/start` | Start BFS exploration |
| POST | `/api/explorer/stop` | Stop exploration |
| GET | `/api/explorer/status` | Poll progress |
| GET | `/api/explorer/runs` | List all explorations |
| GET | `/api/explorer/run/<name>` | Full state graph |
| GET | `/api/explorer/screenshot/<name>/<state_id>` | State screenshot |
| DELETE | `/api/explorer/delete/<name>` | Delete exploration |

## Analytics

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/analytics` | Post performance metrics |

## Tests

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/tests` | List test files and functions |
| POST | `/api/test-runner/start` | Run pytest suite |
| GET | `/api/test-runner/status` | Test run status |
| GET | `/api/test-runner/recordings` | List screen recordings |

## WebRTC Streaming

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/phone/webrtc-signal` | Relay signaling |
| POST | `/api/phone/webrtc-callback/<device>` | Receive from Portal |
| GET | `/api/phone/webrtc-poll-signals/<device>` | Poll signals |
| POST | `/api/phone/webrtc-ws-send` | Send via WebSocket |
| POST | `/api/phone/webrtc-ws-poll` | Poll WebSocket |
| GET | `/api/phone/webrtc-viewer` | Single-device viewer page |
| GET | `/api/phone/webrtc-multi` | Multi-device viewer page |

## Related

- [API: Device Methods](/api/device-methods/) -- Python Device class API
- [API: Skill Classes](/api/skill-classes/) -- Python skill classes
- [API: CLI](/api/cli/) -- command-line usage
