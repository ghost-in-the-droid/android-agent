"""Core shared actions — tap, swipe, type, wait, launch, screenshot, dismiss popup."""
from __future__ import annotations

from pathlib import Path
import time

from gitd.skills.base import Action, ActionResult, Element, _device_is_ios


class TapElement(Action):
    """Tap a named UI element."""
    name = 'tap_element'
    description = 'Find and tap a UI element by name'

    def __init__(self, device, elements, *, element_name: str, **kwargs):
        super().__init__(device, elements)
        self.element_name = element_name

    def execute(self) -> ActionResult:
        pos = self.find_element(self.element_name)
        if not pos:
            return ActionResult(success=False, error=f'Element "{self.element_name}" not found')
        self.device.tap(*pos)
        return ActionResult(success=True, data={'element': self.element_name, 'pos': pos})


class SwipeDirection(Action):
    """Swipe in a direction (up/down/left/right) from screen center."""
    name = 'swipe_direction'
    description = 'Swipe up/down/left/right'

    def __init__(self, device, elements, *, direction: str = 'up', distance: int = 500, **kwargs):
        super().__init__(device, elements)
        self.direction = direction
        self.distance = distance

    def execute(self) -> ActionResult:
        cx, cy = 540, 1200  # default center for 1080x2400
        if _device_is_ios(self.device) and hasattr(self.device, 'get_screen_size'):
            width, height = self.device.get_screen_size()
            if width and height:
                cx, cy = width // 2, height // 2
        d = self.distance
        dirs = {
            'up':    (cx, cy, cx, cy - d),
            'down':  (cx, cy, cx, cy + d),
            'left':  (cx, cy, cx - d, cy),
            'right': (cx, cy, cx + d, cy),
        }
        coords = dirs.get(self.direction)
        if not coords:
            return ActionResult(success=False, error=f'Unknown direction: {self.direction}')
        self.device.swipe(*coords)
        return ActionResult(success=True, data={'direction': self.direction})


class TypeText(Action):
    """Type text into the currently focused input field."""
    name = 'type_text'
    description = 'Type text into the focused field'

    def __init__(self, device, elements, *, text: str, **kwargs):
        super().__init__(device, elements)
        self.text = text

    def execute(self) -> ActionResult:
        if _device_is_ios(self.device) and hasattr(self.device, 'type_text'):
            self.device.type_text(self.text)
        elif all(ord(c) < 128 for c in self.text):
            from gitd.bots.common.adb import input_text_arg

            self.device.adb("shell", "input", "text", input_text_arg(self.text))
        else:
            self.device.type_unicode(self.text)
        time.sleep(0.3)
        return ActionResult(success=True, data={'text': self.text})


class WaitForElement(Action):
    """Wait for a UI element to appear within timeout."""
    name = 'wait_for_element'
    description = 'Poll UI tree until element appears'

    def __init__(self, device, elements, *, element_name: str, timeout: float = 10, **kwargs):
        super().__init__(device, elements)
        self.element_name = element_name
        self.timeout = timeout
    max_retries = 1  # no retries — we handle timeout internally

    def execute(self) -> ActionResult:
        t0 = time.time()
        while time.time() - t0 < self.timeout:
            pos = self.find_element(self.element_name)
            if pos:
                return ActionResult(success=True, data={'element': self.element_name, 'pos': pos,
                                                        'wait_s': round(time.time() - t0, 1)})
            time.sleep(1)
        return ActionResult(success=False,
                            error=f'Element "{self.element_name}" not found after {self.timeout}s')


class LaunchApp(Action):
    """Launch an app by Android package name or iOS bundle id."""
    name = 'launch_app'
    description = 'Start an Android app or iOS bundle'

    def __init__(self, device, elements, *, package: str, activity: str | None = None, **kwargs):
        super().__init__(device, elements)
        self.package = package
        self.activity = activity

    def execute(self) -> ActionResult:
        if _device_is_ios(self.device) and hasattr(self.device, 'launch_app'):
            self.device.launch_app(self.package)
            time.sleep(2)
            return ActionResult(success=True, data={'bundle_id': self.package})
        if self.activity:
            self.device.adb("shell", "am", "start", "-n", f"{self.package}/{self.activity}")
        else:
            # Use monkey to launch the main activity
            self.device.adb("shell", "monkey", "-p", self.package,
                            "-c", "android.intent.category.LAUNCHER", "1")
        time.sleep(2)
        return ActionResult(success=True, data={'package': self.package})

    def postcondition(self) -> bool:
        if _device_is_ios(self.device) and hasattr(self.device, 'app_state'):
            try:
                return int(self.device.app_state(self.package)) == 4
            except Exception:
                return False
        # Verify app is in foreground
        output = self.device.adb("shell", "dumpsys", "window", timeout=5)
        return self.package in output


class TakeScreenshot(Action):
    """Take a screenshot and save to local file."""
    name = 'take_screenshot'
    description = 'Capture phone screen'

    def __init__(self, device, elements, *, output_path: str = '/tmp/screenshot.png', **kwargs):
        super().__init__(device, elements)
        self.output_path = output_path
    max_retries = 1

    def execute(self) -> ActionResult:
        if _device_is_ios(self.device) and hasattr(self.device, 'take_screenshot'):
            path = Path(self.output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(self.device.take_screenshot())
            return ActionResult(success=True, data={'path': self.output_path})

        import subprocess
        self.device.adb("shell", "screencap", "-p", "/sdcard/screenshot.png")
        subprocess.run(["adb", "-s", self.device.serial, "pull",
                        "/sdcard/screenshot.png", self.output_path],
                       capture_output=True, timeout=10)
        return ActionResult(success=True, data={'path': self.output_path})


class DismissPopup(Action):
    """Try to dismiss any visible popup/dialog."""
    name = 'dismiss_popup'
    description = 'Detect and dismiss popups using known patterns'

    def execute(self) -> ActionResult:
        xml = self.device.dump_xml()
        dismissed = self.device.dismiss_popups(xml)
        return ActionResult(success=True, data={'dismissed': dismissed})


class PressBack(Action):
    """Press the platform back/navigation control."""
    name = 'press_back'
    description = 'Press back'
    max_retries = 1

    def execute(self) -> ActionResult:
        self.device.back()
        return ActionResult(success=True)


class PressHome(Action):
    """Press the platform home button."""
    name = 'press_home'
    description = 'Press home'
    max_retries = 1

    def execute(self) -> ActionResult:
        if _device_is_ios(self.device) and hasattr(self.device, 'press_key'):
            self.device.press_key('HOME')
        else:
            self.device.adb("shell", "input", "keyevent", "KEYCODE_HOME")
        time.sleep(0.5)
        return ActionResult(success=True)
