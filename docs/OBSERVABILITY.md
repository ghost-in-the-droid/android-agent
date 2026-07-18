# Observability — Langfuse

Trace every chat turn, tool call, and LLM generation. Two sources reporting to one Langfuse instance:

- **Mac backend** — `claude-code`, `ollama`, `anthropic` providers.
- **Android (Chaquopy)** — the `on-device` provider running Gemma via MediaPipe inside the app.

## Where it runs

Langfuse server **runs on the Mac**, not the phone. The phone is too constrained for Postgres + Next.js. Both sources emit HTTP events to the same Mac instance:

```
┌────────────────┐      ┌─────────────────────────────┐
│  Phone         │──────▶ Mac:3000 (Langfuse UI + API) │
│  Chaquopy      │      │   ↑                          │
│  on-device LLM │      │   │                          │
└────────────────┘      │   │                          │
                        │  Mac backend (claude-code,   │
                        │  ollama, anthropic) ─────────┤
                        └─────────────────────────────┘
```

## Quickstart — self-hosted (recommended)

```bash
# 1. Start a docker daemon (OrbStack, Docker Desktop, or Colima).
brew install --cask orbstack && open /Applications/OrbStack.app

# 2. Boot Langfuse + Postgres
docker compose -f docker-compose.langfuse.yml up -d

# 3. First-time setup
open http://localhost:3000
# → sign up (first user becomes admin, this is local-only)
# → create a project
# → Settings → API Keys → Create — copy public + secret keys

# 4. Paste into .env
LANGFUSE_PUBLIC_KEY=pk-lf-xxxxxxxx
LANGFUSE_SECRET_KEY=sk-lf-xxxxxxxx
LANGFUSE_HOST=http://localhost:3000

# 5. Restart the backend
.venv/bin/python run.py
```

## Quickstart — cloud (zero infra)

If you'd rather skip Docker:

```
LANGFUSE_PUBLIC_KEY=pk-lf-xxxxxxxx
LANGFUSE_SECRET_KEY=sk-lf-xxxxxxxx
LANGFUSE_HOST=https://cloud.langfuse.com
```

## Bringing it up after a reboot

The Mac backend, the SSH tunnel to wherever Langfuse runs, and the ADB
reverses don't auto-restart. After a Mac sleep/reboot or a USB
disconnect/reconnect, anything in that chain may need re-establishing.

If you're working in the **private `mono` repo**, there's a one-shot script
that handles all three:

```bash
./scripts/phone-up.sh        # idempotent bring-up (backend + tunnel + reverses)
./scripts/phone-status.sh    # read-only probe — pinpoints which layer is down
./scripts/phone-down.sh      # symmetric teardown
```

See `mono/docs/PHONE_DEV_SETUP.md` for details. If you're working from the
public repo only, the manual steps are below.

## Letting the phone reach the Mac instance

The on-device provider (`agent_chat_ondevice.py`) runs *inside the Android app* via Chaquopy. To make it report to the Mac's Langfuse:

```bash
# Option A: USB / wireless ADB — port-forward Mac:3000 onto phone:3000
adb -s <serial> reverse tcp:3000 tcp:3000
# Then on the phone, LANGFUSE_HOST=http://127.0.0.1:3000 just works.

# Option B: Same LAN — find Mac's LAN IP
ipconfig getifaddr en0
# e.g. 10.0.0.5  →  set LANGFUSE_HOST=http://10.0.0.5:3000 in the app's prefs
```

For Chaquopy, env vars are seeded from Android's SharedPreferences in `app/src/main/python/_env.py` (or however you bootstrap them) — surface a simple settings field for the Langfuse host.

## What gets traced

Per chat turn (one trace):
- **input** — user message
- **metadata** — `provider`, `model`, `device`, `source: mac|android`, `duration_s`
- **tags** — `[provider, source]` (filterable in UI)

Per tool call (one span):
- name `tool:<tool_name>` (e.g. `tool:get_screen_tree`, `tool:tap`)
- input — tool args
- output — tool result (truncated to 2000 chars)
- level `ERROR` if the tool returned an error

Per LLM call (one generation):
- model name
- input prompt
- output text
- token usage (input / output / total)
- cost (USD) where the provider exposes it

## Disabling

Just leave `LANGFUSE_PUBLIC_KEY` empty. All helpers become no-ops with zero overhead — no client is constructed.

## Files

- `gitd/services/observability.py` — singleton client + helpers (`trace_chat_turn`, `span_tool_call`, `record_generation`, `record_tool_result`).
- `gitd/services/agent_chat_claude_code.py` — wraps Mac-side claude-code provider.
- `gitd/services/agent_chat_ondevice.py` — wraps Android-side Chaquopy provider.
- `docker-compose.langfuse.yml` — Postgres + Langfuse v2 (single-container).
- `.env.example` — credential template.
