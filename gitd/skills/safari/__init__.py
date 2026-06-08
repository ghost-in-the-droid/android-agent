"""iOS browser demo skill."""
from pathlib import Path

from gitd.skills.base import Skill

from .actions.core import OpenBrowser, OpenSafari, OpenUrl, ReadNews, VerifyPage
from .workflows import OpenGhostSite, ReadNewsWorkflow


def load() -> Skill:
    s = Skill(Path(__file__).parent)
    s.register_action(OpenBrowser)
    s.register_action(OpenSafari)
    s.register_action(OpenUrl)
    s.register_action(VerifyPage)
    s.register_action(ReadNews)
    s.register_workflow(OpenGhostSite)
    s.register_workflow(ReadNewsWorkflow)
    return s
