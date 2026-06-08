import json
import sys

import scripts.ios_chrome_news_smoke as smoke


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
    monkeypatch.setattr(smoke, "device_health", lambda device: health)
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


def test_ios_chrome_news_smoke_can_skip_health_preflight(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(
        sys,
        "argv",
        ["ios_chrome_news_smoke.py", "--device", "ios:abc123", "--out-dir", str(tmp_path), "--skip-health"],
    )
    monkeypatch.setattr(smoke, "device_health", lambda device: calls.append(("health", device)))
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
