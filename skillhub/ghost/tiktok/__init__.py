"""TikTok skill — v2 schema (agent-invocable actions declared in skill.yaml).

This module intentionally does NOT export a v1-style `load()` factory.
The v2 engine reads skill.yaml directly via gitd.skills.engine.load_skill().

For python_action targets used by skill.yaml steps, see helpers.py.
For custom_python validators, see validators.py.
"""
from pathlib import Path

_SKILL_DIR = Path(__file__).parent
