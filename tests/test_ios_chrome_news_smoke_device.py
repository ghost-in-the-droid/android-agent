"""Device-backed iOS smoke / health check.

Unlike ``test_ios_chrome_news_smoke.py`` (fast, fully mocked unit tests of the
CLI control flow), this drives a **real iPhone** end-to-end through Ghost's iOS
device backend: opens Chrome, loads text.npr.org, and extracts headlines +
article bodies. It is the on-demand health check surfaced in the dashboard's
"Device Health" tab and runnable via the Test Runner.

Gated: it only runs when an iOS device target is present (the Test Runner sets
``DEVICE=ios:<udid>``; locally set ``IOS_DEVICE_UDID``). It skips otherwise, so
CI stays green without hardware. Requires the tunnel + Appium + WDA signing to
be up (see ``ghost-ios up`` / the iOS setup guide).
"""
import os

import pytest

from gitd.services.browser import read_news


def _ios_target() -> str:
    device = os.getenv("DEVICE", "")
    if device.startswith("ios:"):
        return device
    udid = os.getenv("IOS_DEVICE_UDID", "")
    return f"ios:{udid}" if udid else ""


pytestmark = pytest.mark.skipif(
    not _ios_target(),
    reason="no iOS device target (set IOS_DEVICE_UDID or DEVICE=ios:<udid>) — device health test",
)

MIN_HEADLINES = 5
MIN_ARTICLE_BODIES = 3


def test_ios_chrome_news_smoke_on_device(tmp_path):
    device = _ios_target()
    result = read_news(
        device,
        "https://text.npr.org/",
        max_headlines=MIN_HEADLINES,
        max_articles=MIN_ARTICLE_BODIES,
        bundle_id=os.getenv("IOS_BUNDLE_ID", "com.google.chrome.ios"),
        wait_s=2.0,
        save_screenshots=True,
        out_dir=str(tmp_path),
    )

    assert result.get("ok"), f"read_news did not succeed: {result.get('error')!r}"

    headlines = result.get("headlines") or []
    assert len(headlines) >= MIN_HEADLINES, (
        f"expected >= {MIN_HEADLINES} headlines, got {len(headlines)}"
    )

    articles = result.get("articles") or []
    bodies = [a for a in articles if len(str(a.get("body_snippet") or "").strip()) > 40]
    assert len(bodies) >= MIN_ARTICLE_BODIES, (
        f"expected >= {MIN_ARTICLE_BODIES} non-empty article bodies, got {len(bodies)}"
    )
