---
title: "🖥️ Phone Farm"
description: Set up multiple physical phones with USB hubs, per-phone job scheduling, and parallel automation.
---

Ghost in the Droid supports multiple physical Android devices simultaneously. Each phone gets its own job queue, its own scheduler entries, and its own live stream. This guide covers hardware setup, multi-device configuration, and per-phone scheduling.

## Hardware Requirements

| Component | Recommendation | Notes |
|-----------|---------------|-------|
| USB hub | Powered 7+ port hub | Must be powered -- phones draw significant current |
| USB cables | Data-capable cables | Charge-only cables do not work with ADB |
| Phones | Any Android 5.0+ | Higher-end devices are faster (XML dumps, app transitions) |
| Host machine | Linux recommended | ADB is most stable on Linux; macOS works too |

## Connecting Multiple Devices

1. Plug all phones into the powered USB hub
2. Enable USB debugging on each phone (see [Connect Phone](/getting-started/connect-phone/))
3. Authorize each phone (accept the USB debugging prompt on each device)
4. Verify all devices are visible:

```bash
adb devices
# YOUR_DEVICE_SERIAL    device    (Phone 1)
# YOUR_DEVICE_SERIAL_2  device    (Phone 2)
# EMULATOR_SERIAL       device    (optional: emulator)
```

## Device Management in the Dashboard

Navigate to the **Phone Agent** tab to see all connected devices:

- Device serial, model, and nickname
- Online/offline status
- Live WebRTC stream per device
- Tap/type/back controls for remote interaction

Each device appears as a selectable option throughout the dashboard -- the Skill Hub, Bot tab, Scheduler, and Skill Creator all have device selector dropdowns.

## Per-Phone Job Scheduling

The scheduler enforces **one active job per phone**. Each device has its own queue, and jobs are processed independently.

### Create Per-Phone Schedules

```bash
# Phone 1: crawl every 4 hours
curl -X POST http://localhost:5055/api/schedules \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Phone 1 crawl",
    "job_type": "crawl",
    "device": "YOUR_DEVICE_SERIAL",
    "interval_minutes": 240,
    "params": {"query": "#Cat", "passes": 5},
    "max_duration_minutes": 30,
    "priority": 5
  }'

# Phone 2: upload every 6 hours
curl -X POST http://localhost:5055/api/schedules \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Phone 2 upload",
    "job_type": "post",
    "device": "YOUR_DEVICE_SERIAL_2",
    "interval_minutes": 360,
    "params": {"video_path": "/data/videos/latest.mp4"},
    "max_duration_minutes": 30,
    "priority": 3
  }'
```

### Priority and Preemption

Jobs have priority 1 (highest) through 5 (lowest). When a higher-priority job is pending and the current job has been running for over 90 seconds (grace period), the scheduler preempts the running job.

**Protected jobs:** `post` and `publish_draft` are never preempted (interrupting would corrupt the upload state).

### Scheduler Tick

The scheduler runs on a 30-second tick cycle:

1. Clean orphaned jobs (dead PIDs)
2. Enqueue due scheduled jobs
3. Process each phone's queue (launch, detect completion, preempt)
4. Check for timeouts (SIGTERM -> 5s -> SIGKILL)
5. Detect externally finished processes

## Running Tests Per Device

```bash
# Run full test suite on Phone 1
DEVICE=YOUR_DEVICE_SERIAL python3 -m pytest tests/ -v --tb=short

# Run specific test on Phone 2
DEVICE=YOUR_DEVICE_SERIAL_2 python3 -m pytest tests/test_04_crawl.py -v
```

The **Tests** tab in the dashboard also has a device selector for running pytest with screen recordings.

## Parallel Automation Patterns

### Divide Work by Function

```
Phone 1 (fast):      crawl + upload + publish
Phone 2 (steady):    skill workflows + app exploration
```

### Divide Work by Account

```
Phone 1: TikTok account A -> target audience X
Phone 2: TikTok account B -> target audience Y
```

### Divide Work by Schedule

Use the scheduler's daily_times feature to stagger work:

```bash
# Phone 1: morning crawl + evening publish
# Phone 2: afternoon skills + night exploration
```

## Monitoring

The **Scheduler** tab provides a 24-hour visual timeline showing all jobs across all phones. Color-coded bars indicate job type, and you can see which phone is running what at a glance.

Per-phone queue status is available via the API:

```bash
curl -s http://localhost:5055/api/scheduler/queue | python3 -m json.tool
```

## Emulator Support

Emulators appear as regular ADB devices and work with the same scheduling and job system. The `EmulatorManager` service provides lifecycle management (create, start, stop, delete AVDs) from the dashboard and API.

See [Emulator Support](/features/emulator/) for details on the EmulatorPool for parallel headless emulators.

## Troubleshooting

### Device drops offline

```bash
adb kill-server && adb start-server && adb devices
```

If a specific device goes offline, unplug and replug its USB cable. Some phones need USB mode set to "File transfer" mode.

### Hub power issues

If devices keep disconnecting, the USB hub may not supply enough power. Use a hub with external power supply rated for at least 2A per port.

### Jobs stuck after server restart

The scheduler's `_phone_procs` dict is in-memory. After a server restart, orphaned jobs are cleaned up on the next scheduler tick (within 30 seconds).

## Related

- [Scheduler](/features/scheduler/) -- full scheduler documentation
- [Stealth Mode](/guides/stealth/) -- avoid detection across multiple phones
- [Emulator Support](/features/emulator/) -- virtual devices for testing
