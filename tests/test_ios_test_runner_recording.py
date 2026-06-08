import sys
from pathlib import Path

from gitd.routers import tests as test_runner


class FakeProc:
    def __init__(self):
        self.terminated = False
        self.killed = False

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.killed = True


def test_ios_screen_recording_uses_wda_mjpeg_and_ffmpeg(tmp_path, monkeypatch):
    calls = []
    proc = FakeProc()

    class FakeIOSDevice:
        mjpeg_url = "http://127.0.0.1:9100"

    monkeypatch.setattr(test_runner, "_TR_RECORDINGS_DIR", tmp_path)
    monkeypatch.setattr(test_runner, "get_device", lambda serial: FakeIOSDevice())

    def fake_popen(cmd, stdout=None, stderr=None):
        calls.append(cmd)
        return proc

    monkeypatch.setattr(test_runner.subprocess, "Popen", fake_popen)

    returned_proc, local_path = test_runner._sr_start("ios:abc123", "ios_abc123_smoke.mp4")

    assert returned_proc is proc
    assert local_path == str(tmp_path / "ios_abc123_smoke.mp4")
    assert calls == [
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "mjpeg",
            "-i",
            "http://127.0.0.1:9100",
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(tmp_path / "ios_abc123_smoke.mp4"),
        ]
    ]


def test_ios_screen_recording_stop_returns_local_file(tmp_path):
    proc = FakeProc()
    local_path = tmp_path / "ios_recording.mp4"
    local_path.write_bytes(b"mp4")

    result = test_runner._sr_stop_and_pull("ios:abc123", proc, str(local_path), local_path.name)

    assert proc.terminated is True
    assert result == local_path


def test_recording_names_are_filesystem_safe():
    assert test_runner._safe_recording_name("ios:abc123/test name") == "ios_abc123_test_name"


def test_test_runner_uses_current_interpreter_for_pytest():
    cmd = test_runner._pytest_cmd("tests/test_ios_device.py::test_factory_routes_ios_prefix", retry=True)

    assert cmd[:3] == [sys.executable, "-u", "-m"]
    assert cmd[3:7] == ["pytest", "-v", "--tb=short", "-s"]
    assert "--reruns" in cmd
    assert cmd[-1] == "tests/test_ios_device.py::test_factory_routes_ios_prefix"


def test_test_runner_sets_ios_live_test_env(monkeypatch):
    monkeypatch.delenv("IOS_DEVICE_UDID", raising=False)

    env = test_runner._pytest_env("ios:abc123")

    assert env["DEVICE"] == "ios:abc123"
    assert env["IOS_DEVICE_UDID"] == "abc123"
    assert env["PYTHONUNBUFFERED"] == "1"


def test_test_runner_keeps_android_env_unchanged(monkeypatch):
    monkeypatch.delenv("IOS_DEVICE_UDID", raising=False)

    env = test_runner._pytest_env("emulator-5554")

    assert env["DEVICE"] == "emulator-5554"
    assert "IOS_DEVICE_UDID" not in env
