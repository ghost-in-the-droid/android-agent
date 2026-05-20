# On-device parser + Gemma chat template + stop-fix + WIP vLLM provider

Python-side companion to the app's `feature/llama-cpp-vulkan-adreno` PR.
Everything here is provider/agent-loop work: tool-call parsing, prompt
template, KV cache hashing, multi-turn coherence, and the stop button.

## Companion PR

- `ghost-app` → `feature/llama-cpp-vulkan-adreno` (the Kotlin / JNI / Gradle
  side; carries this submodule bump)

## Commits

| Commit | What |
|---|---|
| `fe17427` | Gemma chat template (`<start_of_turn>` markers) + DeviceActions Python wiring + n_ctx=4096 |
| `d869a6f` | Stream-side protocol: empty piece ≠ EOS (needed for JNI hold-back) |
| `c1823b7` | Chat path loads disk-persist KV cache before generateStart |
| `64769e9` | Rename `gemma-4-e2b-gguf` → `gemma-4-e2b-q4km-gguf` |
| `2096c08` | **Stop button actually stops claude** (orphan subproc fix) |
| `06fea2f` | WIP: vLLM provider for jsl-gpu via SSH tunnel + adb reverse |

## The big-deal fixes

### 1. Gemma chat template

Was using a custom `[SYSTEM]/[USER]/[ASSISTANT]` scaffold the model had
never seen in training. Gemma cheerfully echoed those markers back inside
its own replies, then started hallucinating fake follow-up turns. Result:
"`com.android.settings, com.android.settings, com.android.settings, ...`"
× hundreds, eventual context overflow on turn 7.

Switched to canonical `<start_of_turn>user / model / <end_of_turn>`.
Single source of truth via `ondevice_stable_prefix(system, device)` so
the warmup endpoint and the chat path can never drift apart. Multi-turn
coherence holds for 6+ turns now (verified live on Snapdragon 888).

### 2. Stop button propagates across the phone↔Mac boundary

Phone's `_chat_claude_code_remote` is a proxy: phone hits its own
`/api/agent-chat/message` → that hits Mac's same endpoint → Mac spawns
`claude` CLI. Two separate session ids. When the user hit Stop on the
phone, the phone-side stop fired against the phone's own session_id —
but the claude subprocess lives on the Mac under a different session.
Mac's `send_message` generator was blocked in `iter_lines()` waiting for
claude's next chunk, so it didn't notice the broken pipe until claude
had emitted 3-5 more tool calls. Multiple stops accumulated multiple
runaway claudes fighting each other for phone control.

Fix is layered:

- Phone-side proxy captures Mac's session_id from the first SSE `session`
  event and on `GeneratorExit` POSTs `/stop/{remote_sid}` to Mac before
  the connection dies.
- Mac-side `chat_claude_code` spawns claude with `start_new_session=True`
  so it has its own pgid, then registers the `Popen` in `_active_procs`.
- `stop_agent` does `killpg(SIGTERM)` → wait 2s → `killpg(SIGKILL)`,
  wiping claude + node + MCP-tool children together. Nuclear pkill kept
  as safety net.

Verified live: Stop now halts within ~1 s instead of letting claude run
wild for 30+ seconds.

### 3. Chat path loads disk-persist KV cache

Previously only the warmup endpoint loaded it. The chat path's
`generateStart` saw an empty KV and paid a full cold prefill (~4 min on
Q5_K_M) on every first chat call after a model switch. Now both callers
share `_ensure_kv_warmed()` so the cache file lands the same way.

### 4. Tool-call parser handles model slop

Three layers, applied in order:

1. `tool` / ` ```json ` fenced block parse
2. Inline `{...}` scan with `_attempt_repairs` (doubled-brace collapse,
   trailing-junk strip, balanced-brace truncation)
3. **NEW**: global `{{ ` → `{` flatten + re-scan if both prior passes
   missed (Gemma at temp 0 routinely emits inline doubled braces with
   mismatched closing counts that the step-2 regex couldn't match)

Plus action-schema (`{"action_type": "open_app", "app_name": "X"}`)
translation for ghost-gemma-style trained outputs.

### 5. launch_app: package verifier + Chaquopy bridge

Was failing two ways on-phone:

1. Model hallucinated package names (`com.reddit.android` when reality
   was `com.reddit.frontpage`). `monkey` returns 0 for missing packages,
   so the agent thought it succeeded.
2. `monkey` and `am force-stop` both require permissions uid 10030 doesn't
   have. Both fall back silently from host adb (uid 2000 shell) which
   masked the bug during dev.

Fix: verify the package exists first (returns "Did you mean: X?" hint),
then call into `DeviceActions.launchApp()` via the Chaquopy `jclass`
bridge — uses the app's own `Context.startActivity()` which doesn't
need cross-user permissions. Falls back to the `am start` path when
Chaquopy isn't available (host-side dev runs).

## Numbers

End-to-end first-turn UX, gemma-4-e2b-q4km-gguf on Snapdragon 888:

| Phase | Tokens | ms |
|---|---:|---:|
| App cold launch → daemon ready | — | ~15 000 |
| KV restore from disk (warmup-d5e... or warmup-c7b7...) | 1263 | 155 |
| Prefill turn 1 (KV cache hit + user msg diff) | ~50 new | 6 000 – 13 000 |
| Decode turn 1 | 30–90 | 7 000 – 22 000 |

## Untested / WIP

- **vLLM provider** (`06fea2f`): code-complete (full multi-turn loop,
  OpenAI conversation-history wiring, tool dispatch, helpful error
  messages) but never run against a live vLLM server. Doesn't affect
  any existing provider. Verification path documented in the commit
  message.

## How to verify

Without vLLM, on a real phone:

```bash
# Mac side
cd android-agent && source .venv/bin/activate
uvicorn gitd.app:app --port 15055 --host 127.0.0.1 &
adb reverse tcp:15055 tcp:15055
adb reverse tcp:3000 tcp:3000  # optional, for Langfuse tracing

# Phone side — the bundled gitd is on localhost:5055 inside the app's process
# Use the on-device picker → gemma-4-e2b-q4km-gguf
# Tap a suggestion chip (e.g. Wi-Fi toggle)

# Watch for:
adb logcat | grep -F -e BENCH -e DeviceActions -e nativeLoadState
```
