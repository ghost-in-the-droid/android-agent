# Job Scheduler — Feature Summary

## What It Does

Per-phone job queue with priority-based scheduling, preemption, timeout enforcement, and orphan recovery. Runs as a daemon thread inside the Flask server, ticking every 30 seconds to enqueue due scheduled jobs, launch pending work, and detect finished processes. All automation jobs (crawl, post, skill execution, app exploration) flow through this single scheduler.

## Current State

**Working:**
- 30-second scheduler tick loop (daemon thread)
- Per-phone job queues (one active job per device at a time)
- Priority-based preemption with 90-second grace period
- 7 job types supported
- Orphan detection and recovery (dead PIDs, server restart)
- Timeout enforcement with SIGTERM → SIGKILL escalation
- 24h timeline visualization in dashboard Scheduler tab
- Full job CRUD via REST API
- Log file capture per job (`/tmp/sched_job_<id>.log`)
- Job summary parsing from `[done]` markers in logs
- Protection: never preempts post/publish_draft jobs (interrupting corrupts state)

**Limitations:**
- Single active job per phone (no parallel jobs on same device)
- No retry-on-failure logic (jobs fail once and stay failed)
- No cron-style scheduling (only interval and daily-times)
- Preemption kills the entire subprocess (no graceful pause/resume)

## Architecture

```
scheduled_jobs table (recurring configs)
    │
    │  _scheduler_tick() every 30s (daemon thread)
    ▼
Step 0: Clean orphaned running jobs (dead PIDs not in _phone_procs)
    │   Archive completed orphans, kill timed-out orphans
    ▼
Step 1: Enqueue due scheduled jobs → job_queue (status='pending')
    │   _is_job_due() checks interval/daily_times against last run
    ▼
Step 2: _process_phone_queue() per device
    │   ├─ If no running job → launch highest-priority pending
    │   ├─ If running job finished → parse log summary, archive to job_runs
    │   └─ If higher-priority pending waiting >90s → preempt current
    ▼
Step 3: Check running jobs for timeout (max_duration_s)
    │   SIGTERM → wait 5s → SIGKILL if still alive
    ▼
Step 4: Detect externally finished processes → archive

State machine per job:
  pending → running → completed|failed|timeout|killed|preempted → archived to job_runs
```

## Job Types

| Type | Script | Default Timeout | Purpose |
|------|--------|----------------|---------|
| `crawl` | `bots/tiktok/scraper.py` | 900s | Hashtag/user crawling |
| `post` | `bots/tiktok/upload.py` | 900s | Video upload (draft/post) |
| `publish_draft` | `bots/tiktok/upload.py` | 900s | Publish existing draft |
| `skill_workflow` | `skills/_run_skill.py` | 900s | Run a skill workflow |
| `skill_action` | `skills/_run_skill.py` | 900s | Run a single skill action |
| `app_explore` | `skills/auto_creator.py` | 900s | BFS app exploration |
| `content_gen` | `agent/agent_core.py` | 3600s | LLM content planning |

## Files

| File | Purpose |
|------|---------|
| `gitd/server.py` | `_scheduler_tick()`, `_scheduler_loop()`, `_process_phone_queue()`, `_launch_scheduled_job()`, `_kill_scheduled_job()`, `_build_cmd()`, `_build_scheduled_cmd()`, `_content_plan_tick()` |
| `gitd/db.py` | `scheduled_jobs`, `job_queue`, `job_runs` tables; `enqueue_job()`, `finish_job()`, `archive_to_runs()`, `get_job_runs()` |
| `gitd/static/dashboard.html` | Scheduler tab (timeline, CRUD), Bot tab (quick-launch) |

## API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/schedules` | List all scheduled jobs with last/next run info |
| POST | `/api/schedules` | Create a scheduled job |
| PUT | `/api/schedules/<id>` | Update a scheduled job |
| DELETE | `/api/schedules/<id>` | Delete a scheduled job |
| POST | `/api/schedules/<id>/toggle` | Enable/disable a schedule |
| POST | `/api/schedules/<id>/run-now` | Manually trigger immediate run |
| GET | `/api/scheduler/status` | Per-phone status (running job, PID, pending count) |
| GET | `/api/scheduler/queue` | Current job queue (all statuses) |
| GET | `/api/scheduler/queue/<id>/logs` | Stream log lines for a job |
| POST | `/api/scheduler/queue/<id>/kill` | Kill a running/pending job |
| POST | `/api/scheduler/runs/<id>/restart` | Re-enqueue a completed/failed job |
| GET | `/api/scheduler/history` | All archived job runs |
| GET | `/api/scheduler/history/<id>/logs` | Logs for an archived run |
| GET | `/api/scheduler/timeline` | 24h timeline data (runs + upcoming schedules) |

## Database Tables

```sql
scheduled_jobs   -- Recurring job configs (name, type, phone, priority, schedule_type, interval/daily_times, config_json, max_duration_s)
job_queue        -- Active queue (pending/running jobs with PID, log_file, timestamps)
job_runs         -- Archived history (completed/failed/killed with duration, exit_code, error_msg)
```

## Key Constants

| Constant | Value | Purpose |
|----------|-------|---------|
| `_PREEMPT_GRACE_S` | 90 seconds | Wait this long before preempting a lower-priority job |
| Tick interval | 30 seconds | How often the scheduler checks all queues |
| Default `max_duration_s` | 900 (15min) | Per-job timeout if not overridden |

## Dashboard Integration

- **Scheduler tab:** 24h visual timeline (color-coded bars per job type), schedule CRUD form, recent runs table with filters, per-phone queue status indicators
- **Bot tab:** Quick-launch buttons for crawl/post that enqueue to the same job queue
- **Skill Hub tab:** Run workflow/action buttons enqueue `skill_workflow`/`skill_action` jobs

## Known Issues & TODOs

- [ ] No retry-on-failure (a failed crawl stays failed — must manually re-enqueue)
- [ ] No cron-style scheduling (e.g., "every Monday at 9am")
- [ ] Preemption kills subprocess hard — no graceful pause/resume mechanism
- [ ] Log files accumulate in `/tmp/` — no automatic cleanup
- [ ] No max concurrent jobs across all phones (could overwhelm the machine)
- [ ] `_phone_procs` dict is in-memory only — lost on server restart (orphan recovery handles this but with delay)
- [ ] Job priority 1 (highest) through 5 (lowest) but only 2 is commonly used
