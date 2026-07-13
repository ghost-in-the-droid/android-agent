# Ghost LLM (iOS) — on-device LLM app

SwiftUI app that runs an LLM entirely on the iPhone via **llama.cpp** (GGUF), the
iOS mirror of Ghost's Android on-device path. Design rationale + milestones:
[`../docs/ios/ONDEVICE_LLM.md`](../docs/ios/ONDEVICE_LLM.md).

## Layout

```
ios/
  project.yml                 # xcodegen spec (SwiftUI, iOS 17+, LlamaSwift dep)
  GhostLLM/
    App/                      # GhostLLMApp.swift, ContentView.swift
    Engine/
      InferenceEngine.swift   # runtime-agnostic protocol (MLX can conform later)
      LlamaEngine.swift       # llama.cpp actor: load GGUF, greedy decode
      ModelStore.swift        # model location (bundle now, Documents later)
    Resources/                # bundled GGUF (gitignored, fetched by script)
  scripts/fetch-phase0-model.sh
```

The `.xcodeproj` is generated (gitignored) — edit `project.yml`, not the project.

## Build & run (simulator)

```bash
brew install xcodegen                 # one-time
cd ios
./scripts/fetch-phase0-model.sh       # downloads the tiny Phase 0 model
xcodegen generate
xcodebuild -project GhostLLM.xcodeproj -scheme GhostLLM \
  -sdk iphonesimulator -destination 'generic/platform=iOS Simulator' \
  -derivedDataPath build build

SIM="iPhone 16 Pro"
xcrun simctl boot "$SIM" || true
xcrun simctl install "$SIM" \
  build/Build/Products/Debug-iphonesimulator/GhostLLM.app
xcrun simctl launch --console-pty "$SIM" com.ghostinthedroid.ghostllm
```

The app auto-runs Phase 0 on launch and prints `PHASE0_RESULT …` (first token,
full text, tok/s). On the simulator it runs on CPU (no Metal); on device it
offloads to Metal.

## Status

**M0 complete** — see the design doc. Next: M1 (chat template + full turn +
Gemma-4 E2B download-on-first-run).
