"""iOS browser demo workflows."""
from __future__ import annotations

from gitd.skills.base import Action, EngineConfig, Workflow

from .actions.core import OpenBrowser, OpenUrl, ReadNews, VerifyPage, _default_bundle_id


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


class ReadNewsWorkflow(Workflow):
    name = "read_news"
    description = "Read headlines and article snippets from a text-friendly news site in iOS Chrome/browser"
    engine = EngineConfig(back_count=0, auto_launch=False, skip_popup_detect=True)

    def __init__(
        self,
        device,
        elements=None,
        url: str = "https://text.npr.org/",
        max_headlines: int = 5,
        max_articles: int = 3,
        bundle_id: str | None = None,
        wait_s: float = 2.0,
        save_screenshots: bool = False,
        out_dir: str | None = None,
        **kw,
    ):
        super().__init__(device, elements)
        self.url = url
        self.max_headlines = max_headlines
        self.max_articles = max_articles
        self.bundle_id = bundle_id or _default_bundle_id()
        self.wait_s = wait_s
        self.save_screenshots = save_screenshots
        self.out_dir = out_dir

    def steps(self) -> list[Action]:
        return [
            ReadNews(
                self.device,
                self.elements,
                url=self.url,
                max_headlines=self.max_headlines,
                max_articles=self.max_articles,
                bundle_id=self.bundle_id,
                wait_s=self.wait_s,
                save_screenshots=self.save_screenshots,
                out_dir=self.out_dir,
            )
        ]
