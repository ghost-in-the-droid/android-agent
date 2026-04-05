"""Base skill — shared actions any app can use."""
from pathlib import Path
from gitd.skills.base import Skill

_SKILL_DIR = Path(__file__).parent


def load() -> Skill:
    """Load the base skill with shared actions."""
    from gitd.skills._base.actions import (
        TapElement, SwipeDirection, TypeText, WaitForElement,
        LaunchApp, TakeScreenshot, DismissPopup, PressBack, PressHome,
    )
    skill = Skill(_SKILL_DIR)
    for cls in [TapElement, SwipeDirection, TypeText, WaitForElement,
                LaunchApp, TakeScreenshot, DismissPopup, PressBack, PressHome]:
        skill.register_action(cls)
    return skill
