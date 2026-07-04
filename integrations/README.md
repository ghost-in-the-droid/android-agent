# Ghost integrations — an Android body for your agent

Drop real Android device control into an existing **LangChain** or **LlamaIndex**
agent. Every one of Ghost's on-device tools (`tap`, `type_text`, `launch_app`,
`get_screen_tree`, `find_on_screen`, screenshots, OCR, …) becomes a native tool
in your framework — no rewrite, no separate runner.

Nothing in Ghost's core imports these adapters; the framework deps are optional
extras.

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

## Fallback: point any MCP-aware agent at Ghost's MCP endpoint

Both frameworks speak MCP, so you can also skip the adapters and connect to
Ghost's MCP server directly:

```bash
python3 -m gitd.mcp_server        # serves MCP at http://127.0.0.1:8002/mcp
```

Then register that endpoint with your framework's MCP client (e.g. LangChain's
`langchain-mcp-adapters` or LlamaIndex's `McpToolSpec`).

## Notes

- **Device binding**: the serial is bound when you build the toolset, so the
  agent never has to pass `device` — and a bound serial can't be overridden by
  a tool argument.
- **Safety default**: the raw-`shell` and `run_skill` tools are excluded by
  default. Pass `include_dangerous=True` to `ghost_langchain_tools` /
  `ghost_llamaindex_tools` to include them.
