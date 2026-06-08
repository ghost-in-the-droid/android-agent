import json
import sys

import scripts.ios_chrome_news_smoke as smoke
from gitd.bots.common.ios import IOSDeviceConfig


def test_ios_chrome_news_smoke_stops_on_failed_health_preflight(monkeypatch, tmp_path):
    health = {
        "platform": "ios",
        "connection": {"type": "appium-wda", "status": "wda_signing_failed"},
        "recommended_fix": "fix_wda_signing",
    }
    monkeypatch.setattr(
        sys,
        "argv",
        ["ios_chrome_news_smoke.py", "--device", "abc123", "--out-dir", str(tmp_path)],
    )
    monkeypatch.setattr(smoke, "_preflight_health", lambda device, bundle_id: health)
    monkeypatch.setattr(
        smoke,
        "read_news",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("read_news should not run")),
    )

    rc = smoke.main()

    assert rc == 1
    result = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    saved_health = json.loads((tmp_path / "health.json").read_text(encoding="utf-8"))
    assert result["stage"] == "health"
    assert result["health"]["recommended_fix"] == "fix_wda_signing"
    assert saved_health == health


def test_ios_chrome_news_smoke_preflight_uses_requested_browser_bundle(monkeypatch):
    calls = []

    class FakeIOSDevice:
        def __init__(self, device, bundle_id=None):
            calls.append(("device", device, bundle_id))
            self.mjpeg_url = "http://127.0.0.1:9100"
            self.mjpeg_settings = {}

    def fake_ios_device_health(device, ios_dev):
        calls.append(("health", device, ios_dev))
        return {"platform": "ios", "connection": {"status": "available"}}

    monkeypatch.setattr(smoke, "IOSDevice", FakeIOSDevice)
    monkeypatch.setattr(smoke, "ios_device_health", fake_ios_device_health)

    health = smoke._preflight_health("ios:abc123", "com.google.chrome.ios")

    assert health["connection"]["status"] == "available"
    assert calls[0] == ("device", "ios:abc123", "com.google.chrome.ios")
    assert calls[1][0:2] == ("health", "ios:abc123")
    assert isinstance(calls[1][2], FakeIOSDevice)


