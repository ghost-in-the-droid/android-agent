import json

from fastapi.testclient import TestClient

from gitd.app import app
from gitd.bots.common.ios import IOSDevice
from gitd.services.agent_tools import execute_tool
from gitd.services.browser import open_url, read_news


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
    assert [item["title"] for item in result["headlines"]] == [
        "First major story from the test fixture",
        "Second major story from the test fixture",
    ]
    assert result["articles"][0]["navigation"]["url"] == "https://text.npr.org/article/1"
    assert result["articles"][0]["page_title"] == "First article title"
    assert result["articles"][0]["body_snippet"] == "First article title\nFirst article body line."
    assert result["articles"][1]["opened"] is True
    assert (tmp_path / "front_page.png").read_bytes() == b"fake-png"
    assert (tmp_path / "article_1.png").read_bytes() == b"fake-png"


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
