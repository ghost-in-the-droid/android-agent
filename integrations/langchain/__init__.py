"""LangChain adapter — give any LangChain agent an Android body.

    from integrations.langchain import ghost_langchain_tools

    tools = ghost_langchain_tools("emulator-5554")
    agent = create_react_agent(llm, tools)      # tools now control a real phone

Requires the ``langchain`` extra: ``pip install ghost-in-the-droid[langchain]``.
"""

from __future__ import annotations

from integrations._core import build_ghost_tools, pydantic_args_model


def ghost_langchain_tools(device: str, *, include_dangerous: bool = False) -> list:
    """Return Ghost's device tools as a list of LangChain ``StructuredTool``s.

    Each tool is bound to ``device`` and takes only the tool-specific args (no
    ``device`` arg). By default the raw-shell / run-skill tools are excluded;
    pass ``include_dangerous=True`` to include them.
    """
    from langchain_core.tools import StructuredTool

    tools = []
    for gt in build_ghost_tools(device, include_dangerous=include_dangerous):
        args_model = pydantic_args_model(gt.name, gt.args_schema)
        tools.append(
            StructuredTool.from_function(
                func=gt.run,
                name=gt.name,
                description=gt.description,
                args_schema=args_model,
                infer_schema=False,
            )
        )
    return tools


__all__ = ["ghost_langchain_tools"]