def test_ios_chrome_news_smoke_can_skip_health_preflight(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(
        sys,
        "argv",
        ["ios_chrome_news_smoke.py", "--device", "ios:abc123", "--out-dir", str(tmp_path), "--skip-health"],
    )
    monkeypatch.setattr(smoke, "_preflight_health", lambda device, bundle_id: calls.append(("health", device, bundle_id)))
    monkeypatch.setattr(
        smoke,
        "read_news",
        lambda device, url, **kwargs: {
            "ok": True,
            "device": device,
            "url": url,
            "headlines": [{"title": "One"}],
            "kwargs": kwargs,
        },
    )

    rc = smoke.main()

    assert rc == 0
    assert calls == []
    result = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    assert result["device"] == "ios:abc123"
    assert result["headlines"] == [{"title": "One"}]


def test_ios_chrome_news_smoke_can_apply_recommended_health_fix(monkeypatch, tmp_path):
    calls = []
    health_results = iter(
        [
            {
                "platform": "ios",
                "connection": {"type": "appium-wda", "status": "appium_down"},
                "recommended_fix": "start_appium",
            },
            {
                "platform": "ios",
                "connection": {"type": "appium-wda", "status": "available"},
                "recommended_fix": "",
            },
        ]
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["ios_chrome_news_smoke.py", "--device", "ios:abc123", "--out-dir", str(tmp_path), "--fix-health"],
    )
    monkeypatch.setattr(smoke, "_preflight_health", lambda device, bundle_id: next(health_results))
    monkeypatch.setattr(
        smoke,
        "fix_device_health",
        lambda device, issue: calls.append(("fix", device, issue))
        or {"ok": True, "platform": "ios", "issue": issue, "pid": 2468},
    )
    monkeypatch.setattr(
        smoke,
        "read_news",
        lambda device, url, **kwargs: {
            "ok": True,
            "device": device,
            "url": url,
            "headlines": [{"title": "One"}],
            "articles": [],
        },
    )

    rc = smoke.main()

    assert rc == 0
    result = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    health_fix = json.loads((tmp_path / "health_fix.json").read_text(encoding="utf-8"))
    saved_health = json.loads((tmp_path / "health.json").read_text(encoding="utf-8"))
    assert calls == [("fix", "ios:abc123", "start_appium")]
    assert saved_health["connection"]["status"] == "available"
    assert health_fix["issue"] == "start_appium"
    assert result["health_fix"]["pid"] == 2468
    assert result["headlines"] == [{"title": "One"}]


def test_ios_chrome_news_smoke_uses_first_discovered_device(monkeypatch, tmp_path):
    monkeypatch.delenv("IOS_DEVICE_UDID", raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        ["ios_chrome_news_smoke.py", "--out-dir", str(tmp_path), "--skip-health"],
    )
    monkeypatch.setattr(smoke, "known_ios_udids", lambda **_kwargs: ["00008110-0012345678901234"])
    monkeypatch.setattr(
        smoke,
        "read_news",
        lambda device, url, **kwargs: {
            "ok": True,
            "device": device,
            "url": url,
            "headlines": [{"title": "One"}],
            "kwargs": kwargs,
        },
    )

    rc = smoke.main()

    assert rc == 0
    result = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    assert result["device"] == "ios:00008110-0012345678901234"


def test_ios_chrome_news_smoke_dry_run_prints_discovery_without_session(monkeypatch, capsys):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ios_chrome_news_smoke.py",
            "--dry-run",
            "--device",
            "SIM-123",
            "--bundle-id",
            "com.google.chrome.ios",
        ],
    )
    monkeypatch.setattr(smoke, "configured_ios_udids", lambda: ["PHONE-123"])
    monkeypatch.setattr(
        smoke,
        "discover_host_ios_devices",
        lambda include_simulators=True: [
            {
                "udid": "SIM-123",
                "name": "iPhone 16",
                "platform_version": "18.5",
                "source": "simulator",
                "state": "Booted",
            }
        ],
    )
    monkeypatch.setattr(
        smoke,
        "ios_config_for_udid",
        lambda udid: IOSDeviceConfig(
            udid=udid,
            appium_url="http://127.0.0.1:4723",
            bundle_id="com.apple.mobilesafari" if udid == "SIM-123" else "com.google.chrome.ios",
            mjpeg_server_port=9107,
        ),
    )
    monkeypatch.setattr(
        smoke,
        "_preflight_health",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("health should not run")),
    )
    monkeypatch.setattr(
        smoke,
        "read_news",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("read_news should not run")),
    )

    rc = smoke.main()

    assert rc == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["selected_device"] == "ios:SIM-123"
    assert plan["requested_bundle_id"] == "com.google.chrome.ios"
    assert [item["device"] for item in plan["devices"]] == ["ios:SIM-123", "ios:PHONE-123"]
    selected = plan["devices"][0]
    assert selected["selected"] is True
    assert selected["source"] == "simulator"
    assert selected["host_state"] == "Booted"
    assert selected["bundle_id"] == "com.apple.mobilesafari"
    assert selected["mjpeg_server_port"] == 9107


def test_ios_chrome_news_smoke_list_devices_respects_no_simulators(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["ios_chrome_news_smoke.py", "--list-devices", "--no-simulators"])
    monkeypatch.setattr(smoke, "configured_ios_udids", lambda: [])
    monkeypatch.setattr(
        smoke,
        "known_ios_udids",
        lambda include_host=True, include_simulators=True: ["REAL-123"] if not include_simulators else ["SIM-123"],
    )
    monkeypatch.setattr(
        smoke,
        "discover_host_ios_devices",
        lambda include_simulators=True: [
            {
                "udid": "REAL-123",
                "name": "Dan's iPhone",
                "platform_version": "18.5",
                "source": "host",
                "state": "connected",
            },
            *(
                [
                    {
                        "udid": "SIM-123",
                        "name": "iPhone 16",
                        "platform_version": "18.5",
                        "source": "simulator",
                        "state": "Booted",
                    }
                ]
                if include_simulators
                else []
            ),
        ],
    )
    monkeypatch.setattr(
        smoke,
        "ios_config_for_udid",
        lambda udid: IOSDeviceConfig(udid=udid, bundle_id="com.google.chrome.ios"),
    )

    rc = smoke.main()

    assert rc == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["include_simulators"] is False
    assert plan["selected_device"] == "ios:REAL-123"
    assert [item["device"] for item in plan["devices"]] == ["ios:REAL-123"]
