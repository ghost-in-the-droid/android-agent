---
title: "How Ghost Compares"
description: Where Ghost in the Droid sits versus cloud device-automation services — local-first, open-source, $0 per device.
---

:::caution[Draft — pending marketing copy]
The competitive narrative and comparison rows on this page are being finalised by the marketing team. The **"Ghost at a glance"** section below is code-grounded and accurate; the framed comparison against specific alternatives will be dropped in before this page ships. Structure and sidebar entry are in place so the copy can land cleanly.
:::

<!--
ADB-MARKETING: drop the approved comparison copy into the marked sections below.
Keep competitor claims factual and sourced. The "Ghost at a glance" table is
already accurate against the codebase — extend, don't contradict it.
-->

## The short version

<!-- ADB-MARKETING COPY: 2-3 sentence positioning statement goes here.
     Theme from the codebase: Ghost is local-first and open-source — it drives
     real phones over ADB from your own machine, with no per-device cloud fee. -->

## Ghost at a glance

These are facts about what Ghost is and does today (v1.3.0):

| | Ghost in the Droid |
|---|---|
| **License** | Open source, MIT |
| **Where it runs** | Your machine + your phones/emulators — local-first, no cloud dependency |
| **Cost per device** | $0 — it's your hardware and your ADB connection |
| **Device access** | Real Android phones over ADB (USB or TCP), **no root required** |
| **Emulators** | Docker+KVM emulator pool for parallel/headless runs |
| **How agents drive it** | 41 [MCP tools](../mcp-server/) over stdio or HTTP — works with any MCP client |
| **The brain** | Model-agnostic: [6 providers](../llm-providers/) — Claude, GPT, Gemini, local Ollama/vLLM, or [on-device](../on-device-llm/) |
| **On-device option** | Run the model *inside the phone* — nothing leaves the device |
| **Reusability** | [Skill system](../skill-system/) — record automations once, replay them |
| **Observability** | Built-in [tracing](../tracing/) of every turn, tool call, and token |
| **Benchmarking** | [Ghost Bench](../ghost-bench/) — objective, ADB-verified task success |

## Where Ghost fits

<!-- ADB-MARKETING COPY: the framed comparison against specific alternatives
     (e.g. cloud device-farm SaaS, hosted mobile-agent services) goes here as a
     table + narrative. Suggested columns: Ghost | Cloud SaaS alternatives.
     Suggested axes: hosting model, per-device cost, data locality/privacy,
     open source, root requirement, offline capability, model choice. -->

_Comparison table pending marketing copy._

## When Ghost is the right choice

<!-- ADB-MARKETING COPY: "choose Ghost when…" bullets. -->

_Pending marketing copy._

## Related

- [MCP Server](../mcp-server/) — the 41 tools agents call
- [MCP Clients](../mcp-clients/) — every client that can drive Ghost
- [LLM Providers](../llm-providers/) — bring any model, cloud or local
- [On-Device LLM](../on-device-llm/) — the fully-offline story
