---
title: "LangChain & LlamaIndex"
description: Drop real Android device control into an existing LangChain or LlamaIndex agent. Every Ghost tool becomes a native framework tool — no rewrite, no separate runner.
---

⭐ **New in 1.3** — Give the agent you already have a body. Ghost ships first-class adapters for [LangChain](https://www.langchain.com/) and [LlamaIndex](https://www.llamaindex.ai/): every on-device tool (`tap`, `type_text`, `launch_app`, `get_screen_tree`, `find_on_screen`, screenshots, OCR, …) becomes a **native tool in your framework**. No rewrite, no separate runner.

Ghost's core never imports these adapters — the framework dependencies are **optional extras**, so installing Ghost doesn't pull LangChain or LlamaIndex unless you ask for them.

## LangChain

```bash
pip install "ghost-in-the-droid[langchain]"
```

```python
from langchain.chat_models import init_chat_model
from langgraph.prebuilt import create_react_agent
from integrations.langchain import ghost_langchain_tools

tools = ghost_langchain_tools("emulator-5554")   # bound to one device
agent = create_react_agent(init_chat_model("anthropic:claude-sonnet-4"), tools)

agent.invoke({"messages": "Open Settings and turn on Wi-Fi"})
# → the agent taps its way through the real phone
```

Every tool Ghost exposes is now a [LangChain tool](https://python.langchain.com/docs/concepts/tools/) the agent can call, so it slots straight into [LangGraph](https://langchain-ai.github.io/langgraph/) or any existing LangChain agent loop.

## LlamaIndex

```bash
pip install "ghost-in-the-droid[llamaindex]"
```

```python
from llama_index.core.agent.workflow import FunctionAgent
from llama_index.llms.anthropic import Anthropic
from integrations.llamaindex import ghost_llamaindex_tools

tools = ghost_llamaindex_tools("emulator-5554")
agent = FunctionAgent(tools=tools, llm=Anthropic(model="claude-sonnet-4"))

await agent.run("Open the camera and take a selfie")
```

The tools arrive as native [LlamaIndex `FunctionTool`s](https://docs.llamaindex.ai/en/stable/module_guides/deploying/agents/tools/), usable in a [`FunctionAgent`](https://docs.llamaindex.ai/en/stable/understanding/agent/) or any LlamaIndex workflow.

## Fallback: point any MCP agent at Ghost

Both frameworks also speak [MCP](https://modelcontextprotocol.io/), so you can skip the adapters entirely and connect to Ghost's [MCP server](../mcp-server/) directly:

```bash
python3 -m gitd.mcp_server        # serves MCP at http://127.0.0.1:8002/mcp
```

Then register that endpoint with your framework's MCP client — [`langchain-mcp-adapters`](https://github.com/langchain-ai/langchain-mcp-adapters) for LangChain, or [`McpToolSpec`](https://docs.llamaindex.ai/en/stable/api_reference/tools/mcp/) for LlamaIndex. See the [MCP Clients](../mcp-clients/) matrix for every other client that can drive Ghost the same way.

## Two things worth knowing

- **Device binding is locked.** The serial is bound when you build the toolset (`ghost_langchain_tools("emulator-5554")`), so the agent never has to pass a `device` argument — and a bound serial **can't be overridden** by a tool call. One toolset drives exactly one phone.
- **Dangerous tools are opt-in.** The raw `shell` and `run_skill` tools are **excluded by default**. Pass `include_dangerous=True` to `ghost_langchain_tools` / `ghost_llamaindex_tools` if you actually want them.

## When to use which

| You want… | Use |
|---|---|
| Ghost tools inside an **existing** LangChain / LlamaIndex agent | the adapters above |
| To drive Ghost from **another** MCP client (Claude Code, Cursor, …) | the [MCP server](../mcp-server/) + [MCP Clients](../mcp-clients/) |
| A quick one-device script with no framework | Ghost's own [agent chat](../dashboard/) |

## Related

- [MCP Server](../mcp-server/) — the same tools, exposed over MCP
- [MCP Clients](../mcp-clients/) — every client that can drive Ghost
- [ADB Device Control](../adb-device/) — the device layer these tools wrap
- [How Ghost Compares](../how-ghost-compares/) — where the framework-adapter story fits vs alternatives
