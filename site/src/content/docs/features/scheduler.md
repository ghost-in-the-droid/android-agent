---
title: "⏰ Scheduler"
description: Per-phone job queue with priority preemption, timeout enforcement, and 24-hour timeline visualization.
---

The scheduler manages all automation jobs across all connected phones. It runs as a daemon thread inside the Flask server, ticking every 30 seconds to enqueue, launch, monitor, and clean up jobs.

## How It Works

```
scheduled_jobs table (recurring configs)
    |
    |  _scheduler_tick() every 30s
    v
Step 0: Clean orphaned running jobs (dead PIDs)
    v
Step 1: Enqueue due scheduled jobs -> job_queue (status='pending')
    v
Step 2: Process each phone's queue
    |  - No running job? -> launch highest-priority pending
    |  - Running job finished? -> parse log, archive to job_runs
    |  - Higher-priority waiting >90s? -> preempt current
    v
Step 3: Check running jobs for timeout
    |  SIGTERM -> wait 5s -> SIGKILL if still alive
    v
Step 4: Detect externally finished processes -> archive
```

## Job Types

| Type | Script | Default Timeout | Purpose |
|------|--------|----------------|---------|
| `crawl` | `bots/tiktok/scraper.py` | 900s (15min) | Hashtag/user crawling |
| `post` | `bots/tiktok/upload.py` | 900s | Video upload |
| `publish_draft` | `bots/tiktok/upload.py` | 900s | Publish existing draft |
| `skill_workflow` | `skills/_run_skill.py` | 900s | Run a skill workflow |
| `skill_action` | `skills/_run_skill.py` | 900s | Run a single action |
| `app_explore` | `skills/auto_creator.py` | 900s | BFS app exploration |

## Creating Schedules

### Via API

```bash
curl -X POST http://localhost:5055/api/schedules \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Daily cat crawl",
    "job_type": "crawl",
    "device": "YOUR_DEVICE_SERIAL",
    "interval_minutes": 1440,
    "params": {"query": "#Cat", "tab": "top", "passes": 5},
    "max_duration_minutes": 30,
    "priority": 5
  }'
```

### Schedule Types

- **Interval** -- run every N minutes (`interval_minutes`)
- **Daily times** -- run at specific times each day (`daily_times: ["09:00", "18:00"]`)

### Priority

Priority ranges from 1 (highest) to 5 (lowest). Higher-priority jobs can preempt lower-priority ones after the grace period.

## Preemption

When a higher-priority job is pending and the current job has been running for more than 90 seconds:

1. Scheduler sends SIGTERM to the running process
2. Waits 5 seconds
3. Sends SIGKILL if still alive
4. Launches the pending higher-priority job

**Protected jobs:** `post` and `publish_draft` are never preempted (interrupting would corrupt the upload state).

## API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/schedules` | List all scheduled jobs |
| POST | `/api/schedules` | Create a scheduled job |
| PUT | `/api/schedules/<id>` | Update a schedule |
| DELETE | `/api/schedules/<id>` | Delete a schedule |
| POST | `/api/schedules/<id>/toggle` | Enable/disable |
| POST | `/api/schedules/<id>/run-now` | Trigger immediate run |
| GET | `/api/scheduler/status` | Per-phone status (running job, PID, pending count) |
| GET | `/api/scheduler/queue` | Current job queue |
| GET | `/api/scheduler/queue/<id>/logs` | Stream log lines |
| POST | `/api/scheduler/queue/<id>/kill` | Kill a job |
| POST | `/api/scheduler/runs/<id>/restart` | Re-enqueue a completed/failed job |
| GET | `/api/scheduler/history` | Archived job runs |
| GET | `/api/scheduler/history/<id>/logs` | Logs for archived run |
| GET | `/api/scheduler/timeline` | 24h timeline data |

## Job State Machine

```
pending -> running -> completed | failed | timeout | killed | preempted
                                    \-> archived to job_runs table
```

## Database Tables

```sql
scheduled_jobs   -- Recurring configs (name, type, phone, priority, interval/daily_times, params)
job_queue        -- Active queue (pending/running with PID, log_file, timestamps)
job_runs         -- Archived history (exit_code, duration, error_msg)
```

## Dashboard Integration

The **Scheduler** tab shows:

- **24h Timeline** -- visual bars per phone, color-coded by job type
- **Schedules Panel** -- CRUD form for creating/editing schedules
- **Recent Runs** -- filterable table of completed jobs with status, duration, exit code
- **Queue Status** -- per-phone indicators showing running job and pending count

The **Bot** tab's quick-launch buttons also enqueue to the same job queue.

## Key Constants

| Constant | Value | Purpose |
|----------|-------|---------|
| Tick interval | 30 seconds | How often scheduler checks all queues |
| `_PREEMPT_GRACE_S` | 90 seconds | Minimum runtime before preemption |
| Default `max_duration_s` | 900 (15min) | Per-job timeout |
| Kill escalation | 5 seconds | SIGTERM -> SIGKILL delay |

## Monitoring

```bash
# Per-phone status
curl -s http://localhost:5055/api/scheduler/status | python3 -m json.tool

# Job queue
curl -s http://localhost:5055/api/scheduler/queue | python3 -m json.tool

# Job history
curl -s http://localhost:5055/api/scheduler/history?limit=20 | python3 -m json.tool
```

## Troubleshooting

### Jobs stuck in "running"

If a subprocess crashes without cleanup, the scheduler detects the dead PID on its next tick (30 seconds). You can also kill manually:

```bash
curl -X POST http://localhost:5055/api/scheduler/queue/<id>/kill
```

### Jobs not starting

Check: does the schedule exist? Is it enabled? Is `interval_minutes` correct? Is another job already running on that phone?

### After server restart

The `_phone_procs` dict is in-memory and lost on restart. Orphaned jobs are cleaned up on the next tick via PID checking.

## Related

- [Phone Farm](/guides/phone-farm/) -- multi-device scheduling
- [Skill System](/features/skill-system/) -- skill_workflow and skill_action job types
- [API: REST Endpoints](/api/rest-endpoints/) -- all 90+ endpoints
