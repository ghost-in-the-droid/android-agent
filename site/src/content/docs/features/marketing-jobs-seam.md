---
title: "Marketing Jobs Seam"
description: One HTTP endpoint that lets an external orchestrator queue a TikTok post through Ghost — draft-only by design. The clean boundary between "content brain" and "phone hands".
---

⭐ **New in 1.3** — A single, deliberately narrow endpoint: `POST /api/marketing-jobs/enqueue`. It's how an outside agent hands Ghost a video to post, without reaching into anything else.

## Why this exists — the split

Ghost's job is **phone hands**: driving a real Android device over ADB. Deciding *what* to post, *when*, and *with what caption* is a different job — a **content brain** — and it lives in a separate process (for the reference deployment, that's an external [social-media-agent](https://github.com/ghost-in-the-droid/android-agent) orchestrator).

The two talk through exactly one seam:

```
┌─────────────────────────────────┐         ┌─────────────────────────────────┐
│  External agent (content brain) │         │  Ghost (phone hands)            │
│                                 │  HTTP   │                                 │
│  • Decides what/when to post    │ ──────▶ │  POST /api/marketing-jobs/      │
│  • Writes caption + hashtags    │  POST   │           enqueue               │
│  • Renders the video            │         │        │                        │
│                                 │         │        ▼                        │
│                                 │         │  job_queue (status=pending)     │
└─────────────────────────────────┘         │        │                        │
                                             │        ▼  next scheduler tick   │
                                             │  bots/tiktok/upload.py worker   │
                                             │        │                        │
                                             │        ▼                        │
                                             │  Saves as DRAFT on the phone    │
                                             └─────────────────────────────────┘
```

The endpoint lives in the **public** `gitd/` namespace (`gitd/routers/marketing_jobs.py`) so an external caller can drive Ghost without depending on the premium plugin.

## The one rule: draft-only

This is the whole safety model, and it is not configurable.

> No matter what you send, the job is saved as a **draft**. The seam has no permission to live-publish.

In `enqueue_marketing_job()`, the config's `action` is hard-overridden to `"draft"`:

```python
# gitd/routers/marketing_jobs.py
config = {
    "video": req.video_path,
    "caption": req.caption,
    "hashtags": req.hashtags,
    "action": "draft",          # ← forced, ignores req.action
}
```

If a caller explicitly passes `action="publish"`, the request still succeeds — but the attempt is logged as a warning and the job is saved as a draft anyway:

```python
if req.action and req.action.lower() != "draft":
    logger.warning(
        "marketing_jobs.enqueue: rejecting action=%r from external caller; "
        "saving as draft instead", req.action,
    )
```

Going from draft → published is a separate, human-in-the-loop step. Live auto-publishing is intentionally *not* something an external agent can reach through this API.

## Request

`POST /api/marketing-jobs/enqueue`

| Field | Type | Required | Notes |
|---|---|---|---|
| `video_path` | string | ✅ | **Absolute** path to the video on the machine running Ghost. Validated to exist. |
| `phone_serial` | string | ✅ | ADB serial of the phone to post from. |
| `caption` | string | | Post caption. Default `""`. |
| `hashtags` | string | | Hashtag string. Default `""`. |
| `tts_text` | string | | If set, Ghost injects a text-to-speech voiceover into the video. |
| `account` | string | | Expected active TikTok account on the phone (sanity check). |
| `scheduled_at` | string (ISO) | | **Informational only** — the job runs ASAP on the next scheduler tick, not at this time. |
| `action` | string | | Ignored. Forced to `"draft"`. |

Validation is strict up front (`gitd/routers/marketing_jobs.py`):

- `video_path` must be **absolute** → `400` otherwise
- `video_path` must **exist** on disk → `400` otherwise
- `phone_serial` must be non-empty → `400` otherwise

## Response

```json
{
  "job_id": "ghost-job-42",
  "estimated_post_at": "2026-07-04T18:00:00Z",
  "action": "draft",
  "phone_serial": "YOUR_DEVICE_SERIAL"
}
```

`estimated_post_at` echoes back your `scheduled_at` — it is **not** enforced. `job_id` is the queue id you can watch in the [Scheduler](../scheduler/) view.

Under the hood the endpoint wraps `_enqueue_job(...)` with `job_type="post"`, `priority=2`, `trigger="marketing_agent"`, and a `max_duration_s` of 1800. The existing `bots/tiktok/upload.py` worker picks it up on the next scheduler tick.

## Example call

```bash
curl -X POST http://localhost:5055/api/marketing-jobs/enqueue \
  -H "Content-Type: application/json" \
  -d '{
    "video_path": "/home/me/renders/clip_042.mp4",
    "phone_serial": "YOUR_DEVICE_SERIAL",
    "caption": "Ghosts in the machine 👻",
    "hashtags": "#android #automation",
    "tts_text": "Meet Ghost, the open-source Android agent."
  }'
```

Ghost queues the draft, the worker opens TikTok on the phone, uploads the video, fills the caption, and stops at the draft screen.

## When to use

**Use the seam when:**
- You have an external orchestrator that decides content and just needs Ghost to put it on a phone
- You want a hard guarantee that automation can only ever *draft*, never publish
- You're integrating Ghost as the "device layer" under your own content pipeline

**Don't use the seam when:**
- You want to drive the phone interactively — use [Agent Chat](../dashboard/) or the [MCP Server](../mcp-server/) instead
- You need to publish automatically — by design, you can't; publishing stays manual
- The video isn't already rendered to a local file — this seam takes a finished file path, not a render request

## Related

- [Scheduler](../scheduler/) — the job queue this endpoint feeds; watch `ghost-job-*` runs here
- [MCP Server](../mcp-server/) — the richer, tool-based way external agents drive Ghost
- [ADB Device Control](../adb-device/) — the phone-hands layer that actually performs the upload
