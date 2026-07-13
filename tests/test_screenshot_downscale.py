"""The MCP screenshot tool must return a downscaled JPEG, not a raw full-res PNG.

Raw PNG base64 overflows the MCP tool-result token cap on content-heavy screens
(feature #8 stopgap). This proves the tool routes through the compressed path and
that the payload is materially smaller than the raw capture.
"""

import base64
import io

from gitd import mcp_server
from gitd.services import device_context


def _big_png() -> bytes:
    """A phone-sized, detail-heavy PNG (worst case for the token cap)."""
    from PIL import Image

    # deterministic high-frequency pattern → PNG doesn't compress it away
    img = Image.new("RGB", (1080, 2400))
    px = img.load()
    for y in range(0, 2400, 2):
        for x in range(0, 1080, 2):
            px[x, y] = ((x * 7) % 256, (y * 5) % 256, ((x + y) * 3) % 256)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_mcp_screenshot_returns_jpeg_not_raw_png(monkeypatch):
    raw = _big_png()
    monkeypatch.setattr(device_context, "_raw_screenshot_bytes", lambda d: raw)

    out_b64 = mcp_server.screenshot("emulator-5554")
    out_bytes = base64.b64decode(out_b64)

    # JPEG magic, not PNG
    assert out_bytes[:2] == b"\xff\xd8"
    assert not out_bytes.startswith(b"\x89PNG")


def test_mcp_screenshot_payload_is_materially_smaller(monkeypatch):
    raw = _big_png()
    monkeypatch.setattr(device_context, "_raw_screenshot_bytes", lambda d: raw)

    raw_b64_len = len(base64.b64encode(raw).decode())
    new_b64_len = len(mcp_server.screenshot("emulator-5554"))

    # the whole point: the compressed payload must be a large fraction smaller
    assert new_b64_len < raw_b64_len / 3, f"expected >3x cut, got {raw_b64_len} -> {new_b64_len}"


def test_mcp_screenshot_delegates_to_device_context(monkeypatch):
    called = {}

    def fake_screenshot(device):
        called["device"] = device
        return {"image": "ZmFrZQ==", "width": 10, "height": 20}

    monkeypatch.setattr(device_context, "screenshot", fake_screenshot)
    assert mcp_server.screenshot("ios:00008XXX-XXXX") == "ZmFrZQ=="
    assert called["device"] == "ios:00008XXX-XXXX"  # cross-platform: iOS routes the same way
