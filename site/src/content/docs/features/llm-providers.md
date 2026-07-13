---
title: "LLM Providers"
description: Ghost's agent-chat works with any LLM — Claude, GPT, Gemini, Llama, Gemma. Cloud, local, or on the phone itself.
---

Ghost's built-in agent loop is model-agnostic. Point it at a cloud API, run Ollama on your laptop, or run the model **on the phone itself**. Same tools, same skills, same interface — just swap the brain.

## The 6 providers

| # | Provider | Where it runs | Best for | Setup |
|---|---|---|---|---|
| 1 | **[Claude Code](https://claude.com/claude-code)** | Your machine (via CLI) | Free daily driver, Sonnet/Opus/Haiku | `claude` CLI installed |
| 2 | **[Anthropic API](https://docs.anthropic.com/)** | Anthropic cloud | Latest Claude 4 Sonnet + Opus with full control | `ANTHROPIC_API_KEY` |
| 3 | **[OpenRouter](https://openrouter.ai/)** | Cloud multiplexer | Any model — GPT, Gemini, DeepSeek, Grok, Hermes... | `OPENROUTER_API_KEY` |
| 4 | **[Ollama](https://ollama.com/)** | Your machine | Local models, no cloud, cheap iteration | Ollama installed |
| 5 | **On-device** ⭐ | The phone itself | 100% offline, no data leaves the device | Ghost app installed |
| 6 | **[vLLM](https://docs.vllm.ai/)** | Your GPU / self-hosted | Full-precision open-source models at speed | vLLM server URL |

## Pick your brain

### 🆓 Just try it — [Claude Code](https://claude.com/claude-code)

Free with a [Claude Pro/Max subscription](https://claude.com/pricing), no API key needed.

```bash
# One-time
claude mcp add ghost stdio -- python3 -m gitd.mcp_server

# Use it
```

Ghost auto-selects `claude-code` provider with Sonnet. Zero config.

### 🚀 Best quality — [Anthropic API](https://docs.anthropic.com/)

Get a key at [console.anthropic.com](https://console.anthropic.com/).

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

Provider `anthropic` unlocks [Claude Sonnet 4](https://www.anthropic.com/claude/sonnet) and [Opus 4](https://www.anthropic.com/claude/opus) directly. Recommended for anything you'd bill a customer for.

### 🌐 Any model — [OpenRouter](https://openrouter.ai/)

Single API key, [hundreds of models](https://openrouter.ai/models). Great for evals or when you need GPT / Gemini / Nous Hermes / etc.

Get a key at [openrouter.ai/keys](https://openrouter.ai/keys).

```bash
export OPENROUTER_API_KEY=sk-or-v1-...
```

Bundled model list:

- [`anthropic/claude-sonnet-4`](https://openrouter.ai/anthropic/claude-sonnet-4)
- [`google/gemini-2.5-pro`](https://openrouter.ai/google/gemini-2.5-pro)

Or type any [OpenRouter model ID](https://openrouter.ai/models) directly in the agent chat model selector.

### 🏠 Fully local — [Ollama](https://ollama.com/)

For fast iteration, offline dev, or privacy-first setups. [Install Ollama](https://ollama.com/download), then:

```bash
ollama pull llama3.2:3b
```

Ghost auto-discovers running Ollama models. Ships tuned defaults:

- [`llama3.2:3b`](https://ollama.com/library/llama3.2) and [`llama3.2:1b`](https://ollama.com/library/llama3.2) — fast, tool-use capable
- [`gemma3:4b`](https://ollama.com/library/gemma3) — best quality-per-parameter in the small tier
- [`qwen3:4b`](https://ollama.com/library/qwen3) — strong reasoning
- [`phi4-mini:3.8b`](https://ollama.com/library/phi4-mini) — Microsoft's compact model
- [`mistral:7b`](https://ollama.com/library/mistral) — classic solid all-rounder

Browse the [full model library](https://ollama.com/library) for more.

### 📱 On the phone itself ⭐ new in 1.3

The killer story: run the model **inside the Ghost Android app** via [MediaPipe LLM Inference](https://ai.google.dev/edge/mediapipe/solutions/genai/llm_inference) or [llama.cpp](https://github.com/ggerganov/llama.cpp). Nothing leaves the phone. Works in airplane mode.

- [`gemma-3-1b-it`](https://huggingface.co/google/gemma-3-1b-it) — MediaPipe, tiny footprint, fast
- [`gemma-2-2b-it`](https://huggingface.co/google/gemma-2-2b-it) — better reasoning
- [`gemma-4-e2b-q4km-gguf`](https://huggingface.co/unsloth/gemma-4-E2B-it-GGUF) — llama.cpp GGUF, best on-device model

Install the Ghost companion app, download a model bundle in-app, pick provider `on-device` in the dashboard.

### ⚡ Self-hosted GPU — [vLLM](https://docs.vllm.ai/)

If you're running your own GPU (H100, A100, RTX 4090, etc.) with [vLLM](https://github.com/vllm-project/vllm), point Ghost at it. Full-precision Gemma or any [HuggingFace](https://huggingface.co/) model at [OpenAI-compatible endpoints](https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html).

```bash
export VLLM_BASE_URL=http://your-gpu-box:8000/v1
```

Bundled defaults for Gemma 4 (via [Unsloth](https://unsloth.ai/)):

- [`unsloth/gemma-4-E2B-it`](https://huggingface.co/unsloth/gemma-4-E2B-it) (full precision)
- [`unsloth/gemma-4-E2B-it-bnb-4bit`](https://huggingface.co/unsloth/gemma-4-E2B-it-bnb-4bit)
- [`unsloth/gemma-4-E4B-it`](https://huggingface.co/unsloth/gemma-4-E4B-it) (full precision)
- [`unsloth/gemma-4-E4B-it-bnb-4bit`](https://huggingface.co/unsloth/gemma-4-E4B-it-bnb-4bit)

Great combo: **Ghost on your phone** → SSH tunnel to your workstation → **vLLM on the desk GPU**. Full model quality, low latency, private data.

## Choose by use case

**"I just want to try Ghost"** → Claude Code (free, zero config)

**"I'm shipping to real users"** → Anthropic API (best-in-class Claude 4)

**"I'm evaluating models"** → OpenRouter (hundreds of models, one key)

**"I don't want to pay per call"** → Ollama (unlimited, local)

**"I don't want data leaving the phone"** → On-device (100% offline)

**"I have my own GPU"** → vLLM (self-hosted, high throughput)

**"I want the whole stack under my roof"** → Ollama or vLLM + Ghost self-hosted

## Provider comparison

| | Cloud dep | Cost | Latency | Quality | Privacy | Offline |
|---|---|---|---|---|---|---|
| Claude Code | Anthropic | Free* | Fast | ⭐⭐⭐⭐⭐ | ⚠️ prompts leave device | ❌ |
| Anthropic API | Anthropic | Pay-per-token | Fast | ⭐⭐⭐⭐⭐ | ⚠️ prompts leave device | ❌ |
| OpenRouter | Router + upstream | Pay-per-token | Fast | ⭐⭐⭐⭐ (varies) | ⚠️ prompts leave device | ❌ |
| Ollama | None | Free | Medium | ⭐⭐⭐ | 🟢 local | ✅ |
| **On-device** | **None** | **Free** | **Slow-medium** | **⭐⭐⭐** | **🟢 phone-only** | **✅** |
| vLLM | Your GPU box | Electricity | Fast | ⭐⭐⭐⭐ | 🟢 self-hosted | ✅ (LAN) |

*Free with Claude Pro/Max subscription.

## Switching providers

From the dashboard:

1. Open **Agent Chat** on any device
2. Pick provider + model from the toolbar
3. Send your message

From code:

```python
from gitd.services.agent_chat import create_session

session = create_session(
    device="YOUR_DEVICE_SERIAL",
    provider="on-device",           # or "anthropic", "ollama", etc.
    model="gemma-4-e2b-q4km-gguf",
)
```

Switching between providers mid-conversation preserves history.

## Configuration reference

Environment variables:

```bash
# Cloud APIs
ANTHROPIC_API_KEY=sk-ant-...
OPENROUTER_API_KEY=sk-or-v1-...

# Local runtimes
VLLM_BASE_URL=http://gpu-host:8000/v1
```

Ollama is expected at `http://localhost:11434` (the standard `ollama serve` address); the agent chat backend connects there directly.

## Adding a new provider

Providers live in a single map:

```python
# gitd/services/agent_chat.py
PROVIDERS = {
    "your-provider": {
        "label": "Your Provider",
        "models": ["model-id-1", "model-id-2"],
    },
    ...
}
```

Plus a dispatch handler. See existing providers as reference. PRs welcome — especially for new local model runtimes and vendor-specific APIs.

## Related

- [MCP Server](../mcp-server/) — the other direction: agents that connect **to** Ghost
- [Dashboard](../dashboard/) — pick and switch providers in the UI
- [Getting Started: Installation](../../getting-started/installation/) — set up Ghost + your first provider
