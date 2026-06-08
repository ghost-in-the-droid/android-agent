import json

from fastapi.testclient import TestClient

from gitd.app import app
from gitd.services.agent_tools import execute_tool, tools_for_device
from gitd.services.tool_platforms import supports_platform, tool_platform_info


class FakeProc:
    def __init__(self):
        self.terminated = False
        self.signals = []
        self.killed = False
        self.returncode = None

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = 0

    def send_signal(self, sig):
        self.signals.append(sig)
        self.returncode = 0

    def wait(self, timeout=None):
        self.returncode = 0
        return 0

    def kill(self):
        self.killed = True
        self.returncode = -9


def test_ios_phone_recording_uses_wda_mjpeg_and_ffmpeg(tmp_path, monkeypatch):
    from gitd.services import phone_recording

    calls = []
    proc = FakeProc()

    class FakeIOSDevice:
        mjpeg_url = "http://127.0.0.1:9100"

    monkeypatch.setattr(phone_recording, "RECORDINGS_DIR", tmp_path)
    monkeypatch.setattr(phone_recording, "get_device", lambda device: FakeIOSDevice())
    phone_recording._active.clear()

    def fake_popen(cmd, stdout=None, stderr=None):
        calls.append(cmd)
        return proc

    monkeypatch.setattr(phone_recording.subprocess, "Popen", fake_popen)

    started = phone_recording.start_recording("ios:abc123", filename="ios-smoke.mp4")
    assert started["ok"] is True
    assert started["platform"] == "ios"
    assert started["mode"] == "wda-mjpeg"
    assert started["filename"] == "ios-smoke.mp4"
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
            str(tmp_path / "ios-smoke.mp4"),
        ]
    ]

    (tmp_path / "ios-smoke.mp4").write_bytes(b"mp4")
    stopped = phone_recording.stop_recording("ios:abc123")

    assert proc.terminated is True
    assert stopped["ok"] is True
    assert stopped["saved"] is True
    assert stopped["url"] == "/api/phone/recording/ios-smoke.mp4"
    assert phone_recording.recording_status("ios:abc123")["running"] is False


def test_android_phone_recording_uses_adb_screenrecord_and_pull(tmp_path, monkeypatch):
    from gitd.services import phone_recording

    popen_calls = []
    run_calls = []
    proc = FakeProc()

    monkeypatch.setattr(phone_recording, "RECORDINGS_DIR", tmp_path)
    phone_recording._active.clear()

    def fake_popen(cmd, stdout=None, stderr=None):
        popen_calls.append(cmd)
        return proc

    def fake_run(cmd, timeout=None, check=False, capture_output=False):
        run_calls.append(cmd)
        if "pull" in cmd:
            (tmp_path / "android-smoke.mp4").write_bytes(b"mp4")

        class Result:
            returncode = 0

        return Result()

    monkeypatch.setattr(phone_recording.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(phone_recording.subprocess, "run", fake_run)

    started = phone_recording.start_recording("emulator-5554", filename="android-smoke.mp4")
    stopped = phone_recording.stop_recording("emulator-5554")

    assert started["platform"] == "android"
    assert started["mode"] == "adb-screenrecord"
    assert popen_calls[0][:5] == ["adb", "-s", "emulator-5554", "shell", "screenrecord"]
    assert proc.signals
    assert any("pull" in call for call in run_calls)
    assert stopped["ok"] is True
    assert stopped["url"] == "/api/phone/recording/android-smoke.mp4"


def test_recording_rest_routes_use_service(monkeypatch):
    calls = []

    monkeypatch.setattr(
        "gitd.services.phone_recording.start_recording",
        lambda device, filename="": calls.append(("start", device, filename))
        or {"ok": True, "device": device, "filename": filename, "running": True},
    )
    monkeypatch.setattr(
        "gitd.services.phone_recording.stop_recording",
        lambda device: calls.append(("stop", device))
        or {"ok": True, "device": device, "filename": "rec.mp4", "saved": True},
    )
    monkeypatch.setattr(
        "gitd.services.phone_recording.recording_status",
        lambda device: {"ok": True, "device": device, "running": False},
    )
    monkeypatch.setattr(
        "gitd.services.phone_recording.list_recordings",
        lambda: [{"name": "rec.mp4", "url": "/api/phone/recording/rec.mp4"}],
    )

    client = TestClient(app)

    started = client.post("/api/phone/recording/start", json={"device": "ios:abc123", "filename": "rec.mp4"})
    stopped = client.post("/api/phone/recording/stop", json={"device": "ios:abc123"})
    status = client.get("/api/phone/recording/status/ios:abc123")
    listed = client.get("/api/phone/recordings")

    assert started.status_code == 200
    assert stopped.status_code == 200
    assert status.json()["running"] is False
    assert listed.json()["recordings"][0]["name"] == "rec.mp4"
    assert calls == [("start", "ios:abc123", "rec.mp4"), ("stop", "ios:abc123")]


def test_recording_agent_tools_and_platform_registry(monkeypatch):
    monkeypatch.setattr(
        "gitd.services.phone_recording.start_recording",
        lambda device, filename="": {"ok": True, "device": device, "platform": "ios", "filename": filename},
    )
    monkeypatch.setattr(
        "gitd.services.phone_recording.recording_status",
        lambda device: {"ok": True, "device": device, "platform": "ios", "running": True},
    )

    started = json.loads(
        execute_tool("start_screen_recording", {"device": "ios:abc123", "filename": "agent-rec.mp4"})
    )
    status = json.loads(execute_tool("screen_recording_status", {"device": "ios:abc123"}))
    ios_tools = {tool["name"] for tool in tools_for_device("ios:abc123")}

    assert started["filename"] == "agent-rec.mp4"
    assert status["running"] is True
    assert "start_screen_recording" in ios_tools
    assert "stop_screen_recording" in ios_tools
    assert "screen_recording_status" in ios_tools
    assert supports_platform("start_screen_recording", "ios") is True
    assert tool_platform_info("start_screen_recording").support == "cross_platform"
