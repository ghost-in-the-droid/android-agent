---
title: "Ghost Bench"
description: A built-in, dependency-free benchmark that measures how well an agent + model actually drives a real Android device. Objective ADB-verified pass/fail — no LLM judge.
---

Ghost Bench is the built-in benchmark suite for answering one question: **does this provider + model combination actually get things done on a phone?** It gives the agent a natural-language goal, lets it drive a real device, and then checks the device state over ADB to decide pass or fail.

## What it measures

End-to-end **task success** on a real Android device or emulator. Not token counts, not vibes — for each task the agent must reach a goal state that is then verified **objectively via `adb shell`**. There is no model-as-judge: grading is a deterministic device-state check, so runs are reproducible and comparable.

Scoring is binary per task (1.0 or 0.0). A run's headline number is the **success rate** = mean of the per-task scores.

## The tasks

Ghost Bench 1.0 ships **14 tasks in 2 categories**. Tasks are defined as **JSON data** (`gitd/benchmarks/ghost_bench/task_data/*.json`), not code — adding one is just another JSON object.

### Navigation (6 tasks) — "open the X app"

`OpenAppSettings` · `OpenAppContacts` · `OpenAppClock` · `OpenAppCamera` · `OpenAppChrome` · `OpenAppCalculator`

Verified by inspecting the resumed activity (`dumpsys activity activities`) and checking it belongs to the target app.

### Settings (8 tasks) — "change a system setting"

`SystemWifiTurnOn` · `SystemWifiTurnOff` · `SystemBluetoothTurnOn` · `SystemBluetoothTurnOff` · `SystemBrightnessMax` · `SystemBrightnessMin` · `SystemAirplaneModeOn` · `SystemAirplaneModeOff`

Verified by reading the actual setting back (e.g. `settings get global wifi_on`).

Each task carries a `complexity` (settings toggles are `1.0`, airplane-mode is `1.5`) which drives an advisory `max_steps = complexity × 10`.

## How a run works

The runner (`gitd/benchmarks/runner.py`) executes the selected tasks **sequentially**. For each task:

```
1. reset_device      → two HOME keyevents, settle
2. initialize_task   → run the task's init cmd over ADB to set preconditions
                       (e.g. `svc wifi disable` before a "turn wifi on" task —
                        so the goal is never already satisfied)
3. run agent         → POST the goal to /api/agent-chat/message and stream
                       the agent's tool calls until it finishes
4. evaluate_task     → run the task's eval cmd over ADB, compare to expected
                       → score 1.0 / 0.0 + reason
5. save              → persist the run after every task (incremental)
```

A task's grader uses one of three checks against the ADB command output: exact match (`expect`), membership (`expect_in` — e.g. wifi-on accepts both `"1"` and the transient `"2"`), or case-insensitive substring (`expect_contains`, used for activity names).

Preconditions matter: a task deliberately puts the device in the *opposite* state first, so "turn wifi on" only passes if the agent genuinely turned it on.

## Running it

### From the dashboard (primary)

Open the **📊 Benchmarks** tab. Under **Tasks**, pick a `provider`, `model`, and `device`, select tasks (or *Run All*), and start. A live SSE log and device stream show progress; the **Runs** tab keeps history with expandable per-task agent logs.

The UI offers the same providers as [Agent Chat](../llm-providers/) — `claude-code` (sonnet/opus/haiku), `anthropic`, `openrouter`, and locally-discovered `ollama` models.

### From the API

```bash
# Start a run
curl -X POST http://localhost:5055/api/benchmarks/runs \
  -H "Content-Type: application/json" \
  -d '{
    "suite": "ghost_bench",
    "provider": "ollama",
    "model": "gemma3:4b",
    "device": "emulator-5554"
  }'
# → { "ok": true, "run_id": "a1b2c3d4", ... }

curl -s http://localhost:5055/api/benchmarks/runs/a1b2c3d4      # full results
```

Omit `tasks` to run the whole suite, or pass a list of task ids to run a subset. Live progress streams from `GET /api/benchmarks/runs/{id}/events` (SSE).

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/benchmarks/suites` | List suites (`ghost_bench`) |
| `GET` | `/api/benchmarks/tasks` | List tasks (filter by `suite`, `category`) |
| `POST` | `/api/benchmarks/runs` | Start a run |
| `GET` | `/api/benchmarks/runs` | All runs (active + saved) |
| `GET` | `/api/benchmarks/runs/{id}` | One run: per-task scores, logs, totals |
| `POST` | `/api/benchmarks/runs/{id}/stop` | Cooperative stop |
| `GET` | `/api/benchmarks/runs/{id}/events` | Live SSE progress |

## Comparing configs and models

There's no magic diff endpoint — you compare by **running the same tasks under different `provider`/`model` and reading each run's `success_rate`**. Every run records its own model, provider, device, `passed`/`total_tasks`, and `total_time_s`, and they all sit together in the Runs list, so a Sonnet run and a `gemma3:4b` run on the identical 14 tasks are directly comparable. This is the intended workflow for "is the cheaper local model good enough here?"

Results are persisted as one JSON file per run under `gitd/benchmarks/results/{run_id}.json` (git-ignored — local to your machine), holding the full run plus every task's agent log.

## When to use / when NOT to use

**Use Ghost Bench when:**
- You're choosing a provider/model and want a real number, not a guess
- You changed the agent loop, prompt, or a tool and want a regression check
- You want reproducible, objective pass/fail rather than eyeballing chats

**Don't lean on it when:**
- You need broad app coverage — it's 14 system/navigation tasks, not a full app-automation suite. For that, we ship [AndroidWorld](https://github.com/google-research/android_world) support alongside Ghost Bench — early result: **115 of 116 tasks passed (99.1%)** driven by Claude Code, on the unmodified upstream harness. Treat as a preview; full trajectories and methodology writeup coming.
- You need partial credit — scoring is strictly binary
- You expect a hard step cap — `max_steps` is **advisory only**; the runner doesn't abort a task at that count (the 300s per-task HTTP timeout is the real ceiling)

## Gotchas

- **Binary scoring, mean = success rate.** No partial credit; a task 90% done still scores 0.
- **`max_steps` is informational**, surfaced in the API/UI but not enforced by the runner.
- **Objective grading only sees what `adb shell` can read** — reliable, but limited to inspectable device state.
- **Runs execute in a daemon thread.** A server restart mid-run loses the in-memory run; only tasks already saved to disk persist (with status still `running`).
- **Sequential, with ~3s of fixed settles per task** — a full 14-task run is not instant.

## Related

- [LLM Providers](../llm-providers/) — the providers/models you benchmark against each other
- [On-Device LLM](../on-device-llm/) — benchmark Gemma running on the phone vs a cloud model
- [Tracing](../tracing/) — every benchmark turn is also captured as a trace for deep debugging
