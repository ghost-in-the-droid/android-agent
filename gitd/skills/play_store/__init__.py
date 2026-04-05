"""Play Store skill — install, uninstall, update apps via Google Play."""
from pathlib import Path
from gitd.skills.base import Skill
from .actions.core import (
    OpenStore, SearchApp, InstallApp, UninstallApp, UpdateApp, CheckVersion,
)
from .workflows import InstallByName


def load() -> Skill:
    s = Skill(Path(__file__).parent)
    s.register_action(OpenStore)
    s.register_action(SearchApp)
    s.register_action(InstallApp)
    s.register_action(UninstallApp)
    s.register_action(UpdateApp)
    s.register_action(CheckVersion)
    s.register_workflow(InstallByName)
    return s
