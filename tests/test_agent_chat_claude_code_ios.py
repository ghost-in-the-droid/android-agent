import inspect

from gitd.services import agent_chat_claude_code


def test_claude_code_auto_tts_skips_ios(monkeypatch):
    started = []

    class FakeThread:
        def __init__(self, *args, **kwargs):
            started.append((args, kwargs))

        def start(self):
            started.append("started")

    monkeypatch.setattr(agent_chat_claude_code.threading, "Thread", FakeThread)

    agent_chat_claude_code._tts_speak_bg("ios:abc123", "hello")

    assert started == []


def test_claude_code_remote_docs_are_platform_routed():
    doc = inspect.getdoc(agent_chat_claude_code._chat_claude_code_remote)

    assert "Android through ADB or iOS through Appium/WebDriverAgent" in doc
    assert "via ADB (USB or wireless)" not in doc
