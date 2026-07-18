# M2 — on-device agent loop bridge (design)

**Goal:** the on-device LLM drives the iPhone's UI through Ghost's tools —
"the iPhone talks to itself." Phone-independent design; execution needs an
iPhone window from ios-tester (post-v1.3.0-demo).

## Architecture: pure-Swift on-device agent loop

The Ghost LLM app runs the LLM **and** the tool loop **and** the WDA client, all
on the phone. No cloud, no Python round-trip — the strongest form of the
marketing story (airplane mode). This mirrors Android's in-process design; we
skip PythonKit/embedded-Python for the MVP (simpler, fully native, no 2nd
runtime). The Python `gitd` agent loop stays the reference for tool semantics.

```
LlamaEngine (M1)  ──►  AgentLoop  ──►  WDAClient  ──►  WebDriverAgent (:8100)
   on-device LLM        tool loop       REST/HTTP        on the same iPhone
        ▲                   │
        └──── observation ◄─┘  (UI dump + screenshot after each action)
```

## Tool set (maps 1:1 to WDA REST, per `gitd/bots/common/ios.py` direct-WDA)

| Tool | WDA endpoint (`{base}/session/{sid}/…`) |
|---|---|
| `tap(x,y)` | `POST /actions` (W3C pointer) |
| `swipe(x1,y1,x2,y2)` | `POST /actions` |
| `type_text(text)` | `POST /keys` (or `/element/active` → `/value`) |
| `press_button(name)` | `POST /wda/pressButton` (home, volume…) |
| `press_enter` | `POST /keys` (\n) |
| `launch_app(bundle_id)` | `POST /wda/apps/launch` |
| `open_url(url)` | `POST /url` |
| `get_ui()` | `GET /source` (accessibility XML → compact JSON) |
| `screenshot()` | `GET /screenshot` (base64 PNG) |
| `done(summary)` | — (terminates the loop) |

Session lifecycle: `POST /session` (create) / `GET /status` (health) /
`DELETE /session/{sid}`. `IOS_WDA_URL` is the base (static Tailscale URL
preferred — see [[ghost-ios-wda-drive-path]] in fleet memory).

## Loop

1. System prompt describes the tools + a strict JSON call schema.
2. LLM emits one tool call as JSON.
3. Parse → `WDAClient` executes → capture observation (compact UI dump; optional
   screenshot for a vision model).
4. Append observation to the transcript; repeat until `done` or `maxSteps`.

### Reliable tool-calling — constrained decoding

Small models don't emit clean JSON reliably. llama.cpp supports **GBNF
grammars** (`llama_sampler_init_grammar`) — we constrain decoding to a grammar
that only permits valid tool-call JSON, guaranteeing parseable output regardless
of model size. This is the M2 robustness path (M1 uses plain greedy; M2 adds a
grammar-constrained sampler). Model: Gemma-4 E2B is the floor; a tool-tuned
model may land better — evaluate during M2.

## Interfaces (to build)

- `protocol WDAClient` — `createSession`, `tap`, `swipe`, `typeText`,
  `pressButton`, `launchApp`, `openURL`, `getUI`, `screenshot`.
  - `HTTPWDAClient` — real, hits `IOS_WDA_URL`.
  - `MockWDAClient` — scripted UI states; lets the whole loop be tested with **no
    phone** (canned observations + a scripted/grammar-constrained decider).
- `struct Tool` + `ToolCall` (Codable) + a GBNF grammar string.
- `actor AgentLoop` — owns `LlamaEngine` + `WDAClient`, runs steps, emits a
  transcript for the UI.

## Topology decision (default chosen; flag if wrong)

**Default:** the app runs **on the target iPhone** and drives WDA at the phone's
own WDA base — true self-driving. If running our app + WDA on the same device
proves impractical for the demo, fall back to the proven remote-drive path (a
driver hits the phone's WDA over Tailscale). Either way `WDAClient` is unchanged
— only the base URL differs. Will confirm the demo topology with ios-tester when
scheduling the phone window.

## Test plan (phone-free, now)

1. `MockWDAClient` returns a scripted screen (e.g. a home screen → Settings).
2. Grammar-constrained decider (or a canned decider) issues tap/get_ui/done.
3. Assert the loop executes the right WDA calls in order and terminates.
Then swap `MockWDAClient` → `HTTPWDAClient` against the real device.

## Status & findings (2026-07-13)

- ✅ `WDAClient` (+ `HTTPWDAClient`, `MockWDAClient`), `AgentLoop`, tool vocab +
  JSON parser built and committed. Scripted-decider test passes (correct WDA call
  order + clean termination).
- ✅ Loop is LLM-driven and **crash-safe**: with the tiny SmolLM2 pipeline-model
  it emits valid JSON shape (`{"tool":"getAppInfo"}`) but hallucinates tool names
  → loop safely reports "no valid tool call". Reliable tool selection needs the
  capable **Gemma-4 E2B** (on-device) — validated as expected.
- ⚠️ **Grammar-constrained decoding** (`toolCallGrammar` + `llama_sampler_init_grammar`)
  is implemented but **gated off** (`AgentLoop(useGrammar:)` defaults false): the
  current GBNF fails llama.cpp's parser, which then throws an *uncatchable* C++
  exception on the first token. TODO: validate/fix the GBNF against llama.cpp
  on-device, then enable — it's the right fix for tool-name reliability.

Remaining for M2/M3 (external-blocked): deploy to device (needs keychain unlock)
to run Gemma on Metal, and point `HTTPWDAClient` at the live phone (needs
ios-tester's phone window — they're mid-v1.3.0-demo).
