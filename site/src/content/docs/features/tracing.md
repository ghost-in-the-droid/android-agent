---
title: "Tracing & Observability"
description: Every agent turn is recorded — the prompt, each tool call, tokens, cost, and timing. Local SQLite by default, optional Langfuse for a visual UI. Nothing to enable.
---

⭐ **New in 1.3** — Ghost records a **trace** for every chat turn and a **span** for every tool call and LLM generation inside it. It's always on, it's local, and it can't break a chat turn.

## The model: traces and spans

- A **trace** is one round-trip: user message → final answer (a "turn").
- A **span** is one step inside that trace — either a **tool call** (`tap`, `get_screen_tree`, `web_search`…) or an **LLM generation**.

So a turn where the agent reads the screen, taps twice, then answers becomes one trace with four spans (three tool + one generation), each timed, with inputs, outputs, and token counts attached.

```
Trace  (provider=claude-code, model=sonnet, device=R9PT…, status=success, 6.2s)
 ├─ span  generation  llm-call            in=4120  out=88   1.9s
 ├─ span  tool        tool:get_screen_tree                  0.4s
 ├─ span  tool        tool:tap                              0.3s
 └─ span  generation  llm-call            in=4310  out=45   1.4s
        ↳ trace totals: input_tokens, output_tokens, cost_usd accumulated across all generations
```

## Two backends, one API

Every provider calls the same handful of helpers in `gitd/services/observability.py`; the helpers write to one or both backends:

| Backend | When it's active | What it's for |
|---|---|---|
| **Local SQLite** | **Always on** — no config | Offline-safe recording; powers the `/api/traces` inspector API. Tables `traces` + `trace_spans`. |
| **[Langfuse](https://langfuse.com/)** | Opt-in — set `LANGFUSE_PUBLIC_KEY` + `LANGFUSE_SECRET_KEY` | A full visual trace UI, cross-device aggregation, eval scoring. |

Both receive the same trace shape, so turning Langfuse on is purely additive — local recording keeps happening either way.

> **Observability never crashes a turn.** Every DB write and every Langfuse call is wrapped in a swallow-and-continue guard (`observability.py`). If tracing fails, the agent turn proceeds as if it weren't there.

## What gets recorded

The `traces` table (`gitd/models/trace.py`) captures, per turn:

`provider` · `model` · `device` · `source` (`mac` or `android`) · `user_input` · `final_output` · `status` (`running` / `success` / `error` / `stopped`) · `error_text` · `input_tokens` · `output_tokens` · `cost_usd` · `duration_ms` · `started_at` · `ended_at`.

Each `trace_spans` row adds: `kind` (`tool` / `generation`) · `name` (e.g. `tool:web_search`, `llm-call`) · `input_json` · `output_json` · `level` (`DEFAULT` / `ERROR`) · timing.

Token totals are **accumulated**, not overwritten: `record_generation()` sums each LLM call's usage into the trace so multi-call turns (like an on-device Gemma tool loop) report a correct grand total.

## Inspecting traces — the REST API

The inspector surface is a REST API under `/api/traces` (`gitd/routers/traces.py`). It's the way to read what the agent did:

| Method | Path | Returns |
|---|---|---|
| `GET` | `/api/traces` | Recent traces, newest-first — filter by `provider`, `source`, `status`, `conversation_id`; `limit` (≤500) / `offset` |
| `GET` | `/api/traces/{id}` | One trace + all its spans (full inputs/outputs) |
| `GET` | `/api/traces/stats` | Aggregates over `since_hours` (default 24): total, errors, success rate, avg duration, total cost, tokens, breakdown by provider |
| `DELETE` | `/api/traces/{id}` | Delete one trace (spans cascade) |
| `DELETE` | `/api/traces` | Clear everything (debug) |

```bash
# Last 24h at a glance
curl -s http://localhost:5055/api/traces/stats | python3 -m json.tool

# Most recent failing turns
curl -s "http://localhost:5055/api/traces?status=error&limit=10"

# Full detail (every span) for one turn
curl -s http://localhost:5055/api/traces/<trace_id>
```

:::note
There is **no dedicated "Traces" tab in the dashboard yet** — trace inspection today is via this REST API, or visually through the Langfuse UI (below). The `/api/traces` responses are already shaped for a future in-app viewer.
:::

## Visual traces with Langfuse (optional)

For a click-through UI — flame graphs, per-span drill-down, eval scores — point Ghost at [Langfuse](https://langfuse.com/). A one-container stack ships in the repo:

```bash
docker compose -f docker-compose.langfuse.yml up -d   # Langfuse v2 + Postgres, UI on :3000
```

Then set the keys and restart Ghost:

```bash
export LANGFUSE_PUBLIC_KEY=pk-lf-...
export LANGFUSE_SECRET_KEY=sk-lf-...
export LANGFUSE_HOST=http://localhost:3000   # default
```

With keys present, each turn is mirrored to Langfuse as a trace named `chat:<provider>`, generations named `llm-call` with token usage, and tags for provider/source. Leave the keys empty and the Langfuse path is skipped entirely — local SQLite tracing continues unaffected.

On-device Gemma running inside the Ghost APK reports too (`source=android`); the phone reaches a Langfuse server on your machine via `adb reverse tcp:3000 tcp:3000`.

## How to debug an agent with it

1. Reproduce the bad turn in [Agent Chat](../dashboard/).
2. `GET /api/traces?limit=1` to grab the newest trace id.
3. `GET /api/traces/{id}` and read the spans in order — you see the exact tool inputs the model chose, each tool's output, and where `level` flips to `ERROR`.
4. Check the generation spans' `input_json` to see the prompt the model actually received (the KV-cache prefix, tool list, screen state) — most "why did it do that?" questions are answered here.

Because every tool call's args and result are captured, a mis-tap or a tool that returned junk is visible without adding a single `print`.

## Gotchas

- **Local tracing is unconditional.** Older notes in `docs/OBSERVABILITY.md` describe tracing as "no-ops unless Langfuse is configured" — that's stale; local SQLite recording always runs.
- **Row sizes are truncated** to keep the DB lean (user input ~8K chars, final output ~16K, tool results ~4K). Full untruncated payloads aren't retained.
- **`conversation_id` is a soft link** (no foreign key) — a trace opens before its conversation row is saved, so joins are best-effort.
- **The bundled Langfuse compose uses dev-only secrets** (`NEXTAUTH_SECRET` / `SALT`) — change them before exposing it anywhere real.

## Related

- [LLM Providers](../llm-providers/) — the `provider` / `model` recorded on every trace
- [On-Device LLM](../on-device-llm/) — traces from Gemma running on the phone (`source=android`)
- [MCP Server](../mcp-server/) — every tool call you see as a span comes from this tool set
