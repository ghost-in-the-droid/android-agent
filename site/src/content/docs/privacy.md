---
title: Privacy Policy
description: How Ghost in the Droid handles your data
---

**Effective date:** April 5, 2026  
**Last updated:** April 5, 2026

Ghost in the Droid ("the Software") is an open-source Android automation framework. This policy explains what data the Software accesses, how it is used, and your rights.

## What the Software Does

Ghost in the Droid connects to Android devices via ADB (Android Debug Bridge) and provides automation capabilities including screen reading, tapping, typing, app management, and skill execution.

## Data the Software Accesses

### On your device
- **Screenshots and screen content** — captured when executing automation tasks or when requested by the user. Stored locally.
- **UI element trees** — Android accessibility/UI hierarchy data used to identify and interact with on-screen elements. Processed in memory, not stored permanently.
- **App package lists** — used to check which apps are installed. Not transmitted externally.
- **ADB shell access** — the Software can execute shell commands on connected devices as authorized by the user.

### Stored locally
- **Task history and logs** — records of executed automations, stored in a local SQLite database on the machine running the Software.
- **Skill definitions** — YAML and Python files defining automation recipes, stored on disk.
- **Screenshots** — stored in the local `data/` directory. Not transmitted unless explicitly configured.

### Sent to third parties (only when configured)
- **LLM API calls** — if you configure an API key (OpenAI, Anthropic, or OpenRouter), prompts and screen descriptions may be sent to those providers for AI-powered features (Agent Chat, Skill Creator). No data is sent without an API key configured.
- **Analytics** — if enabled, anonymous usage analytics (feature usage, error counts) may be sent to PostHog or a self-hosted instance. Disabled by default.

## Data we do NOT collect
- We do not collect personal information.
- We do not transmit screenshots, screen content, or device data to our servers.
- We do not track users across devices or sessions.
- We do not sell or share any data with advertisers.
- The Software runs entirely on your local machine. There is no central server (until Ghost Network features in future versions, which will be opt-in).

## Third-party LLM providers

When you use AI-powered features, your prompts are sent to the LLM provider you configured. Their privacy policies apply:
- [OpenAI Privacy Policy](https://openai.com/privacy)
- [Anthropic Privacy Policy](https://www.anthropic.com/privacy)
- [OpenRouter Privacy Policy](https://openrouter.ai/privacy)

You can use the Software without any LLM provider. Skills and automation run without AI.

## Data retention

All data is stored locally on your machine. You can delete it at any time by:
- Removing the `data/` directory (database, screenshots, logs)
- Removing skill files from `gitd/skills/`
- Uninstalling the Software

## Children's privacy

The Software is not intended for use by anyone under 13. We do not knowingly collect data from children.

## Open source

The Software is MIT-licensed and open source. You can audit exactly what data is accessed by reading the source code at [github.com/ghost-in-the-droid](https://github.com/ghost-in-the-droid).

## Changes to this policy

We may update this policy as features change. Changes will be reflected in the "Last updated" date and committed to the repository.

## Contact

For privacy questions: ghost@ghostinthedroid.com  
GitHub: [github.com/ghost-in-the-droid](https://github.com/ghost-in-the-droid)
