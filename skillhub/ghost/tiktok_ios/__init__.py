"""TikTok iOS smoke skill."""

from pathlib import Path

from gitd.skills.base import Skill

from .actions import (
    CaptureVisibleText,
    DismissPopup,
    NavigateToProfile,
    OpenApp,
    TapSearch,
    TypeAndSearch,
    VerifyVisibleText,
    WaitVisibleText,
)
from .workflows import OpenAppSmoke, ProfileSmoke, SearchSmoke


def load() -> Skill:
    s = Skill(Path(__file__).parent)
    s.register_action(OpenApp)
    s.register_action(DismissPopup)
    s.register_action(TapSearch)
    s.register_action(TypeAndSearch)
    s.register_action(NavigateToProfile)
    s.register_action(CaptureVisibleText)
    s.register_action(VerifyVisibleText)
    s.register_action(WaitVisibleText)
    s.register_workflow(OpenAppSmoke)
    s.register_workflow(SearchSmoke)
    s.register_workflow(ProfileSmoke)
    return s
