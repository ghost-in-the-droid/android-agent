"""Ghost in the Droid — Skill Engine v2.

Executes skill.yaml files written against Schema v2 (see docs/skill-schema-v2.md).

Public surface:
    from gitd.skills.engine import load_skill, run_action

    skill = load_skill("skillhub/ghost/tiktok")
    result = run_action(skill, "get_active_account", params={}, device_serial="<serial>")
    print(result.data["handle"])   # → "your_handle"

For the full concept + primitives, see:
    - docs/skill-schema-v2.md
    - docs/skill-taxonomy-soft-vs-hard.md
    - docs/features/skill-execution-engine.md  (engine reference)
"""
from __future__ import annotations

from gitd.skills.engine.loader import SkillDef, ActionDef, load_skill
from gitd.skills.engine.runner import run_action, RunResult
from gitd.skills.engine.context import RunContext

__all__ = [
    "SkillDef",
    "ActionDef",
    "load_skill",
    "run_action",
    "RunResult",
    "RunContext",
]
