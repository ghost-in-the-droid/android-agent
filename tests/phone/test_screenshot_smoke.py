"""screenshot_smoke — TakeScreenshot writes a valid PNG at the device's screen size."""

import re
import struct

from gitd.skills._base.actions.core import LaunchApp, TakeScreenshot

from .helpers import screen_texts, wait_until

SETTINGS = "com.android.settings"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def test_screenshot_is_valid_png_at_screen_size(phone, tmp_path):
    phone.adb("shell", "am", "force-stop", SETTINGS)
    assert LaunchApp(phone, None, package=SETTINGS).run(), "Settings did not come to the foreground"
    assert wait_until(lambda: "Search settings" in screen_texts(phone)), "Settings home page never rendered"

    out = tmp_path / "shot.png"
    result = TakeScreenshot(phone, None, output_path=str(out)).run()
    assert result, f"take_screenshot failed: {result.error}"
    assert out.is_file() and out.stat().st_size > 10_000, f"no usable screenshot written to {out}"

    data = out.read_bytes()
    assert data[:8] == PNG_SIGNATURE, f"not a PNG (header {data[:8]!r})"
    # IHDR is always the first chunk: width/height are big-endian u32 at bytes 16..24.
    width, height = struct.unpack(">II", data[16:24])
    w, h = map(int, re.search(r"(\d+)x(\d+)", phone.adb("shell", "wm", "size")).groups())
    assert (width, height) == (w, h), f"screenshot is {width}x{height}, screen is {w}x{h}"
