# API Reference

The backend auto-generates interactive API documentation via FastAPI's OpenAPI integration. **Use these instead of this file for the full, always-up-to-date endpoint listing:**

- **Swagger UI**: [http://localhost:5055/docs](http://localhost:5055/docs)
- **ReDoc**: [http://localhost:5055/redoc](http://localhost:5055/redoc)

---

## Router Tags (21 domains)

| Tag | Prefix | Description |
|-----|--------|-------------|
| **stats** | `/api/stats` | Dashboard stats, hashtag analytics, growth data |
| **content** | `/api/content` | Video content library, posts, drafts |
| **content-plan** | `/api/content-plan` | Content calendar, generation pipeline |
| **generate** | `/api/gen` | AI video generation |
| **bot** | `/api/bot` | Post bot, crawl queue |
| **bot-workers** | `/api/bot-workers` | Background bot worker management |
| **scheduler** | `/api/schedules`, `/api/scheduler` | Job scheduling, queue management, history |
| **phone** | `/api/phone` | ADB device control, tap, swipe, screenshots |
| **streaming** | `/api/phone/stream` | MJPEG + WebRTC phone screen streaming |
| **streaming-viewers** | `/api/phone/webrtc-*` | WebRTC viewer pages and signaling |
| **skills** | `/api/skills` | Installed skill packages, run actions/workflows |
| **creator** | `/api/creator` | LLM-assisted skill builder with device stream |
| **explorer** | `/api/explorer` | Auto skill miner (BFS state discovery) |
| **tests** | `/api/tests`, `/api/test-runner` | Test runner, recordings, per-device execution |
| **analytics** | `/api/analytics` | Post performance metrics |
| **accounts** | `/api/accounts` | TikTok account management |
| **styles** | `/api/styles` | Content styles and input images |
| **inbox** | `/api/inbox` | Inbox snapshots |
| **agent** | `/api/agent` | Content planning AI agent |
| **misc** | `/api/misc`, `/api/health` | Health check, logs, server management |

---

## Example Requests

### Health check

```bash
curl http://localhost:5055/api/health
# {"status": "ok", "server": "fastapi"}
```

### List connected devices

```bash
curl http://localhost:5055/api/phone/devices
```

### List installed skills

```bash
curl http://localhost:5055/api/skills | python3 -m json.tool
```

### Run a skill workflow

```bash
curl -X POST http://localhost:5055/api/skills/tiktok/run \
  -H "Content-Type: application/json" \
  -d '{"workflow": "upload_video", "params": {"video_path": "/tmp/video.mp4"}, "device": "YOUR_DEVICE_SERIAL"}'
```

### Start a bot job

```bash
curl -X POST http://localhost:5055/api/bot/start \
  -H "Content-Type: application/json" \
  -d '{"type": "post", "device": "YOUR_DEVICE_SERIAL", "params": {"video_path": "/tmp/video.mp4"}}'
```

---

## Authentication

No authentication is required. The server is designed for local use on a trusted network. API keys for external services (OpenAI, Anthropic, etc.) are configured server-side via `.env`.

## Response Format

All endpoints return JSON. Successful responses return the data directly. Errors return `{"detail": "error message"}` with an appropriate HTTP status code (400, 404, 422, 500).
