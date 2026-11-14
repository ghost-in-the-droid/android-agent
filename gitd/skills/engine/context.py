"""RunContext — shared state passed through every step + validator of an action run.

Steps and python_actions read `params` (immutable within a run) and read/write
`result` (typed action output). Free-form attrs (e.g. `media_id`) live on the
context directly for cross-step handoffs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RunContext:
    """State carried through one action's step chain."""

    # Immutable inputs
    action_name: str
    params: dict = field(default_factory=dict)
    device_serial: str = ""

    # Mutable output — validators read this; helpers write to it
    result: dict = field(default_factory=dict)

    # Bookkeeping
    step_index: int = 0
    step_count: int = 0

    # Free-form cross-step state (media_id, session tokens, etc.)
    # Set via `ctx.<name> = value` in a python_action, read via `ctx.<name>` later.
    extras: dict = field(default_factory=dict)

    def __getattr__(self, name: str) -> Any:
        # Allow ctx.media_id shorthand for ctx.extras["media_id"]
        if name.startswith("_"):
            raise AttributeError(name)
        extras = self.__dict__.get("extras", {})
        if name in extras:
            return extras[name]
        raise AttributeError(f"RunContext has no attribute {name!r}")

    def __setattr__(self, name: str, value: Any) -> None:
        # Fields declared at class level go to __dict__; anything else to extras
        if name in {"action_name", "params", "device_serial", "result", "step_index", "step_count", "extras"}:
            object.__setattr__(self, name, value)
        else:
            self.__dict__.setdefault("extras", {})[name] = value
