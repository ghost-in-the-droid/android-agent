"""
Phone-CI fixtures — hard-skill smoke tests against a real (emulated) Android device.

These run in .github/workflows/phone-smoke.yml against a fresh emulator, and
locally against any adb serial:

    PHONE_CI_DEVICE=emulator-5554 python -m pytest tests/phone/test_tap_smoke.py -v

Every test here uses only stock AOSP / google_apis apps (Settings, Contacts) so
the suite runs on a clean emulator image with no logins or extra APKs.

On failure, a screenshot, the UI tree, the focused window and a logcat tail are
written to $PHONE_CI_ARTIFACTS (default: ./phone-ci-artifacts/) — the workflow
uploads that directory as a build artifact.

See docs/CI_PHONE_SETUP.md for how to add a new skill test.
"""

import os
import re
import subprocess
import time
from pathlib import Path

import pytest

ARTIFACT_DIR = Path(os.environ.get("PHONE_CI_ARTIFACTS", "phone-ci-artifacts"))


@pytest.fixture(scope="session")
def phone():
    """Ghost Device bound to the CI emulator.

    Uses PHONE_CI_DEVICE (not DEVICE) so a developer's real-phone DEVICE env var
    never makes these tests drive their personal phone by accident.
    """
    from gitd.bots.common.adb import Device

    serial = os.environ.get("PHONE_CI_DEVICE", "")
    if not serial:
        pytest.skip("PHONE_CI_DEVICE not set — skipping phone-CI tests")
    dev = Device(serial)
    assert dev.adb("shell", "getprop", "sys.boot_completed") == "1", f"{serial} has not finished booting"
    # _base SwipeDirection swipes from a fixed (540, 1200) centre, so the
    # coordinates in these tests assume a 1080x2400 screen (AVD profile pixel_6).
    size = dev.adb("shell", "wm", "size")
    assert "1080x2400" in size, f"phone-CI expects a 1080x2400 screen, got {size!r}"
    return dev


@pytest.fixture(autouse=True)
def home_screen(request):
    """Start every test from an unlocked home screen with no app in front."""
    if "phone" not in request.fixturenames:
        yield
        return
    dev = request.getfixturevalue("phone")
    dev.adb("shell", "input", "keyevent", "KEYCODE_WAKEUP")
    dev.adb("shell", "wm", "dismiss-keyguard")
    dev.adb("shell", "input", "keyevent", "KEYCODE_HOME")
    time.sleep(1)
    yield


# ── Failure artifacts ────────────────────────────────────────────────────────


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    if rep.when == "call" and rep.failed and "phone" in item.funcargs:
        _capture_failure(item.funcargs["phone"], item.nodeid)


def _capture_failure(dev, nodeid: str):
    out = ARTIFACT_DIR / re.sub(r"[^\w.-]+", "_", nodeid)
    out.mkdir(parents=True, exist_ok=True)
    serial = ["adb", "-s", dev.serial]
    captures = {
        "screen.png": [*serial, "exec-out", "screencap", "-p"],
        "logcat.txt": [*serial, "logcat", "-d", "-t", "2000"],
        "window.txt": [*serial, "shell", "dumpsys", "window", "displays"],
    }
    for name, cmd in captures.items():
        try:
            (out / name).write_bytes(subprocess.run(cmd, capture_output=True, timeout=30).stdout)
        except Exception as e:  # best effort — never mask the real test failure
            (out / f"{name}.error").write_text(repr(e))
    try:
        (out / "ui.xml").write_text(dev.dump_xml())
    except Exception as e:
        (out / "ui.xml.error").write_text(repr(e))
