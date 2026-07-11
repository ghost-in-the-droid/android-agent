from gitd.skills.safari import load
from gitd.skills.safari.actions.core import ReadNews
from gitd.skills.safari.workflows import ReadNewsWorkflow


class FakeIOSDevice:
    serial = "ios:abc123"


def test_safari_skill_registers_news_reader():
    skill = load()

    assert skill.name == "safari"
    assert "read_news" in skill.list_actions()
    assert "read_news" in skill.list_workflows()


def test_read_news_action_delegates_to_browser_service(monkeypatch, tmp_path):
    calls = []

    def fake_read_news(device, url, **kwargs):
        calls.append({"device": device, "url": url, "kwargs": kwargs})
        return {
            "ok": True,
            "headlines": [{"title": "A real headline from the test"}],
            "articles": [{"page_title": "Article", "body_snippet": "Body"}],
        }

    monkeypatch.setattr("gitd.services.browser.read_news", fake_read_news)

    result = ReadNews(
        FakeIOSDevice(),
        url="https://text.npr.org/",
        max_headlines=4,
        max_articles=2,
        bundle_id="com.google.chrome.ios",
        wait_s=0.25,
        save_screenshots=True,
        out_dir=str(tmp_path),
    ).run()

    assert result.success is True
    assert result.data["headlines"][0]["title"] == "A real headline from the test"
    assert calls == [
        {
            "device": "ios:abc123",
            "url": "https://text.npr.org/",
            "kwargs": {
                "max_headlines": 4,
                "max_articles": 2,
                "bundle_id": "com.google.chrome.ios",
                "wait_s": 0.25,
                "save_screenshots": True,
                "out_dir": str(tmp_path),
            },
        }
    ]


def test_read_news_action_rejects_android_device():
    device = FakeIOSDevice()
    device.serial = "emulator-5554"

    result = ReadNews(device).run()

    assert result.success is False
    assert "requires an iOS device ref" in result.error


def test_read_news_workflow_is_single_product_path_action(monkeypatch):
    monkeypatch.setattr("gitd.skills.base.time.sleep", lambda *_args, **_kwargs: None)
    device = FakeIOSDevice()

    workflow = ReadNewsWorkflow(
        device,
        url="https://text.npr.org/",
        max_headlines=5,
        max_articles=3,
        bundle_id="com.google.chrome.ios",
    )

    steps = workflow.steps()

    assert workflow.engine.auto_launch is False
    assert [step.name for step in steps] == ["read_news"]
    assert steps[0].url == "https://text.npr.org/"
    assert steps[0].max_headlines == 5
    assert steps[0].max_articles == 3
    assert steps[0].bundle_id == "com.google.chrome.ios"
