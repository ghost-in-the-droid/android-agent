from gitd.routers.streaming import phone_stream


def test_ios_stream_headers_expose_effective_wda_mjpeg_mode():
    response = phone_stream(device="ios:abc123", fps=99, mode="mjpeg")

    assert response.headers["x-phone-platform"] == "ios"
    assert response.headers["x-phone-stream-mode"] == "wda-mjpeg"


def test_ios_stream_headers_expose_screenshot_polling_fallback_mode():
    response = phone_stream(device="ios:abc123", fps=5, mode="screencap")

    assert response.headers["x-phone-platform"] == "ios"
    assert response.headers["x-phone-stream-mode"] == "screenshot-polling"


def test_android_stream_headers_expose_effective_mode():
    response = phone_stream(device="emulator-5554", fps=5, mode="h264")

    assert response.headers["x-phone-platform"] == "android"
    assert response.headers["x-phone-stream-mode"] == "h264"
