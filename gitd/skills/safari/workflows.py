"""iOS browser demo workflows."""
from __future__ import annotations

from gitd.skills.base import Action, EngineConfig, Workflow

from .actions.core import OpenBrowser, OpenUrl, VerifyPage, _default_bundle_id


class OpenGhostSite(Workflow):
    name = "open_ghost_site"
    description = "Open ghostinthedroid.com in the configured iOS browser"
    engine = EngineConfig(back_count=0, launch_settle=1.0, skip_popup_detect=True)

    def __init__(
        self,
        device,
        elements=None,
        url: str = "https://ghostinthedroid.com",
        bundle_id: str | None = None,
        **kw,
    ):
        super().__init__(device, elements)
        self.url = url
        self.bundle_id = bundle_id or _default_bundle_id()

    def steps(self) -> list[Action]:
        return [
            OpenBrowser(self.device, self.elements, bundle_id=self.bundle_id),
            OpenUrl(self.device, self.elements, url=self.url),
            VerifyPage(self.device, self.elements, expected="ghostinthedroid"),
        ]
