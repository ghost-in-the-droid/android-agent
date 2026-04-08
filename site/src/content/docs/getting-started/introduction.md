---
title: "👻 Introduction"
description: What Ghost in the Droid is, how it works, and why it uses real phones for Android automation.
---

Ghost in the Droid is an Android automation platform with a skill ecosystem. It controls real Android phones over USB via ADB to automate app interactions — tapping, swiping, typing, reading screen elements, and navigating complex multi-step flows. What started as a TikTok marketing bot is now a general-purpose framework for building, sharing, and running Android app automation skills, with AI-powered skill creation and live device streaming.

## Why Real Phones?

Emulators are detectable. Apps like TikTok, Instagram, and WhatsApp fingerprint the runtime environment and flag automated actions from emulators. Ghost in the Droid uses **physical Android devices** connected over USB, which means:

- **No emulator detection** -- your actions come from a real device with a real IMEI, real sensors, and real carrier data
- **Production-identical behavior** -- app UI, timing, and network behavior match what real users see
- **Stealth mode** -- Gaussian tap jitter, variable swipe speed, and character-by-character typing simulate human interaction patterns

Emulator support is also available for development and testing, but production automation targets real hardware.

## How It Works

```
Your Python code / Dashboard / Scheduler
        |
        v
   Flask Server (113+ REST endpoints, port 5055)
        |
        v
   Device class (47+ methods wrapping ADB)
        |
        v
   ADB over USB --> Physical Android Phone
        |
        v
   App under automation (TikTok, Instagram, etc.)
```

Every interaction flows through the `Device` class, which wraps `adb shell` commands into a clean Python API. The server orchestrates jobs, the dashboard provides a visual control center, and the skill system packages automation into reusable, shareable units.

## Core Components

| Component | What It Does |
|-----------|-------------|
| **Device class** | 47+ methods: tap, swipe, type, stealth mode, XML parsing, screenshots, notifications |
| **Skill system** | Actions (atomic operations) + Workflows (sequences) + Elements (UI locators) packaged per app |
| **Dashboard** | 9-tab SPA: device management, skill browsing, scheduling, analytics, live streaming |
| **Scheduler** | Per-phone job queue with priority preemption, 6 job types, 30-second tick |
| **Skill Creator** | Split-screen LLM chat + live device stream for building skills visually |
| **App Explorer** | BFS discovery of app UI states, screenshots, and transition graphs |
| **Macro Recorder** | Record/replay action sequences with speed control |

## What's Included

The TikTok skill ships fully implemented as a reference:

- **13 actions**: open app, navigate, search, like, comment, follow, scroll, and more
- **3 workflows**: upload video (43-step flow), crawl users, publish draft
- **41 UI elements** with fallback locator chains (content_desc, text, resource_id, coordinates)

Verified on TikTok v44.3.3 across multiple physical devices.

## Architecture at a Glance

```
android-agent/
  run.py                    # Entry point -> http://localhost:5055
  gitd/         # All application code (54 Python files)
    server.py               # Flask API + scheduler (113 routes, ~4500 LoC)
    db.py                   # SQLite ORM (~2000 LoC, 20+ tables)
    bots/common/adb.py      # Device class (47+ methods)
    skills/                 # Skill packages (tiktok, base, instagram)
    agent/                  # LLM content planner
    static/dashboard.html   # Main SPA (9 tabs, ~400K)
  data/                     # Runtime data + SQLite DB
  tests/                    # Pytest suite (19 files)
```

## Key Design Decisions

1. **One job per phone** -- ADB can only automate one app at a time per device
2. **Subprocess execution** -- bots and skills run as subprocesses to keep the server responsive
3. **Pre/post conditions** -- every skill action validates device state before and after execution
4. **Draft-then-publish** -- videos upload as drafts first, then publish at scheduled time
5. **Element fallback chains** -- resilient to app updates (content_desc -> text -> RID -> coords)
6. **WAL-mode SQLite** -- concurrent reads from dashboard while scheduler writes
7. **Multi-backend LLM** -- OpenRouter, Claude, Ollama selectable per use case

## Next Steps

- [Installation](/getting-started/installation/) -- get Python, ADB, and a phone set up
- [Connect Your Phone](/getting-started/connect-phone/) -- USB debugging and authorization
- [Hello World](/getting-started/hello-world/) -- run your first automation in 5 minutes
