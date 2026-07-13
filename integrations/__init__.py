"""Ghost in the Droid — agent-framework integrations.

Expose Ghost's on-device tools to other agent ecosystems so any LangChain or
LlamaIndex agent can gain an Android body. The framework-agnostic bridge lives
in ``_core`` (no third-party deps); the ``langchain`` and ``llamaindex``
subpackages are thin wrappers that lazily import their framework.

    from integrations.langchain import ghost_langchain_tools
    tools = ghost_langchain_tools("emulator-5554")

Nothing in ``gitd`` imports this package — it is opt-in and its framework deps
are optional extras (``pip install ghost-in-the-droid[langchain]``).
"""

from integrations._core import GhostTool, build_ghost_tools

__all__ = ["GhostTool", "build_ghost_tools"]
