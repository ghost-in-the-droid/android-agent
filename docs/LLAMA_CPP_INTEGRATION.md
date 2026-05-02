# llama.cpp Android — integration plan

**Status:** Kotlin scaffolding is shipped; native lib not yet built into the APK.
**Why:** Google's MediaPipe Android SDK doesn't ship a loadable Gemma 4 `.task`
yet — only `-web.task` (browser-only) and `.litertlm` (new SDK not on Maven).
llama.cpp main branch supports Gemma 4 in GGUF, so that's the path to true
on-device Gemma 4.

## What's already in place

- `app/src/main/java/com/ghostinthedroid/app/ondevice/OnDeviceModel.kt` —
  added `Runtime { MEDIAPIPE, LLAMA_CPP }` enum field on `OnDeviceModel`.
- `LlamaCppLLM.kt` — singleton mirror of `OnDeviceLLM`'s API
  (`init`, `ensureLoaded`, `generate`, `unload`). Native methods are declared
  but unimplemented; calls return `[on-device error: llama.cpp not wired yet …]`
  until the JNI lib lands.
- `OnDeviceLLM.kt` — delegates to `LlamaCppLLM` when the model's `runtime ==
  LLAMA_CPP`. So registering a GGUF-backed model in `OnDeviceModelRegistry`
  with `runtime = Runtime.LLAMA_CPP` immediately routes through the new path.
- `app/build.gradle.kts` — unchanged (no new gradle wiring yet, see step 3).

This means the Kotlin compiler stays green, the existing MediaPipe path is
untouched, and we have a single API for both backends.

## What still needs to happen (~half day)

### 1. Vendor llama.cpp source

```bash
cd ghost-app/app/src/main
git submodule add https://github.com/ggerganov/llama.cpp cpp/llama.cpp
git submodule update --init --recursive
```

llama.cpp itself is the source of truth — we don't fork. Pin to a tag
(e.g. `b4500` or whatever the latest with Gemma 4 support is) so builds
are reproducible.

### 2. Tiny JNI bridge

Write `app/src/main/cpp/llama_jni.cpp` (~100 lines). Skeleton:

```cpp
#include <jni.h>
#include "llama.h"

extern "C" JNIEXPORT jlong JNICALL
Java_com_ghostinthedroid_app_ondevice_LlamaCppLLM_nativeLoadModel(
    JNIEnv* env, jobject /* this */, jstring path, jint maxTokens) {
    const char* path_chars = env->GetStringUTFChars(path, nullptr);
    llama_model_params model_params = llama_model_default_params();
    llama_model* model = llama_load_model_from_file(path_chars, model_params);
    env->ReleaseStringUTFChars(path, path_chars);
    if (!model) return 0;

    llama_context_params ctx_params = llama_context_default_params();
    ctx_params.n_ctx = maxTokens;
    llama_context* ctx = llama_new_context_with_model(model, ctx_params);
    // pack {model, ctx} into a struct, return its pointer as jlong
    auto* handle = new LlamaHandle{model, ctx};
    return reinterpret_cast<jlong>(handle);
}

// nativeGenerate — tokenize prompt, sample tokens until <end_of_turn>, return string
// nativeFreeModel — delete LlamaHandle
```

Match function names to the `external fun` declarations in `LlamaCppLLM.kt`
(JNI auto-binds by `Java_<package>_<class>_<method>`).

### 3. CMakeLists for the NDK build

`app/src/main/cpp/CMakeLists.txt`:

```cmake
cmake_minimum_required(VERSION 3.22)
project(llama_jni)

# Tell llama.cpp we're targeting Android
set(LLAMA_NATIVE OFF)
set(GGML_OPENMP OFF)  # Android NDK doesn't ship openmp by default
add_subdirectory(llama.cpp EXCLUDE_FROM_ALL)

add_library(llama_jni SHARED llama_jni.cpp)
target_link_libraries(llama_jni llama android log)
```

Wire from gradle:

```kotlin
// app/build.gradle.kts
android {
    defaultConfig {
        externalNativeBuild {
            cmake { arguments += listOf("-DGGML_OPENMP=OFF") }
        }
    }
    externalNativeBuild {
        cmake {
            path = file("src/main/cpp/CMakeLists.txt")
            version = "3.22.1"
        }
    }
}
```

### 4. Register Gemma 4 entries in OnDeviceModelRegistry

```kotlin
OnDeviceModel(
    id = "gemma-4-e2b",
    displayName = "Gemma 4 E2B (Q4_K_M)",
    downloadUrl = "https://huggingface.co/unsloth/gemma-4-E2B-it-GGUF/resolve/main/gemma-4-E2B-it-Q4_K_M.gguf",
    sizeBytes = 3_106_735_776L,
    runtime = Runtime.LLAMA_CPP,
    supportsImages = false,  // text-only via llama.cpp; mmproj support is separate
    maxTokens = 4096,
),
OnDeviceModel(
    id = "ghost-gemma",
    displayName = "Ghost-Gemma E4B (fine-tune, Q4_K_M)",
    downloadUrl = "https://huggingface.co/ghost-in-the-droid/ghost-gemma-E4B-GGUF/resolve/main/ghost-gemma-E4B-Q4_K_M.gguf",  // when published
    sizeBytes = 5_335_289_888L,
    runtime = Runtime.LLAMA_CPP,
    maxTokens = 4096,
),
```

These show up in the model picker automatically (no UI changes needed).

### 5. Verify

- `./gradlew :app:assembleDebug` — should compile native lib + APK
- Install + open model picker → see Gemma 4 entries
- Tap Download — file downloads via existing `ModelDownloader` (unchanged)
- Send a chat with `provider=on-device, model=gemma-4-e2b` — routes through
  `OnDeviceLLM.generate` → sees `runtime=LLAMA_CPP` → delegates to
  `LlamaCppLLM.generate` → JNI → llama.cpp inference → response streams back
  → trace shows in the in-app Traces tab with `provider=on-device, model=gemma-4-e2b`

### 6. Optional polish

- **Streaming**: llama.cpp emits tokens one at a time; expose a callback-based
  `generate` that yields each token to the chat loop for real-time TTS.
- **Vision via mmproj**: Gemma 4 multimodal needs the separate
  `mmproj-gemma-4-E2B-it-bf16.gguf` file; llama.cpp loads it as a paired
  encoder. Out of scope for v1.
- **GPU offload**: phones with Adreno can run llama.cpp's Vulkan backend;
  fall back to CPU otherwise.

## Risks

- **APK size**: vendored llama.cpp + the .so for arm64-v8a + x86_64 adds
  ~30-40 MB to the APK. Acceptable for hackathon, can split-APK later.
- **Build time**: first NDK build is ~5 min. Cached after. CI needs
  `--no-daemon` flag to avoid stale cmake state.
- **NDK version**: llama.cpp wants r25b+. Chaquopy uses r25c — overlap fine.

## Reference

- llama.cpp Android example (full working setup): https://github.com/ggerganov/llama.cpp/tree/master/examples/llama.android
- Pattern we're following: `app/src/main/cpp/<jni source>` + cmake submodule.
