import json
import os

import pytest
from fastapi.testclient import TestClient

from gitd.app import app
from gitd.bots.common.ios import IOSDevice
from gitd.services.agent_tools import execute_tool
from gitd.services.browser import extract_articles, extract_visible_text, open_url, read_news, wait_for_text


class FakeNewsIOSDevice:
    serial = "ios:abc123"
    bundle_id = "com.google.chrome.ios"

    def __init__(self):
        self.current_url = ""
        self.launched = []
        self.opened_urls = []
        self.back_count = 0

    def launch_app(self, bundle_id):
        self.launched.append(bundle_id)

    def open_url(self, url, delay=2.0):
        self.current_url = url
        self.opened_urls.append(url)
        return {"ok": True, "expected_url": url, "url": url, "state": "url_matched", "method": "fake"}

    def get_current_url(self):
        return self.current_url

    def extract_articles(self, max_items=5):
        return [
            {
                "title": "First major story from the test fixture",
                "url": "https://text.npr.org/article/1",
                "bounds": {"x1": 10, "y1": 20, "x2": 350, "y2": 60},
                "center": {"x": 180, "y": 40},
                "class": "a",
                "provenance": "web_context",
            },
            {
                "title": "Second major story from the test fixture",
                "url": "https://text.npr.org/article/2",
                "bounds": {"x1": 10, "y1": 80, "x2": 350, "y2": 120},
                "center": {"x": 180, "y": 100},
                "class": "a",
                "provenance": "web_context",
            },
        ][:max_items]

    def extract_visible_text(self, max_lines=200, include_controls=False):
        if self.current_url.endswith("/article/1"):
            return "First article title\nFirst article body line.\nFirst article body line."
        if self.current_url.endswith("/article/2"):
            return "Second article title\nSecond article body line."
        return "NPR text home\nFirst major story from the test fixture\nSecond major story from the test fixture"

    def take_screenshot(self):
        return b"fake-png"

    def tap(self, x, y, delay=0.6):
        self.current_url = "ocr_article"

    def browser_back(self, delay=1.0):
        self.back_count += 1
        self.current_url = "https://text.npr.org/"


def test_read_news_opens_headlines_and_extracts_article_snippets(monkeypatch, tmp_path):
    fake = FakeNewsIOSDevice()
    monkeypatch.setattr("gitd.services.browser.get_device", lambda device: fake)
    monkeypatch.setattr("gitd.services.browser.time.sleep", lambda *_args, **_kwargs: None)

    result = read_news(
        "ios:abc123",
        "text.npr.org",
        max_headlines=2,
        max_articles=2,
        save_screenshots=True,
        out_dir=str(tmp_path),
    )

    assert result["ok"] is True
    assert result["url"] == "https://text.npr.org"
    assert fake.launched == ["com.google.chrome.ios"]
    assert fake.opened_urls == ["https://text.npr.org", "https://text.npr.org/article/1", "https://text.npr.org/article/2"]
    assert fake.back_count == 2
    assert result["navigation"]["state"] == "url_matched"
    assert result["extraction"]["headlines"] == {
        "requested": 2,
        "target": 2,
        "returned": 2,
        "ready": True,
        "attempts": 1,
        "source": "web_context",
    }
    assert result["extraction"]["front_page_text"]["ready"] is True
    assert result["extraction"]["front_page_text"]["source"] == "native_or_web"
    assert [item["title"] for item in result["headlines"]] == [
        "First major story from the test fixture",
        "Second major story from the test fixture",
    ]
    assert result["articles"][0]["navigation"]["url"] == "https://text.npr.org/article/1"
    assert result["articles"][0]["page_title"] == "First article title"
    assert result["articles"][0]["body_snippet"] == "First article title\nFirst article body line."
    assert result["articles"][0]["headline_provenance"] == "web_context"
    assert result["extraction"]["articles"][0]["open_method"] == "url"
    assert result["extraction"]["articles"][0]["text"]["returned_lines"] == 3
    assert result["articles"][1]["opened"] is True
    assert (tmp_path / "front_page.png").read_bytes() == b"fake-png"
    assert (tmp_path / "article_1.png").read_bytes() == b"fake-png"


