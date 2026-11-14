"""Skills framework — Action/Workflow/Skill base classes for Android automation."""

from gitd.skills.base import Action, ActionResult, Skill, Workflow
from gitd.skills.locations import OFFICIAL_AUTHOR, find_skillhub_root

# v1 compat: official skills moved to <repo>/skillhub/ghost/<slug>/. Extending
# the package path keeps `import gitd.skills.<slug>` working for the v1 runtime
# in a source checkout. v2 skills never rely on this (they import by file path).
_hub = find_skillhub_root()
if _hub is not None and (_hub / OFFICIAL_AUTHOR).is_dir():
    __path__.append(str(_hub / OFFICIAL_AUTHOR))
del _hub

__all__ = ["Action", "Workflow", "Skill", "ActionResult"]
