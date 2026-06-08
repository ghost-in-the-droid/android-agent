"""TikTok iOS smoke workflows."""
from __future__ import annotations

from gitd.skills.base import Action, EngineConfig, Workflow

from .actions import DismissPopup, OpenApp, TapSearch, TypeAndSearch


class OpenAppSmoke(Workflow):
    name = "open_app_smoke"
    description = "Launch TikTok on iOS and dismiss common first-run prompts"
    engine = EngineConfig(back_count=0, launch_settle=1.0, skip_popup_detect=True)

    def steps(self) -> list[Action]:
        return [
            OpenApp(self.device, self.elements),
            DismissPopup(self.device, self.elements),
        ]


class SearchSmoke(Workflow):
    name = "search_smoke"
    description = "Launch TikTok on iOS, open search, and submit a query"
    engine = EngineConfig(back_count=0, launch_settle=1.0, skip_popup_detect=True)

    def __init__(self, device, elements=None, query: str = "#fyp", **kwargs):
        super().__init__(device, elements)
        self.query = query

    def steps(self) -> list[Action]:
        return [
            OpenApp(self.device, self.elements),
            DismissPopup(self.device, self.elements),
            TapSearch(self.device, self.elements),
            TypeAndSearch(self.device, self.elements, query=self.query),
        ]
