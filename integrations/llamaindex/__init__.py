"""LlamaIndex adapter — give any LlamaIndex agent an Android body.

    from integrations.llamaindex import ghost_llamaindex_tools

    tools = ghost_llamaindex_tools("emulator-5554")
    agent = FunctionAgent(tools=tools, llm=llm)   # tools now control a real phone

Requires the ``llamaindex`` extra: ``pip install ghost-in-the-droid[llamaindex]``.
"""

from __future__ import annotations

from integrations._core import build_ghost_tools, pydantic_args_model


def ghost_llamaindex_tools(device: str, *, include_dangerous: bool = False) -> list:
    """Return Ghost's device tools as a list of LlamaIndex ``FunctionTool``s.

    Each tool is bound to ``device`` and takes only the tool-specific args. By
    default the raw-shell / run-skill tools are excluded; pass
    ``include_dangerous=True`` to include them.
    """
    from llama_index.core.tools import FunctionTool

    tools = []
    for gt in build_ghost_tools(device, include_dangerous=include_dangerous):
        fn_schema = pydantic_args_model(gt.name, gt.args_schema)
        tools.append(
            FunctionTool.from_defaults(
                fn=gt.run,
                name=gt.name,
                description=gt.description,
                fn_schema=fn_schema,
            )
        )
    return tools


__all__ = ["ghost_llamaindex_tools"]
