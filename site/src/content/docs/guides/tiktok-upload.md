---
title: "🎵 TikTok Upload Pipeline"
description: The complete 43-step ADB upload flow — draft tags, TTS, ad disclosure, hashtags, and scheduling.
---

The TikTok upload pipeline is a 43-step ADB automation that pushes a video to the device, opens TikTok's share intent, adds captions and hashtags, configures ad disclosure, and posts (or saves as a draft for scheduled publishing).

## Overview

```
Push video to device
  -> Share intent to TikTok
    -> Add text/TTS overlay
      -> Type caption + hashtags
        -> Configure ad disclosure
          -> Post or Save as Draft
            -> Tag draft with unique #zzdfXXXXXX for later identification
```

## Prerequisites

- Physical Android phone connected via USB
- TikTok v44.3.3 installed and logged in
- Video file on your computer (MP4, vertical preferred)

## Quick Start

### CLI

```bash
# Upload as draft (safest -- review before publishing)
python3 -m gitd.bots.tiktok.upload \
  /path/to/video.mp4 \
  --caption "Check this out!" \
  --hashtags "cat,aicat,trending" \
  --action draft

# Upload and post immediately
python3 -m gitd.bots.tiktok.upload \
  /path/to/video.mp4 \
  --caption "Amazing content" \
  --hashtags "viral,fyp" \
  --action post

# Upload with text-to-speech overlay
python3 -m gitd.bots.tiktok.upload \
  /path/to/video.mp4 \
  --caption "Listen to this!" \
  --inject-tts \
  --action draft
```

### REST API

```bash
curl -X POST http://localhost:5055/api/skills/tiktok/run \
  -H "Content-Type: application/json" \
  -d '{
    "workflow": "upload_video",
    "device": "YOUR_DEVICE_SERIAL",
    "params": {
      "video_path": "/path/to/video.mp4",
      "caption": "Check this out!",
      "hashtags": ["cat", "aicat"],
      "action": "draft"
    }
  }'
```

### Python

```python
from gitd.skills.tiktok import load
from gitd.bots.common.adb import Device

dev = Device()
skill = load()
wf = skill.get_workflow("upload_video", dev,
    video_path="/path/to/video.mp4",
    caption="Check this out!",
    hashtags=["cat", "aicat"],
    action="draft"
)
result = wf.run()
```

## The 43-Step Flow

The upload script (`bots/tiktok/upload.py`) performs these steps in sequence:

1. Push video to device via `adb push`
2. Send share intent to TikTok (`am start -a SEND -t video/mp4`)
3. Wait for TikTok editor to load
4. Dismiss any "Continue editing?" overlay if present
5. Wait for the "Next" button to appear
6. Tap "Next" to proceed to the caption screen
7. Clear any existing caption text
8. Type the caption text
9. Add each hashtag one by one (type `#tag`, wait for suggestion, tap suggestion)
10. Validate each hashtag was accepted in the XML
11. Navigate to "More options"
12. Toggle "Content disclosure" ON
13. Tap "Authorize" to confirm ad disclosure
14. Save disclosure settings
15. Close the disclosure panel
16. Tap "Post" or "Save to drafts" depending on `--action`

Steps 17-43 handle edge cases: popup dismissal, retry logic for failed hashtag suggestions, draft-tag generation, account verification, and cleanup.

## Draft Tags

When saving as a draft, the system generates a unique hashtag in the format `#zzdfXXXXXX` (6 random hex chars). This tag serves as a reliable identifier to find the draft later, since TikTok doesn't expose draft IDs via the UI.

```python
# Find a specific draft by its tag
dev.go_to_drafts_screen()
xml = dev.dump_xml()
# Search for the draft-tag in the XML to locate the correct draft
```

Draft management methods:

- **Count drafts** -- navigate to drafts screen, count grid items
- **Find by tag** -- search draft descriptions for the `#zzdf` tag
- **Publish draft** -- open draft, tap publish, confirm
- **Delete draft** -- open draft, tap delete, confirm

## Ad Disclosure

TikTok requires ad disclosure for branded content. The upload flow handles this automatically:

1. Tap "More options" below the caption
2. Toggle "Content disclosure" to ON
3. Tap "Authorize" in the confirmation dialog
4. Tap "Save" to confirm
5. Close the panel and return to the post screen

## Scheduling (Draft-then-Publish)

The recommended workflow for scheduled posts:

1. Upload as draft with `--action draft`
2. Create a scheduler entry for `publish_draft` at the desired time
3. The scheduler will find the draft by its tag and publish it

```bash
# Create a schedule to publish at 6 PM daily
curl -X POST http://localhost:5055/api/schedules \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Publish 6PM",
    "job_type": "publish_draft",
    "device": "YOUR_DEVICE_SERIAL",
    "schedule_type": "daily_times",
    "daily_times": ["18:00"],
    "params": {"draft_tag": "zzdf1a2b3c"}
  }'
```

## Content Pipeline Integration

The full automated pipeline:

```
LLM Agent plans content (styles, captions, schedule times)
  -> Video ready (generated or provided)
    -> ADB draft upload with #zzdf tag
      -> Scheduler publishes at planned time
        -> Post analytics scraper captures metrics
```

Launch the full pipeline:

```bash
# Plan 3 days of content (dry run first)
python3 -m gitd.agent.agent_core --days 3 --dry-run

# Execute for real
python3 -m gitd.agent.agent_core --days 3
```

## Troubleshooting

### Upload fails at hashtag step

TikTok's hashtag suggestion dropdown can interfere. Each hashtag is validated in the XML before proceeding. Try shorter, more popular hashtags.

### "Continue editing?" popup

This invisible overlay appears when TikTok was killed mid-edit. The script detects it via pixel scanning for the red Edit button. `restart_tiktok()` handles this automatically.

### Draft-tag visible on published post

The `#zzdfXXXXXX` tag is intentionally added to drafts for identification. It should be removed before publishing. The `publish_draft` workflow handles this automatically.

## Related

- [Scrape Profiles](/guides/scrape-profiles/) -- find influencers to repost
- [Macros](/guides/macros/) -- record and replay custom workflows
- [Scheduler](/features/scheduler/) -- automate the publish schedule
