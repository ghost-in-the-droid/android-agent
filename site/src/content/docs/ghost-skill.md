---
title: Ghost Skill
description: Choose the Ghost agent guide for phone tasks or Skill Creator for authoring hub skills.
---

Give your agent the Ghost workflow. These are agent instructions; app automations
are installed separately from the [Skill Hub](/skills/).

## Ghost — use the phone

Choose **Ghost** for everyday phone tasks: connect MCP, find and install hub skills,
run deterministic actions, or read SOFT.md notes before driving an unfamiliar flow.

From the root of a Ghost source checkout, install for Claude Code in one line:

```bash
mkdir -p ~/.claude/skills/ghost && cp skillhub/_guides/ghost-base/SKILL.md ~/.claude/skills/ghost/SKILL.md
```

Then install the current CLI with `pip install -e .` and connect the server:

```bash
claude mcp add ghost -- android-agent-mcp
```

Other MCP clients use command `android-agent-mcp` with no arguments. For Codex,
copy the same guide to `~/.codex/skills/ghost/SKILL.md` instead.

## Skill Creator — build a reusable skill

Choose **Skill Creator** when authoring or improving an app automation. It covers
steps, validators, SOFT.md notes, signed runs, `ghost skill demo`, and hub submission.

From the same checkout, install in one line:

```bash
mkdir -p ~/.claude/skills/ghost-skill-creation-guide && cp skillhub/_guides/skill-creation-guide/SKILL.md ~/.claude/skills/ghost-skill-creation-guide/SKILL.md
```

For Codex, use `~/.codex/skills/ghost-skill-creation-guide/SKILL.md` instead.
Keep the checkout available for the guide's schema and scoring references.
You can install both: Ghost runs tasks; Skill Creator helps you author the next flow.

[Create a skill](/skills/creating-skills/) · [Publish a skill](/skills/publishing/)

HARD skills replay through `run_skill`. SOFT skills are SOFT.md reference notes
read through `get_skill_notes`. A human captcha is a GATE.
