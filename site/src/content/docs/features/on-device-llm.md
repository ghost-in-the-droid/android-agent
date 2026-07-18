---
title: "On-Device LLM"
description: Run Gemma directly inside the Ghost Android app — no server, no cloud, no data leaving the phone. MediaPipe + llama.cpp under one wrapper.
---

⭐ **New in 1.3** — The killer story: run the model **inside the phone itself**. Works in airplane mode. Nothing leaves the device.

## What "on-device" actually means

There's a big difference between "local" and "on-device":

| | Where model runs | What leaves the phone |
|---|---|---|
| Cloud (Anthropic, OpenRouter…) | Cloud GPU | Your prompts + tools |
| Local ([Ollama](https://ollama.com/), [vLLM](https://docs.vllm.ai/)) | Your laptop / desk GPU | Prompts leave the phone (via LAN or SSH tunnel) — but stay on your network |
| **On-device** ⭐ | **The phone itself** | **Nothing** |

On-device is the only mode where the LLM literally executes inside the Ghost app process. The phone is both the agent's body **and** its brain.

:::tip[On iPhone too]
On-device is no longer Android-only. A native SwiftUI app runs the model and the agent loop entirely on the iPhone via **llama.cpp on Metal** (Qwen2.5 1.5B), with an **opt-in MLX engine** for faster decode on Apple Silicon. Same idea, same airplane-mode guarantee: your iPhone talks to itself. See the [iOS on-device guide](https://github.com/ghost-in-the-droid/android-agent/blob/main/docs/IOS_ONDEVICE.md).
:::

## The 2 engines under one wrapper

Ghost's `OnDeviceLLM` is a **routing singleton** — one Python entry point, two totally separate C++ inference engines:

| Engine | Model format | Where it comes from | Best for |
|---|---|---|---|
| **[MediaPipe LLM Inference](https://ai.google.dev/edge/mediapipe/solutions/genai/llm_inference)** | `.task` | Google's Android SDK — mobile-optimized runtime | Small Gemma models (1B, 2B) with fastest Android integration |
| **[llama.cpp](https://github.com/ggerganov/llama.cpp) (via JNI)** | `.gguf` | Open-source ecosystem ([ggerganov](https://github.com/ggerganov)) + [HuggingFace](https://huggingface.co/models?library=gguf) | Full model zoo — Gemma 4, Llama, Mistral, Qwen, DeepSeek, any GGUF |

`OnDeviceLLM.ensureLoaded(modelId)` reads `OnDeviceModelRegistry` metadata and routes to the right engine. Callers don't know the difference.

## Supported models

### MediaPipe (`.task` format)

| Model | Size | Where to get it |
|---|---|---|
| [`gemma-3-1b-it`](https://huggingface.co/google/gemma-3-1b-it) | ~550 MB | HuggingFace (via Google) |
| [`gemma-2-2b-it`](https://huggingface.co/google/gemma-2-2b-it) | ~1.4 GB | HuggingFace (via Google) |

### llama.cpp (`.gguf` format)

| Model | Size | Where to get it |
|---|---|---|
| [`gemma-4-e2b-q4km-gguf`](https://huggingface.co/unsloth/gemma-4-E2B-it-GGUF) | ~1.8 GB | [Unsloth](https://unsloth.ai/) HuggingFace repo (Q4_K_M quant) |

Any other [GGUF model on HuggingFace](https://huggingface.co/models?library=gguf) can be added to `OnDeviceModelRegistry` and run through the same llama.cpp engine — you just need enough RAM on the phone.

## How it works — the stack

```
┌────────────────────────────────────────────────────────────────┐
│  Ghost Android APK (installed on the phone)                     │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Python layer (Chaquopy = full Python runtime inside APK) │  │
│  │  • agent_chat_ondevice.py                                 │  │
│  │  • Builds Gemma chat template + calls Kotlin              │  │
│  └────────────────────────┬──────────────────────────────────┘  │
│                            │ jclass("...").INSTANCE.generate()  │
│                            ▼                                     │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Kotlin layer                                              │  │
│  │  • OnDeviceLLM singleton — routes by model.runtime         │  │
│  ├───────────────────┬───────────────────────────────────────┤  │
│  │  MediaPipe path   │  llama.cpp path                        │  │
│  │  ─────────────    │  ─────────────                         │  │
│  │  LlmInference     │  LlamaCppLLM (JNI wrapper)             │  │
│  │  ↓                │  ↓                                     │  │
│  │  .task files      │  .gguf files                           │  │
│  └───────────────────┴───────────────────────────────────────┘  │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  ModelDownloader.kt — in-app model download + cache        │  │
│  └───────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────┘
```

### Python ↔ Kotlin bridge

[Chaquopy](https://chaquo.com/chaquopy/) embeds a full CPython runtime inside the Android APK. Ghost's Python code (`agent_chat_ondevice.py`) can call any Kotlin class as if it were Python:

```python
from java import jclass
llm = jclass("com.ghostinthedroid.app.ondevice.OnDeviceLLM").INSTANCE
llm.ensureLoaded("gemma-4-e2b-q4km-gguf")
for token in llm.generate(prompt): ...
```

Zero-copy across the JNI boundary. Same skill code that runs on the laptop dashboard runs unchanged inside the APK.

## The Gemma chat template gotcha

Getting Gemma to work reliably on-device took one non-obvious fix: **use Gemma's canonical chat template, not a custom scaffold**.

We initially wrapped prompts in `[SYSTEM]/[USER]/[ASSISTANT]` markers. Gemma had never seen those tokens in fine-tuning — so it happily echoed them back inside its own replies, "writing" fake `[USER]` turns from inside its assistant response. Multi-turn tool chains would spin out into infinite loops.

Fixed by switching to Gemma's native markers:

```
<start_of_turn>user
{system prompt}

{user message}<end_of_turn>
<start_of_turn>model
```

Multi-turn tool chains work reliably now — verified on a Snapdragon 888 during the Ghost-Gemma hackathon push.

## KV cache warmup

On-device inference cost is dominated by **prompt prefill**, not decode. Our system prompt + tool definitions run to ~4-6K tokens — recomputing that on every turn would kill latency.

`OnDeviceLLM.warmup()` pre-fills the KV cache once at app launch:

```kotlin
// MainActivity onCreate
GlobalScope.launch { OnDeviceLLM.warmup(system, deviceStablePrefix) }
```

Subsequent turns skip the prefill entirely. First-message latency drops from ~15s to sub-second on Snapdragon 8 Gen 3.

The stable prefix is computed in Python and matched on the Kotlin side:

```python
# gitd/services/agent_chat_ondevice.py
def ondevice_stable_prefix(system: str, device: str) -> str:
    return f"<start_of_turn>user\n{system}\n\nDevice: {device}\n\n"
```

## Model download flow

Models are downloaded **in-app** (not sideloaded):

1. User opens Ghost app → picks a model in the picker
2. `ModelDownloader.kt` fetches the file from HuggingFace (or configured mirror)
3. File cached in the app's internal storage (`context.filesDir`)
4. Cached forever after — subsequent launches reuse

Model sizes range 550 MB (Gemma 3 1B) to ~1.8 GB (Gemma 4 E2B). Downloading over WiFi is recommended.

## Performance expectations

Rough numbers on a Snapdragon 8 Gen 3 (Samsung Galaxy S24 class):

| Model | Prefill (warmed) | Decode | Multi-turn feel |
|---|---|---|---|
| Gemma 3 1B (`.task`, MediaPipe) | <1 s | ~20-30 tok/s | Snappy |
| Gemma 2 2B (`.task`, MediaPipe) | 1-2 s | ~10-15 tok/s | OK |
| Gemma 4 E2B (`.gguf` Q4_K_M, llama.cpp) | 1-2 s | ~8-12 tok/s | Best quality, still usable |

Snapdragon 888 (2020 flagship) will be roughly half these numbers. Anything below Snapdragon 8 Gen 1 struggles with 2B+ models.

## When to use on-device

**Use on-device when:**
- You want a demo you can show on a plane / at a conference booth with no wifi
- Privacy matters — customer data, personal info, corporate secrets
- You're bandwidth-constrained (rural, satellite, expensive roaming)
- You want to prove a fully-offline autonomous agent works

**Don't use on-device when:**
- You need the smartest available model (Claude 4, GPT-5 crush any on-device model on complex reasoning)
- You're driving from the laptop dashboard (on-device only runs inside the APK chat UI)
- You need long context windows (>8K tokens) — on-device is memory-constrained

## Running from where?

One subtle product point:

| Where you're chatting from | Which provider runs on-device? |
|---|---|
| Ghost Android app's chat UI | ✅ Yes — LLM runs on the phone |
| Ghost web dashboard on your laptop | ❌ No — LLM runs on your laptop or in cloud |
| MCP client (Claude Code, Cursor) via `ghost` server | ❌ No — the client's model handles reasoning |

The Ghost APK is required for on-device inference. If you're driving Ghost from your laptop, "on-device" isn't in your provider options.

## Adding a new on-device model

Add an entry to `OnDeviceModelRegistry.kt`:

```kotlin
OnDeviceModel(
    id = "my-model-id",
    runtime = Runtime.LLAMA_CPP,            // or MEDIAPIPE
    promptStyle = PromptStyle.GEMMA,        // or RAW
    downloadUrl = "https://.../model.gguf",
    displayName = "My Model 7B (Q4_K_M)",
    sizeBytes = 4_200_000_000,
)
```

Then add the id to Python's `PROVIDERS["on-device"]["models"]` list. That's it.

For entirely new runtimes (Executorch, MLC, etc.) — implement an `LLMBackend` interface parallel to `LlamaCppLLM`, then dispatch in `OnDeviceLLM.ensureLoaded()`.

## Related

- [LLM Providers](../llm-providers/) — the full list of ways to run models with Ghost
- [MCP Server](../mcp-server/) — how external agents drive Ghost (unrelated to on-device)
- [Tracing](../tracing/) — see exactly what tokens the on-device model produced
