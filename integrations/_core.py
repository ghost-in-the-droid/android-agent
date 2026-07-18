"""Framework-agnostic bridge from Ghost's tool catalog to agent frameworks.

Turns each entry in ``gitd.services.agent_tools.TOOLS`` into a device-bound
callable plus a JSON schema, so any adapter (LangChain, LlamaIndex, or your
own) can wrap Ghost's device tools without re-describing them. No third-party
deps here — this module is unit-testable on its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class GhostTool:
    """One device tool, ready to hand to an agent framework.

    ``args_schema`` is the tool's JSON schema with the ``device`` field removed
    (the device is bound into ``run`` when the toolset is built, so the agent
    never has to pass it). ``run(**kwargs)`` executes the tool and returns its
    string result.
    """

    name: str
    description: str
    args_schema: dict
    run: Callable[..., str]


def _schema_without_device(schema: dict) -> dict:
    """Drop the ``device`` property/requirement — it's bound, not agent-supplied."""
    props = {k: v for k, v in (schema.get("properties") or {}).items() if k != "device"}
    required = [r for r in (schema.get("required") or []) if r != "device"]
    return {"type": "object", "properties": props, "required": required}


def build_ghost_tools(device: str, *, include_dangerous: bool = False) -> list[GhostTool]:
    """Build device-bound GhostTools from the shared tool catalog.

    Args:
        device: the ADB serial every tool call is bound to.
        include_dangerous: if False (default), ONLY tools on the vetted
            ``SAFE_DEVICE_TOOLS`` allow-list are exposed. This fails closed —
            raw ``shell``/``run_skill`` and any future un-vetted tool are left
            out until deliberately added to the allow-list. Pass True to hand
            the agent every tool (use only when you fully trust the agent).
    """
    # Imported lazily so this package never forces gitd to load at import time.
    from gitd.services.agent_tools import SAFE_DEVICE_TOOLS, TOOLS, execute_tool

    tools: list[GhostTool] = []
    for spec in TOOLS:
        name = spec["name"]
        if not include_dangerous and name not in SAFE_DEVICE_TOOLS:
            continue

        def _make_run(tool_name: str) -> Callable[..., str]:
            def _run(**kwargs: Any) -> str:
                args = dict(kwargs)
                args["device"] = device  # bind — always overrides any passed value
                return execute_tool(tool_name, args)

            return _run

        tools.append(
            GhostTool(
                name=name,
                description=spec.get("description", ""),
                args_schema=_schema_without_device(spec.get("input_schema", {})),
                run=_make_run(name),
            )
        )
    return tools


_JSON_TYPE_TO_PY: dict[str, type] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "object": dict,
    "array": list,
}


def pydantic_args_model(tool_name: str, args_schema: dict):
    """Build a pydantic model from a GhostTool.args_schema.

    Ghost's schemas are flat objects of scalar/simple properties, so a shallow
    conversion is enough. Used by the LangChain adapter (which wants a pydantic
    args_schema) — kept here so it's covered by the dep-free test suite.
    """
    from typing import Optional

    from pydantic import create_model

    props = args_schema.get("properties") or {}
    required = set(args_schema.get("required") or [])
    fields: dict[str, tuple] = {}
    for key, spec in props.items():
        py_type = _JSON_TYPE_TO_PY.get(spec.get("type", "string"), str)
        if key in required:
            fields[key] = (py_type, ...)
        else:
            fields[key] = (Optional[py_type], None)
    # Sanitize the model name (tool names are already identifier-safe).
    return create_model(f"{tool_name}_Args", **fields)
