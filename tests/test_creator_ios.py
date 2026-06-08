import json

import yaml

from gitd.routers import creator
from gitd.routers import skills as skills_router


def test_creator_prompt_uses_ios_appium_language(monkeypatch):
    monkeypatch.setattr(
        "gitd.services.device_context.get_phone_state",
        lambda _device: {"currentApp": "Chrome", "bundleId": "com.google.chrome.ios"},
    )

    prompt = creator._build_creator_system_prompt(
        {
            "backend": "openrouter",
            "context": {
                "device": "ios:abc123",
                "elements": [
                    {
                        "idx": 0,
                        "text": "Search or type URL",
                        "class": "XCUIElementTypeTextField",
                        "bounds": {"x1": 10, "y1": 20, "x2": 300, "y2": 60},
                    }
                ],
            },
        }
    )

    assert "controls iOS devices through Appium XCUITest and WebDriverAgent" in prompt
    assert "launch(bundle_id)" in prompt
    assert 'platforms: ["ios"]' in prompt
    assert "Do NOT use ADB shell" in prompt
    assert "Current app: Chrome (com.google.chrome.ios)" in prompt
    assert "XCUIElementTypeTextField" in prompt


def test_creator_prompt_keeps_android_adb_language(monkeypatch):
    monkeypatch.setattr(
        "gitd.services.device_context.get_phone_state",
        lambda _device: {"currentApp": "TikTok", "packageName": "com.zhiliaoapp.musically"},
    )

    prompt = creator._build_creator_system_prompt(
        {"backend": "openrouter", "context": {"device": "emulator-5554"}}
    )

    assert "controls Android devices via ADB" in prompt
    assert "launch(package)" in prompt
    assert "Appium XCUITest" not in prompt
    assert "Current app: TikTok (com.zhiliaoapp.musically)" in prompt


def test_create_from_recording_writes_ios_skill_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr(skills_router, "_SKILLS_DIR", tmp_path)

    result = skills_router.api_skills_create_from_recording(
        {
            "name": "ios_creator_demo",
            "steps": [{"action": "launch", "package": "com.google.chrome.ios"}],
            "platforms": ["ios"],
            "app_package": "",
            "android_package": "",
            "ios_bundle_id": "com.google.chrome.ios",
            "elements_ios": [{"text": "Search", "class": "XCUIElementTypeTextField"}],
        }
    )

    skill_dir = tmp_path / "ios_creator_demo"
    meta = yaml.safe_load((skill_dir / "skill.yaml").read_text())

    assert result["ok"] is True
    assert meta["platforms"] == ["ios"]
    assert meta["app_package"] == ""
    assert meta["android_package"] == ""
    assert meta["ios_bundle_id"] == "com.google.chrome.ios"
    assert json.loads((skill_dir / "workflows" / "recorded.json").read_text())[0]["package"] == "com.google.chrome.ios"
    assert yaml.safe_load((skill_dir / "elements_ios.yaml").read_text())[0]["text"] == "Search"


def test_create_from_recording_treats_ios_app_package_as_bundle_id(tmp_path, monkeypatch):
    monkeypatch.setattr(skills_router, "_SKILLS_DIR", tmp_path)

    result = skills_router.api_skills_create_from_recording(
        {
            "name": "ios_bundle_in_app_package",
            "steps": [{"action": "launch", "package": "com.google.chrome.ios"}],
            "platforms": ["ios"],
            "app_package": "com.google.chrome.ios",
        }
    )

    meta = yaml.safe_load((tmp_path / "ios_bundle_in_app_package" / "skill.yaml").read_text())

    assert result["ok"] is True
    assert meta["platforms"] == ["ios"]
    assert meta["app_package"] == ""
    assert meta["android_package"] == ""
    assert meta["ios_bundle_id"] == "com.google.chrome.ios"