def test_read_news_retries_until_headlines_and_article_text_are_ready(monkeypatch):
    class DelayedNewsDevice(FakeNewsIOSDevice):
        def __init__(self):
            super().__init__()
            self.article_extraction_calls = 0
            self.text_calls: dict[str, int] = {}

        def extract_articles(self, max_items=5):
            self.article_extraction_calls += 1
            if self.article_extraction_calls == 1:
                return []
            return super().extract_articles(max_items=max_items)

        def extract_visible_text(self, max_lines=200, include_controls=False):
            calls = self.text_calls.get(self.current_url, 0)
            self.text_calls[self.current_url] = calls + 1
            if self.current_url.endswith("/article/1") and calls == 0:
                return ""
            return super().extract_visible_text(max_lines=max_lines, include_controls=include_controls)

    fake = DelayedNewsDevice()
    monkeypatch.setattr("gitd.services.browser.get_device", lambda device: fake)
    monkeypatch.setattr("gitd.services.browser.time.sleep", lambda *_args, **_kwargs: None)

    result = read_news("ios:abc123", "https://text.npr.org/", max_headlines=1, max_articles=1, wait_s=1)

    assert result["ok"] is True
    assert fake.article_extraction_calls == 2
    assert fake.text_calls["https://text.npr.org/article/1"] == 2
    assert result["extraction"]["headlines"]["attempts"] == 2
    assert result["extraction"]["articles"][0]["text"]["attempts"] == 2
    assert result["articles"][0]["body_snippet"] == "First article title\nFirst article body line."


def test_read_news_waits_for_requested_headline_count(monkeypatch):
    class PartialHeadlineDevice(FakeNewsIOSDevice):
        def __init__(self):
            super().__init__()
            self.article_extraction_calls = 0

        def extract_articles(self, max_items=5):
            self.article_extraction_calls += 1
            articles = super().extract_articles(max_items=max_items)
            if self.article_extraction_calls == 1:
                return articles[:1]
            return articles

    fake = PartialHeadlineDevice()
    monkeypatch.setattr("gitd.services.browser.get_device", lambda device: fake)
    monkeypatch.setattr("gitd.services.browser.time.sleep", lambda *_args, **_kwargs: None)

    result = read_news("ios:abc123", "https://text.npr.org/", max_headlines=2, max_articles=0, wait_s=1)

    assert result["ok"] is True
    assert fake.article_extraction_calls == 2
    assert [item["title"] for item in result["headlines"]] == [
        "First major story from the test fixture",
        "Second major story from the test fixture",
    ]


def test_read_news_waits_for_article_body_beyond_title(monkeypatch):
    class TitleOnlyArticleDevice(FakeNewsIOSDevice):
        def __init__(self):
            super().__init__()
            self.text_calls: dict[str, int] = {}

        def extract_visible_text(self, max_lines=200, include_controls=False):
            calls = self.text_calls.get(self.current_url, 0)
            self.text_calls[self.current_url] = calls + 1
            if self.current_url.endswith("/article/1") and calls == 0:
                return "First article title"
            return super().extract_visible_text(max_lines=max_lines, include_controls=include_controls)

    fake = TitleOnlyArticleDevice()
    monkeypatch.setattr("gitd.services.browser.get_device", lambda device: fake)
    monkeypatch.setattr("gitd.services.browser.time.sleep", lambda *_args, **_kwargs: None)

    result = read_news("ios:abc123", "https://text.npr.org/", max_headlines=1, max_articles=1, wait_s=1)

    assert result["ok"] is True
    assert fake.text_calls["https://text.npr.org/article/1"] == 2
    assert result["articles"][0]["body_snippet"] == "First article title\nFirst article body line."


def test_ios_extract_visible_text_falls_back_to_ocr(monkeypatch):
    class EmptyTextDevice(FakeNewsIOSDevice):
        def extract_visible_text(self, max_lines=200, include_controls=False):
            return ""

    monkeypatch.setattr("gitd.services.browser.get_device", lambda device: EmptyTextDevice())
    monkeypatch.setattr(
        "gitd.services.device_context.ocr_screen",
        lambda device: [
            {"text": "OCR headline line", "conf": 0.91, "x": 10, "y": 40, "w": 200, "h": 24},
            {"text": "OCR body line", "conf": 0.87, "x": 10, "y": 80, "w": 180, "h": 24},
        ],
    )

    result = extract_visible_text("ios:abc123", max_lines=5)

    assert result["source"] == "ocr"
    assert result["lines"] == ["OCR headline line", "OCR body line"]


