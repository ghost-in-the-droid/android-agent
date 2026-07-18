# On-Device LLM for iPhone

> **Your iPhone talks to itself.** The model runs on the phone, the tool loop runs on the phone, and the agent drives the phone's own UI in airplane mode. No cloud round-trip, nothing leaves the device.

This is the iOS mirror of Ghost's Android on-device story. A native SwiftUI app (iOS 17+, in `ios/`) loads a local model, runs Ghost's agent loop, and drives the iPhone through WebDriverAgent from inside itself.

Status: model runtime picked, app scaffolded, full streaming chat turns generated fully on-device, model registry with download-on-first-run. Agent-loop-to-phone hookup and a shipped offline IPA are the remaining milestones (see [Milestones](#milestones)).

## The two engines

Both conform to one `InferenceEngine` protocol (`ios/GhostLLM/Engine/InferenceEngine.swift`), so the UI and agent code never change when you swap engines. This mirrors Android's `Runtime { MEDIAPIPE, LLAMA_CPP }` split.

| Engine | Model format | Decode speed (iPhone, <14B) | Why |
|---|---|---|---|
| **llama.cpp** (Metal) | `.gguf` | baseline | **Shipping default.** Same GGUF file as Android, one model both platforms. Mature, stable C API, full control of the token loop for tool use. |
| **MLX** (Apple Silicon) | MLX quant | ~1.4 to 1.8x faster | **Opt-in.** Native Swift, faster decode on 2026 kernels. Slots behind the same protocol; an `MLXEngine` conforms without touching UI or agent code. |

### Why llama.cpp is the default

1. **Literal model parity with Android.** The Android registry ships `gemma-4-E2B-it-Q4_K_M.gguf` via llama.cpp (see [LLAMA_CPP_INTEGRATION.md](LLAMA_CPP_INTEGRATION.md)). The exact same GGUF runs unmodified on iPhone: the strongest form of "iOS mirror of the Android story," and it de-risks the model since it is already validated on Android. MLX would need a separate converted artifact and a divergent registry.
2. **Maturity and control.** llama.cpp ships an official prebuilt XCFramework per release; the stable C API gives full control of the token loop, which the agent/tool integration needs.
3. **The perf gap is not blocking.** Gemma-4 E2B Q4_K_M decodes fine on A17 / iPhone 15 Pro. MLX's decode edge matters post-MVP, and it is one protocol conformance away when wanted.

Ruled out for the MVP: LiteRT-LM (immature Swift story, not GGUF), Core ML / ANE (slowest decode, heavy conversion), Ollama (needs a daemon, not App-Store-shippable).

### Reliable tool calls: grammar-constrained decoding

Small models do not reliably emit valid JSON tool calls no matter how you prompt them. Ghost constrains decoding to a GBNF grammar that only permits valid tool-call JSON, so a parse failure becomes impossible by construction. The failure mode shifts from "broken JSON" to "well-formed call to the wrong tool," which is the far easier problem to attack with a tighter tool vocabulary and better descriptions.

## Integration mechanics

- **Dependency:** `LlamaSwift`, which re-exports the llama.cpp C API from the official prebuilt XCFramework (pinned to a llama.cpp build with Gemma 4 support). Fallback if the package goes stale: self-build the XCFramework from a pinned llama.cpp tag via `build-xcframework.sh`, matching Android's "vendor upstream, pin a tag" philosophy. Engine code is unchanged either way; it targets the raw C API.
- **Metal offload:** on device, `n_gpu_layers = 99` (Metal). The simulator has no usable Metal (GPU reports 0 MiB), so it falls back to `n_gpu_layers = 0` (CPU) under `#if targetEnvironment(simulator)`.

## Models

| Role | Model | Size | Notes |
|---|---|---|---|
| Pipeline proof (bundled) | SmolLM2-360M-Instruct Q4_K_M | ~270 MB | Validates load to decode in the simulator, instant offline use |
| Production default (download-on-first-run) | `gemma-4-E2B-it-Q4_K_M.gguf` | ~3.1 GB | Android parity, fits iPhone 15 Pro's 8 GB unified memory |
| Agent default (demo) | Qwen2.5 1.5B | ~1 GB | Tuned for grounded tool use on the phone |

Stronger-reasoning option to trial: Phi-4-mini 3.8B. Models are gitignored and fetched on first run.

## Milestones

- **M0 done** runtime picked, Xcode project scaffolded, tokens generated on-device (simulator). SmolLM2-360M, greedy decode, ~19.6 tok/s CPU.
- **M1 done** full prompt-to-response turn: chat template, streaming into SwiftUI, per-turn KV reset, model registry + download-on-first-run.
- **M2** agent-loop hookup: the on-device LLM drives WDA/phone via Ghost tools (direct-WDA path).
- **M3** demo-able: works offline (airplane mode), real UI, shipped IPA.

## Privacy and security

Never commit real device UDIDs, device names, or Apple IDs. Placeholders only (standing rule). Models are gitignored; fetched via `ios/scripts/fetch-phase0-model.sh`. Wireless drive rides your Tailscale tailnet, so treat the tailnet as the trust boundary.

## See also

- [SETUP_IOS.md](SETUP_IOS.md): enabling and configuring iOS support (feature-gated, off by default)
- [LLAMA_CPP_INTEGRATION.md](LLAMA_CPP_INTEGRATION.md): the Android llama.cpp path (same GGUF)
- [release-notes/v1.3.0.md](release-notes/v1.3.0.md): on-device inference in the 1.3 release
