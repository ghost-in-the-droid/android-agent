---
title: "💻 CLI Reference"
description: Command-line usage for run.py, bot scripts, pytest, skill execution, and environment variables.
---

Ghost in the Droid is operated primarily through Python scripts, the Flask server, and pytest. This page covers all CLI entry points.

## Starting the Server

```bash
python3 run.py
```

Starts the Flask server on `http://localhost:5055` with the scheduler daemon thread, all API endpoints, and the dashboard.

For debug mode:

```bash
python3 -c "from gitd.server import app; app.run(host='0.0.0.0', port=5055, debug=True)"
```

## Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `DEVICE` | If multiple phones | Default ADB serial |
| `OPENAI_API_KEY` | For LLM features | OpenAI API key |
| `ANTHROPIC_API_KEY` | For Claude backend | Anthropic API key |
| `OPENROUTER_API_KEY` | For LLM features | OpenRouter API key |

## Bot Scripts

All bot scripts are in `gitd/bots/tiktok/` and can be run directly.

### Influencer Crawling

```bash
# Crawl top tab
python3 -m gitd.bots.tiktok.scraper "#Cat" \
  --tab top --date-filter "Past 24 hours" --passes 5

# Crawl users tab
python3 -m gitd.bots.tiktok.scraper "#Dog" \
  --tab users --passes 3
```

| Flag | Default | Description |
|------|---------|-------------|
| `query` | required | Hashtag to search |
| `--tab` | `top` | Search tab (top, users) |
| `--date-filter` | None | Time filter |
| `--passes` | 3 | Scroll passes |
| `--sort` | Relevance | Sort order |

### Video Upload

```bash
# Upload as draft
python3 -m gitd.bots.tiktok.upload /path/to/video.mp4 \
  --caption "Check this out!" --hashtags "cat,aicat" --action draft

# Upload and post immediately
python3 -m gitd.bots.tiktok.upload /path/to/video.mp4 \
  --caption "Amazing!" --hashtags "viral,fyp" --action post

# Upload with TTS
python3 -m gitd.bots.tiktok.upload /path/to/video.mp4 \
  --caption "Listen!" --inject-tts --action draft
```

### Continuous Crawling

```bash
python3 -m gitd.bots.tiktok.crawl_runner
```

Rotates through all hashtags in the database, picking the least-recently-crawled each time.

### LLM Content Planner

```bash
# Dry run (plan only, no generation)
python3 -m gitd.agent.agent_core --days 3 --dry-run

# Live run
python3 -m gitd.agent.agent_core --days 3 --posts-per-day 3
```

## App Explorer

```bash
python3 -m gitd.skills.auto_creator \
  --package com.zhiliaoapp.musically \
  --device YOUR_DEVICE_SERIAL \
  --max-depth 3 --max-states 20 --settle 1.5
```

| Flag | Default | Description |
|------|---------|-------------|
| `--package` | required | Android package name |
| `--device` | required | ADB serial |
| `--max-depth` | 3 | BFS depth |
| `--max-states` | 20 | Max unique states |
| `--settle` | 1.5 | Seconds after each tap |
| `--output` | auto | Output directory |

## Skill Execution

```bash
python3 -m gitd.skills._run_skill \
  --skill tiktok \
  --workflow upload_video \
  --device YOUR_DEVICE_SERIAL \
  --params '{"video_path": "/tmp/video.mp4"}'
```

This is what the scheduler calls internally for `skill_workflow` and `skill_action` jobs.

## Running Tests

```bash
# Full test suite
DEVICE=YOUR_DEVICE_SERIAL python3 -m pytest tests/ -v --tb=short

# Specific test file
python3 -m pytest tests/test_04_crawl.py -v

# On a different device
DEVICE=YOUR_DEVICE_SERIAL_2 python3 -m pytest tests/ -v
```

### Test Files

| Test | What It Does | Requires |
|------|-------------|----------|
| `test_00_baseline` | Verify correct TikTok account | TikTok logged in |
| `test_01_accounts` | Account switching | 2+ TikTok accounts |
| `test_02_draft` | Upload video as draft | Video file |
| `test_03_post` | Live post (skipped by default) | Video file |
| `test_04_crawl` | Scrape by hashtag | TikTok access |
| `test_08_draft_publish` | Publish a draft | Existing draft |

## Related

- [Installation](/getting-started/installation/) -- setup prerequisites
- [API: REST Endpoints](/api/rest-endpoints/) -- HTTP API reference
- [Scheduler](/features/scheduler/) -- how jobs are managed