def test_ios_extract_articles_falls_back_to_ocr(monkeypatch):
    class EmptyArticleDevice(FakeNewsIOSDevice):
        def extract_articles(self, max_items=5):
            return []

    monkeypatch.setattr("gitd.services.browser.get_device", lambda device: EmptyArticleDevice())
    monkeypatch.setattr(
        "gitd.services.device_context.ocr_screen",
        lambda device: [
            {"text": "World leaders meet for climate talks today", "conf": 0.91, "x": 10, "y": 40, "w": 300, "h": 24},
            {"text": "Menu", "conf": 0.94, "x": 10, "y": 10, "w": 80, "h": 20},
        ],
    )

    result = extract_articles("ios:abc123", max_items=3)

    assert result["source"] == "ocr"
    assert result["articles"] == [
        {
            "title": "World leaders meet for climate talks today",
            "url": "",
            "bounds": {"x1": 10, "y1": 40, "x2": 310, "y2": 64},
            "center": {"x": 160, "y": 52},
            "class": "ocr",
            "provenance": "ocr",
            "confidence": 0.91,
        }
    ]


def test_read_news_can_complete_with_ocr_only_extraction(monkeypatch):
    class OcrOnlyDevice(FakeNewsIOSDevice):
        def __init__(self):
            super().__init__()
            self.taps = []

        def extract_articles(self, max_items=5):
            return []

        def extract_visible_text(self, max_lines=200, include_controls=False):
            return ""

        def tap(self, x, y, delay=0.6):
            self.taps.append((x, y))
            self.current_url = "ocr_article"

    fake = OcrOnlyDevice()

    def fake_ocr(device):
        if fake.current_url == "ocr_article":
            return [
                {"text": "World leaders meet for climate talks today", "conf": 0.91, "x": 10, "y": 40, "w": 300, "h": 24},
                {"text": "The first paragraph appears in OCR.", "conf": 0.86, "x": 10, "y": 80, "w": 330, "h": 24},
            ]
        return [
            {"text": "World leaders meet for climate talks today", "conf": 0.91, "x": 10, "y": 120, "w": 300, "h": 24}
        ]

    monkeypatch.setattr("gitd.services.browser.get_device", lambda device: fake)
    monkeypatch.setattr("gitd.services.device_context.ocr_screen", fake_ocr)
    monkeypatch.setattr("gitd.services.browser.time.sleep", lambda *_args, **_kwargs: None)

    result = read_news("ios:abc123", "https://text.npr.org/", max_headlines=1, max_articles=1, wait_s=0)

    assert result["ok"] is True
    assert result["headlines"][0]["provenance"] == "ocr"
    assert result["extraction"]["headlines"]["source"] == "ocr"
    assert fake.taps == [(160, 132)]
    assert result["articles"][0]["open_method"] == "center"
    assert result["extraction"]["articles"][0]["text"]["source"] == "ocr"
    assert result["articles"][0]["body_snippet"] == (
        "World leaders meet for climate talks today\nThe first paragraph appears in OCR."
    )


def test_read_news_android_returns_explicit_unsupported():
    result = read_news("emulator-5554", "https://text.npr.org/")

    assert result["ok"] is False
    assert result["platform"] == "android"
    assert "currently implemented for iOS" in result["error"]


def test_ios_open_url_service_returns_navigation_evidence(monkeypatch):
    fake = FakeNewsIOSDevice()
    monkeypatch.setattr("gitd.services.browser.get_device", lambda device: fake)

    result = open_url("ios:abc123", "text.npr.org", bundle_id="com.google.chrome.ios")

    assert result == {
        "ok": True,
        "platform": "ios",
        "url": "https://text.npr.org",
        "navigation": {
            "ok": True,
            "expected_url": "https://text.npr.org",
            "url": "https://text.npr.org",
            "state": "url_matched",
            "method": "fake",
        },
    }
    assert fake.bundle_id == "com.google.chrome.ios"


def test_android_wait_for_text_retries_until_match(monkeypatch):
    calls = []

    def fake_find(device, text):
        calls.append((device, text))
        if len(calls) < 3:
            return None
        return {"text": "Loaded headline", "x": 20, "y": 40, "w": 100, "h": 20, "method": "xml"}

    monkeypatch.setattr("gitd.services.device_context.find_on_screen", fake_find)
    monkeypatch.setattr("gitd.services.browser.time.sleep", lambda *_args, **_kwargs: None)

    result = wait_for_text("emulator-5554", "headline", timeout=1)

    assert result["ok"] is True
    assert result["platform"] == "android"
    assert result["found"] is True
    assert result["attempts"] == 3
    assert result["match"]["text"] == "Loaded headline"
    assert calls == [
        ("emulator-5554", "headline"),
        ("emulator-5554", "headline"),
        ("emulator-5554", "headline"),
    ]


