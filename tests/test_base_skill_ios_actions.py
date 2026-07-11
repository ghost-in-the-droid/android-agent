from pathlib import Path

from gitd.skills._base.actions.core import LaunchApp, PressHome, SwipeDirection, TakeScreenshot, TypeText


class FakeIOSDevice:
    serial = "ios:abc123"

    def __init__(self):
        self.calls = []

    def adb(self, *args, **kwargs):
        raise AssertionError(f"iOS base action should not call adb: {args}")

    def type_text(self, text):
        self.calls.append(("type_text", text))

    def launch_app(self, bundle_id):
        self.calls.append(("launch_app", bundle_id))

    def app_state(self, bundle_id):
        self.calls.append(("app_state", bundle_id))
        return 4

    def press_key(self, key):
        self.calls.append(("press_key", key))

    def get_screen_size(self):
        self.calls.append(("get_screen_size",))
        return (393, 852)

    def swipe(self, x1, y1, x2, y2):
        self.calls.append(("swipe", x1, y1, x2, y2))

    def take_screenshot(self):
        self.calls.append(("take_screenshot",))
        return b"ios-png"


def test_base_type_text_uses_ios_text_entry(monkeypatch):
    monkeypatch.setattr("gitd.skills._base.actions.core.time.sleep", lambda *_args, **_kwargs: None)
    dev = FakeIOSDevice()

    result = TypeText(dev, {}, text="hello iOS").execute()

    assert result.success is True
    assert result.data == {"text": "hello iOS"}
    assert dev.calls == [("type_text", "hello iOS")]


def test_base_launch_app_uses_ios_bundle_and_query_state(monkeypatch):
    monkeypatch.setattr("gitd.skills._base.actions.core.time.sleep", lambda *_args, **_kwargs: None)
    dev = FakeIOSDevice()
    action = LaunchApp(dev, {}, package="com.google.chrome.ios")

    result = action.execute()

    assert result.success is True
    assert result.data == {"bundle_id": "com.google.chrome.ios"}
    assert action.postcondition() is True
    assert dev.calls == [
        ("launch_app", "com.google.chrome.ios"),
        ("app_state", "com.google.chrome.ios"),
    ]


def test_base_press_home_uses_ios_home_button(monkeypatch):
    monkeypatch.setattr("gitd.skills._base.actions.core.time.sleep", lambda *_args, **_kwargs: None)
    dev = FakeIOSDevice()

    result = PressHome(dev, {}).execute()

    assert result.success is True
    assert dev.calls == [("press_key", "HOME")]


def test_base_swipe_direction_uses_ios_screen_size():
    dev = FakeIOSDevice()

    result = SwipeDirection(dev, {}, direction="up", distance=100).execute()

    assert result.success is True
    assert dev.calls == [
        ("get_screen_size",),
        ("swipe", 196, 426, 196, 326),
    ]


def test_base_take_screenshot_uses_ios_screenshot_bytes(tmp_path):
    dev = FakeIOSDevice()
    output = tmp_path / "shot.png"

    result = TakeScreenshot(dev, {}, output_path=str(output)).execute()

    assert result.success is True
    assert result.data == {"path": str(output)}
    assert Path(output).read_bytes() == b"ios-png"
    assert dev.calls == [("take_screenshot",)]
