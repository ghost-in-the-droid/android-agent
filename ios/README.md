# Ghost LLM (iOS) — on-device LLM app

SwiftUI app that runs an LLM **entirely on the iPhone** via **llama.cpp** (GGUF) —
the iOS mirror of Ghost's Android on-device path. It can chat, drive the phone as
an agent, and run a self-narrating demo. Design rationale + milestones:
[`../docs/ios/ONDEVICE_LLM.md`](../docs/ios/ONDEVICE_LLM.md) and
[`../docs/ios/AGENT_LOOP_BRIDGE.md`](../docs/ios/AGENT_LOOP_BRIDGE.md).

## Layout

```
ios/
  project.yml                 # xcodegen spec (SwiftUI, iOS 17+, LlamaSwift dep)
  GhostLLM/
    App/                      # GhostLLMApp.swift, ContentView.swift (chat), ChatViewModel
    Engine/
      InferenceEngine.swift   # runtime-agnostic protocol (MLX can conform later)
      LlamaEngine.swift       # llama.cpp actor: load GGUF, sampler chain (penalty+greedy)
      ModelRegistry.swift     # SmolLM2 (bundled) + Gemma-4 E2B (download-on-first-run)
      ModelStore.swift        # bundle vs Documents resolution
      ModelDownloadManager.swift
    Agent/                    # AgentLoop, WDAClient (+ mock), tool vocab, GBNF grammar
    Demo/                     # DemoView/DemoViewModel (self-running hero demo),
                              #   RedditFetcher, StatusServer (:8088 for fleet tiles)
    Resources/                # bundled GGUF (gitignored) + reddit_thread.json fallback
  scripts/
    fetch-phase0-model.sh     # download the tiny bundled model
    export-ipa.sh             # archive + export a signed .ipa (dev / ad-hoc / app-store)
  ExportOptions-*.plist       # export configs per distribution method
```

The `.xcodeproj` is generated (gitignored) — edit `project.yml`, not the project.

## Build & run (simulator)

```bash
brew install xcodegen                 # one-time
cd ios
./scripts/fetch-phase0-model.sh       # downloads the bundled model
xcodegen generate
xcodebuild -project GhostLLM.xcodeproj -scheme GhostLLM \
  -sdk iphonesimulator -destination 'generic/platform=iOS Simulator' \
  -derivedDataPath build build
xcrun simctl install booted build/Build/Products/Debug-iphonesimulator/GhostLLM.app
xcrun simctl launch booted com.ghostinthedroid.ghostllm
```

Simulator runs on CPU (no Metal); device offloads all layers to Metal.

### Launch flags (env)

- `GHOST_DEMO=1` — self-running hero demo (fetch r/LocalLLaMA + on-device summary)
- `GHOST_MODEL=gemma` — boot straight into Gemma-4 E2B
- `GHOST_PERF=smol|gemma` — timed generation, prints `PERF_RESULT … tok/s`

## Deploy to a physical device (autonomous)

Signing is headless via a dedicated keychain (one-time `~/ghost-signing-setup.sh`
by the Mac owner). After that:

```bash
~/ghost-deploy-auto.sh                # build + sign + install to the iPhone, no prompts
```

## IPA / distribution

```bash
METHOD=development ./scripts/export-ipa.sh   # installs on registered devices (default)
METHOD=ad-hoc      ./scripts/export-ipa.sh   # shareable to registered UDIDs
METHOD=app-store   ./scripts/export-ipa.sh   # TestFlight / App Store
```

`development` works today with the Apple Development cert. `ad-hoc` / `app-store`
need a **Distribution cert** added to `ghost-signing.keychain-db` + the matching
provisioning profile — then the same command yields a shareable IPA.

## Status — M0 → M3 complete

On-device on a real iPhone 15 Pro (A17 Pro, Metal): SmolLM2-360M ~51 tok/s,
**Gemma-4 E2B ~13.7 tok/s**. Chat, model download-on-first-run, agent-drives-WDA,
and a self-running demo that reads r/LocalLLaMA and summarizes it offline. Hero
recording + `:8088` fleet-tile status endpoint shipped. See the design doc.
