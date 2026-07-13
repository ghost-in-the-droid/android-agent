# On-Device LLM for iOS — runtime decision + MVP plan

**Status:** M0 complete (2026-07-13). Runtime picked, SwiftUI app scaffolded,
tokens generated fully on-device in the iOS simulator.

The iOS mirror of Ghost's Android on-device story: an LLM that runs entirely on
the iPhone (no cloud round-trip) and hooks into Ghost's agent loop to drive the
phone from inside itself. Marketing: *your iPhone talks to itself — LLM
on-device, tool loop on-device, agent runs in airplane mode.*

App lives in `ios/` (SwiftUI, iOS 17+). See `ios/README.md` for build/run.

## Runtime decision: **llama.cpp** (with an MLX-ready abstraction)

We evaluated MLX-swift, llama.cpp, LiteRT-LM, and Core ML/ANE.

| | llama.cpp | MLX-swift |
|---|---|---|
| Model format | **GGUF — same file as Android** | MLX quant (separate conversion) |
| Decode speed (iPhone, <14B) | baseline | ~1.4–1.8× faster (2026 kernels) |
| App Store distribution | ✅ embedded, no daemon | ✅ embedded, no daemon |
| Swift integration | C API via XCFramework | native Swift |
| Cross-platform parity | **1 model, both platforms** | iOS-only model artifact |

**Why llama.cpp for the MVP:**

1. **Literal model parity with Android.** The Android registry ships
   `gemma-4-E2B-it-Q4_K_M.gguf` (unsloth) via llama.cpp
   (see `docs/LLAMA_CPP_INTEGRATION.md`). The *exact same GGUF* runs unmodified
   on iOS — the strongest form of "iOS mirror of the Android story," and it
   de-risks the model (already validated for Android). MLX would require a
   separate converted artifact and a divergent model registry.
2. **Maturity + control.** llama.cpp ships an official prebuilt XCFramework per
   release; the stable C API gives us full control of the token loop, which we
   need for the agent/tool integration (M2).
3. **Perf gap isn't MVP-blocking.** Gemma-4 E2B Q4_K_M decodes fine on
   A17/iPhone 15 Pro. MLX's decode edge matters later, not for demo-ability.

**Not one-way.** All call sites go through the `InferenceEngine` protocol
(`ios/GhostLLM/Engine/InferenceEngine.swift`). An `MLXEngine` can conform later
without touching the UI or agent code — mirrors Android's
`Runtime { MEDIAPIPE, LLAMA_CPP }` enum. If we want MLX's decode speed post-MVP,
it slots in behind the same protocol.

*Ruled out for MVP:* LiteRT-LM (best Gemma-E2B memory/speed but immature Swift
story, not GGUF); Core ML/ANE (lowest memory but slowest decode, heavy model
conversion); Ollama (requires a daemon — not App-Store-shippable).

### Integration mechanics

- Dependency: `github.com/mattt/llama.swift` (`LlamaSwift`) — re-exports the
  llama.cpp C API from the official prebuilt XCFramework. Currently pinned by
  the package to llama.cpp **b9978** (has Gemma 4 support).
  - *Fallback if the package goes stale:* self-build the XCFramework from a
    pinned llama.cpp tag via its `build-xcframework.sh` (matches Android's
    "vendor upstream, pin a tag" philosophy). Our engine code is unchanged
    either way — it targets the raw C API.
- **Simulator has no usable Metal** (GPU reports 0 MiB) → `n_gpu_layers = 0`
  (CPU) under `#if targetEnvironment(simulator)`; `n_gpu_layers = 99` (Metal
  offload) on device.

## Models

- **Phase 0 (pipeline proof, bundled):** SmolLM2-360M-Instruct Q4_K_M (~270 MB).
  Tiny, fast, validates load→tokenize→decode→detokenize in the simulator.
- **Production default (download-on-first-run):** `gemma-4-E2B-it-Q4_K_M.gguf`
  (~3.1 GB) — Android parity. Fits iPhone 15 Pro's 8 GB unified memory.
  Alternative stronger-reasoning option to trial: Phi-4-mini 3.8B.

## Milestones

- **M0 ✅** runtime picked + Xcode project scaffolded + tokens generated
  on-device (simulator). First run: SmolLM2-360M, greedy decode, 19.6 tok/s CPU.
- **M1** full prompt→response turn: chat template, sample-to-EOS, streaming into
  the SwiftUI chat window; download-on-first-run for Gemma-4 E2B; model registry.
- **M2** agent-loop hookup: on-device LLM drives WDA/phone via Ghost tools
  (needs an iPhone window from ios-tester; direct-WDA path from PR #52).
- **M3** demo-able: works offline (airplane mode), real UI, shipped IPA.

## Privacy / security

Never commit real device UDIDs, device names, or Apple IDs — placeholders only
(standing fleet rule). Models are gitignored; fetched via
`ios/scripts/fetch-phase0-model.sh`.
