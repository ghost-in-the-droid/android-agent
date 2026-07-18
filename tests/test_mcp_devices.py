from gitd import mcp_server


class FakeAndroidDevice:
    def __init__(self, serial):
        self.serial = serial

    def adb(self, *args, **kwargs):
        assert self.serial == "emulator-5554"
        assert args == ("shell", "getprop", "ro.product.model")
        assert kwargs == {"timeout": 3}
        return "Pixel 8\n"


def test_mcp_list_devices_includes_ios_probe_status(monkeypatch):
    def fake_ios_devices(deep_probe=False):
        assert deep_probe is False
        return [
            {
                "serial": "ios:abc123",
                "model": "Casey's iPhone",
                "platform": "ios",
                "source": "host",
                "host_state": "connected",
                "status": "appium_down",
                "status_message": "Start Appium on http://127.0.0.1:4723.",
                "appium_url": "http://127.0.0.1:4723",
            }
        ]

    monkeypatch.setattr(mcp_server, "Device", FakeAndroidDevice)
    monkeypatch.setattr(mcp_server, "list_connected_device_refs", lambda: ["emulator-5554", "ios:abc123"])
    monkeypatch.setattr(mcp_server, "list_configured_ios_devices", fake_ios_devices)

    result = mcp_server.list_devices()

    assert "emulator-5554 (Pixel 8)" in result
    assert "ios:abc123" in result
    assert "Casey's iPhone" in result
    assert "status=appium_down" in result
    assert "host=host/connected" in result
    assert "appium=http://127.0.0.1:4723" in result
    assert "hint=Start Appium on http://127.0.0.1:4723." in result


def test_mcp_list_devices_falls_back_when_ios_details_fail(monkeypatch):
    monkeypatch.setattr(mcp_server, "list_connected_device_refs", lambda: ["ios:abc123"])
    monkeypatch.setattr(
        mcp_server,
        "list_configured_ios_devices",
        lambda deep_probe=False: (_ for _ in ()).throw(RuntimeError("xctrace failed")),
    )

    assert mcp_server.list_devices() == "ios:abc123 (iOS via Appium/WDA)"