def test_android_wait_for_text_returns_structured_timeout(monkeypatch):
    monkeypatch.setattr("gitd.services.device_context.find_on_screen", lambda device, text: None)

    result = wait_for_text("emulator-5554", "missing text", timeout=0)

    assert result == {
        "ok": False,
        "platform": "android",
        "text": "missing text",
        "found": False,
        "match": None,
        "attempts": 1,
        "timeout": 0.0,
    }


def test_ios_wait_for_text_returns_structured_timeout(monkeypatch):
    class TimeoutIOSDevice(FakeNewsIOSDevice):
        def wait_for_text(self, text, timeout=12):
            raise TimeoutError(f"Timed out waiting for {text}")

    fake = TimeoutIOSDevice()
    monkeypatch.setattr("gitd.services.browser.get_device", lambda device: fake)

    result = wait_for_text("ios:abc123", "missing text", timeout=0)

    assert result["ok"] is False
    assert result["platform"] == "ios"
    assert result["found"] is False
    assert result["visible_text"].startswith("NPR text home")
    assert "Timed out waiting" in result["error"]


def test_read_news_rest_route_uses_browser_service(monkeypatch):
    def fake_read_news(device, url, **kwargs):
        return {"ok": True, "device": device, "url": url, "kwargs": kwargs, "headlines": []}

    monkeypatch.setattr("gitd.services.browser.read_news", fake_read_news)
    client = TestClient(app)

    response = client.post(
        "/api/phone/browser/read-news",
        json={"device": "ios:abc123", "url": "https://text.npr.org/", "max_headlines": 4, "max_articles": 2},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["device"] == "ios:abc123"
    assert body["kwargs"]["max_headlines"] == 4
    assert body["kwargs"]["max_articles"] == 2


def test_read_news_agent_tool_dispatches_to_browser_service(monkeypatch):
    def fake_read_news(device, url, **kwargs):
        return {"ok": True, "device": device, "url": url, "kwargs": kwargs, "headlines": [{"title": "One"}]}

    monkeypatch.setattr("gitd.services.browser.read_news", fake_read_news)

    result = json.loads(
        execute_tool(
            "read_news",
            {
                "device": "ios:abc123",
                "url": "https://text.npr.org/",
                "max_headlines": 1,
                "max_articles": 1,
                "wait_s": 0,
            },
        )
    )

    assert result["ok"] is True
    assert result["kwargs"]["max_headlines"] == 1
    assert result["kwargs"]["max_articles"] == 1


def test_ios_wait_for_text_checks_webview_text_before_native_xml(monkeypatch):
    dev = IOSDevice("ios:abc123", appium_url="http://appium.local")
    calls = []

    def fake_extract_visible_text(max_lines=300):
        calls.append(max_lines)
        return "Article body from web context"

    monkeypatch.setattr(dev, "extract_visible_text", fake_extract_visible_text)

    assert dev.wait_for_text("web context", timeout=0.01, interval=0.01) == "Article body from web context"
    assert calls == [300]


@pytest.mark.skipif(
    not (
        os.getenv("IOS_LIVE_NEWS_TEST")
        and os.getenv("IOS_APPIUM_URL")
        and os.getenv("IOS_DEVICE_UDID")
    ),
    reason="set IOS_LIVE_NEWS_TEST=1, IOS_APPIUM_URL, and IOS_DEVICE_UDID to run live iOS Chrome news test",
)
def test_live_ios_chrome_news_workflow():
    from gitd.services.device_context import device_health

    device = f"ios:{os.environ['IOS_DEVICE_UDID']}"
    health = device_health(device)
    assert health["connection"]["status"] == "available", health

    result = read_news(
        device,
        os.getenv("IOS_LIVE_NEWS_URL", "https://text.npr.org/"),
        max_headlines=int(os.getenv("IOS_LIVE_NEWS_HEADLINES", "2")),
        max_articles=int(os.getenv("IOS_LIVE_NEWS_ARTICLES", "1")),
        bundle_id=os.getenv("IOS_BUNDLE_ID", "com.google.chrome.ios"),
        wait_s=float(os.getenv("IOS_LIVE_NEWS_WAIT", "2.0")),
        save_screenshots=False,
    )

    assert result["ok"] is True, result
    assert len(result["headlines"]) >= 1
    assert result["headlines"][0].get("title")
    if result["articles"]:
        assert result["articles"][0].get("opened") is True
        assert result["articles"][0].get("body_snippet")
