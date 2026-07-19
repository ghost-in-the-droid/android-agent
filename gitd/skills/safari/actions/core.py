"""iOS browser demo actions."""

from __future__ import annotations

import os
import time

from gitd.bots.common.device import is_ios_ref
from gitd.skills.base import Action, ActionResult

DEFAULT_BROWSER_BUNDLE_ID = "com.google.chrome.ios"


def _default_bundle_id() -> str:
    return os.getenv("IOS_BUNDLE_ID", DEFAULT_BROWSER_BUNDLE_ID)


class OpenBrowser(Action):
    name = "open_browser"
    description = "Launch the configured iOS browser"
    max_retries = 1

    def __init__(self, device, elements=None, bundle_id: str | None = None, **kw):
        super().__init__(device, elements)
        self.bundle_id = bundle_id or _default_bundle_id()

    def execute(self) -> ActionResult:
        if not is_ios_ref(getattr(self.device, "serial", "")):
            return ActionResult(success=False, error="iOS browser demo skill requires an iOS device ref")
        self.device.launch_app(self.bundle_id)
        return ActionResult(success=True, data={"bundle_id": self.bundle_id})


class OpenSafari(OpenBrowser):
    name = "open_safari"
    description = "Launch the configured iOS browser; kept as a compatibility alias"


class OpenUrl(Action):
    name = "open_url"
    description = "Open a URL in the active iOS browser"
    max_retries = 2

    def __init__(self, device, elements=None, url: str = "https://ghostinthedroid.com", **kw):
        super().__init__(device, elements)
        self.url = url

    def execute(self) -> ActionResult:
        if not is_ios_ref(getattr(self.device, "serial", "")):
            return ActionResult(success=False, error="open_url requires an iOS device ref")
        url = self.url.strip()
        if url and "://" not in url:
            url = "https://" + url
        self.device.open_url(url)
        return ActionResult(success=True, data={"url": url})


class VerifyPage(Action):
    name = "verify_page"
    description = "Verify expected text is visible in the iOS browser source"
    max_retries = 3
    retry_delay = 1.0

    def __init__(self, device, elements=None, expected: str = "ghostinthedroid", **kw):
        super().__init__(device, elements)
        self.expected = expected

    def execute(self) -> ActionResult:
        time.sleep(1.0)
        xml = self.device.dump_xml()
        if self.expected.lower() in xml.lower():
            return ActionResult(success=True, data={"expected": self.expected})
        return ActionResult(success=False, error=f"Expected text not visible: {self.expected}")


class ReadNews(Action):
    name = "read_news"
    description = "Open a news site in iOS Chrome/browser and extract headlines plus article snippets"
    max_retries = 1

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

    def execute(self) -> ActionResult:
        serial = getattr(self.device, "serial", "")
        if not is_ios_ref(serial):
            return ActionResult(success=False, error="read_news requires an iOS device ref")

        from gitd.services.browser import read_news

        result = read_news(
            serial,
            self.url,
            max_headlines=self.max_headlines,
            max_articles=self.max_articles,
            bundle_id=self.bundle_id,
            wait_s=self.wait_s,
            save_screenshots=self.save_screenshots,
            out_dir=self.out_dir,
        )
        if result.get("ok"):
            return ActionResult(success=True, data=result)
        return ActionResult(
            success=False,
            data=result,
            error=result.get("error") or "read_news did not return headlines",
        )
