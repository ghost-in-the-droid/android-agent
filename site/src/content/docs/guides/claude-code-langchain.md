---
title: Claude Code (and Codex) as your LangChain LLM
description: Run a LangChain / LangGraph agent on your local Claude Code subscription — no cloud API key, no per-token cost, ToS-clean.
---

Ghost's LangChain integration lets an agent drive a real phone through 50+
LangChain tools. The LLM behind it is swappable — and you can point it at your
**local Claude Code subscription** (Max/Pro) instead of a paid API. No API key,
no per-token bill, and it's the reliable path: a capable Claude model drives the
tools where small local models hallucinate.

> **Why this is allowed:** the integration **spawns the official `claude` CLI as
> a subprocess** — Anthropic's own first-party client — which is permitted. What
> is **not** permitted (and actively enforced) is routing your subscription's
> OAuth token through a third-party HTTP proxy. Subprocess ✅, token proxy ❌.

## Setup

Requires **Python 3.11+** and the Claude Code CLI already authenticated
(`claude` logged in to your Max/Pro account).

```bash
python3.11 -m venv ~/.ghost-cc-venv
~/.ghost-cc-venv/bin/pip install \
  "git+https://github.com/thehumanworks/langchain-claude-code" \
  langgraph langchain-core
```

One patch is currently needed — the wrapper invokes tools via the private
`tool._run(**args)`, which newer `langchain-core` rejects (`missing keyword-only
argument: config`). Use the public API instead, in
`langchain_claude_code/claude_chat_model.py` → `_wrap_langchain_tool`:

```python
# replace the _arun / _run branch with:
result = await tool.ainvoke(args)
```

## Usage

The key difference from a normal ChatModel: **Claude Code *is* the agent loop.**
It executes bound tools internally (exposing them to the CLI as an in-process
MCP server), so you call `.bind_tools(...).invoke(...)` directly — do **not**
wrap it in `create_react_agent`.

```python
from langchain_claude_code import ChatClaudeCode
from integrations.langchain import ghost_langchain_tools

llm = ChatClaudeCode(
    model="sonnet",
    permission_mode="bypassPermissions",  # auto-approve the phone tool-calls
)
tools = ghost_langchain_tools("<device-serial>")   # 53 phone tools

result = llm.bind_tools(tools).invoke(
    "Open Reddit, go to r/LocalLLaMA, and give me the top 2 posts' "
    "title, upvotes and comments as a JSON array."
)
print(result.content)
```

Claude Code opens the app, navigates, OCRs the screen, and returns the answer —
all on your subscription, no cloud API call.

## Gotchas

- **`permission_mode="bypassPermissions"`** is required, or Claude Code stops and
  asks you to approve each device tool call.
- **Ambient MCP servers shadow your bound tools.** If the working directory has a
  `.mcp.json` (or you have global MCP servers) that expose similar tools, Claude
  Code may call *those* instead of the ones you passed to `.bind_tools(...)`. Run
  it strict so only your bound tools are visible — set `strict_mcp_config=True`
  on the `ClaudeAgentOptions` the wrapper builds. Otherwise you'll see the agent
  "work" but your tools never fire.
- **Forbid the shortcuts.** With `Bash`/`WebFetch`/`WebSearch` available, a capable
  model may shell out to `adb` or fetch the data off the web instead of driving
  the device through your tools. Pass `disallowed_tools=["Bash","WebFetch","WebSearch"]`
  to force it onto the real integration.
- **Python 3.11+** only (the package won't install on 3.10).
- Each LLM turn spawns the `claude` CLI, so it's a little slower than a hosted
  API — fine for demos and batch jobs.
- Bind your LangChain tools; Claude Code runs its own loop, so skip
  `create_react_agent`.

## Coming soon: Codex

The same pattern works for the **OpenAI Codex CLI** (your ChatGPT subscription).
Notes for when the `codex`-backed wrapper lands:

- Codex is logged in via ChatGPT — no API key.
- Pick a **ChatGPT-supported model** (`-m gpt-5.5`); the default `gpt-5.4` and the
  `*-codex` variants error with *"not supported when using Codex with a ChatGPT
  account."*
- Approvals: `--dangerously-bypass-approvals-and-sandbox` (or `-a never`).
- Exit with `/quit`; skip the first-run update prompt and accept the trust
  dialog.
