---
title: The ghost CLI
description: One line drives your phone — the task-first ghost command.
---

# The `ghost` CLI

`ghost` gives any AI agent an Android or iOS body from one line:

```bash
ghost "check r/LocalLLaMA on reddit" --device asus
```

The **task is the argument** — no `run` verb, no subcommand. `ghost` spins up the
agent loop (tools + your chosen LLM), drives the phone, and streams what it does.

## Install

```bash
pipx install ghost-in-the-droid      # provides the `ghost` command
```

`ghost` is the primary command. The older `gitd`, `android-agent`, and
`ghost-in-the-droid` commands still work (with a deprecation notice) and will be
removed in a future release. `android-agent-mcp` (the MCP server) is unchanged.

## First run

The first time you run `ghost`, a short wizard detects your setup and writes
`~/.ghost/config.toml`:

```
Ghost setup — pick your LLM backend

  [1] Claude Code   (detected: /usr/local/bin/claude)   ← recommended
  [2] Ollama        (3 local models: llama3.2, qwen2.5, mistral)
  [3] OpenRouter    (set $OPENROUTER_API_KEY)
  ...
```

It then asks for a device nickname and a default mode, saves your config, and
**resumes the command you originally typed** — you never re-type it.

Prefer no prompts? Configure it in one shot, or drive everything from env vars:

```bash
ghost setup --backend claude-code --model sonnet --mode fast --device asus:R58NXXXXXXX
GHOST_BACKEND=ollama GHOST_MODEL=llama3.2 ghost "open settings"
```

## Task runs

```bash
ghost "<task>" [--device D] [--mode M] [--backend B]
```

- **`--device` / `-d` / `--udid`** — a nickname from `~/.ghost/devices.toml`
  (e.g. `asus`) or a raw serial / ref. With one device connected it is auto-picked;
  with several, `ghost` asks you to name one.
- **`--mode fast | vision | reason`** — `fast` reads the screen as text (cheapest),
  `vision` attaches screenshots, `reason` favors deliberate multi-step planning.
- **`--backend`** — override the configured LLM backend for this run.

Quote your task. A bare word that matches a subcommand (below) is treated as that
subcommand — `ghost "record my day"` (quoted) runs a task; `ghost record …` would
be a command. `ghost -- "<task>"` always forces task mode.

## Commands

| Command | What it does |
|---------|--------------|
| `ghost "<task>"` | Run an agent task on a device |
| `ghost devices` | List connected devices + your aliases |
| `ghost setup` | First-run wizard (or `--backend …` non-interactively) |
| `ghost configure` | Edit config interactively |
| `ghost config get <key>` / `set <key>=<val>` / `path` | Read/write config |
| `ghost mcp install --client <name>` | Register Ghost's MCP server with a client |
| `ghost up` | Start the Ghost server + dashboard |
| `ghost doctor` | Check your environment (adb, ports, keys) |
| `ghost login` | Sign in via your Claude subscription |
| `ghost skill …` | Manage skills (install/list/run/…) |

## Connect an MCP client

Register Ghost's MCP server (`android-agent`) with your agent client in one step:

```bash
ghost mcp install --client claude-code
ghost mcp install --client cursor
ghost mcp install --client codex
ghost mcp install --client opencode
```

Each writes (or merges into) that client's config — for example OpenCode's
`~/.config/opencode/opencode.json` gains an `mcp` entry running `android-agent-mcp`.
Existing entries are preserved.

## Config & files

```
~/.ghost/config.toml     backend, model, default mode, default device, dashboard port
~/.ghost/devices.toml    your device aliases  (alias → serial/ref)
~/.ghost/skills/         installed skills
~/.ghost/logs/           session logs
```

Resolution precedence, highest first: **command-line flag → `GHOST_*` env →
`~/.ghost/config.toml` → detected default.**
