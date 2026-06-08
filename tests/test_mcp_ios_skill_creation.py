import json

import yaml

from gitd import mcp_server


def test_mcp_create_skill_writes_ios_metadata_and_elements(tmp_path, monkeypatch):
    fake_mcp_file = tmp_path / "gitd" / "mcp_server.py"
    fake_mcp_file.parent.mkdir()
    fake_mcp_file.write_text("")
    monkeypatch.setattr(mcp_server, "__file__", str(fake_mcp_file))

    steps = [{"action": "launch", "package": "com.google.chrome.ios"}]
    elements_ios = {"address_bar": {"text": "Search or type web address"}}

    result = mcp_server.create_skill(
        name="ios_browser_demo",
        app_package="com.google.chrome.ios",
        steps=json.dumps(steps),
        platforms="ios",
        elements_ios=json.dumps(elements_ios),
    )

    skill_dir = fake_mcp_file.parent / "skills" / "ios_browser_demo"
    meta = yaml.safe_load((skill_dir / "skill.yaml").read_text())

    assert "for ios" in result
    assert meta["platforms"] == ["ios"]
    assert meta["app_package"] == ""
    assert meta["android_package"] == ""
    assert meta["ios_bundle_id"] == "com.google.chrome.ios"
    assert json.loads((skill_dir / "workflows" / "recorded.json").read_text()) == steps
    assert yaml.safe_load((skill_dir / "elements_ios.yaml").read_text()) == elements_ios


def test_mcp_create_skill_preserves_legacy_android_default(tmp_path, monkeypatch):
    fake_mcp_file = tmp_path / "gitd" / "mcp_server.py"
    fake_mcp_file.parent.mkdir()
    fake_mcp_file.write_text("")
    monkeypatch.setattr(mcp_server, "__file__", str(fake_mcp_file))

    result = mcp_server.create_skill(
        name="android_demo",
        app_package="com.example.android",
        steps=json.dumps([{"action": "tap", "x": 1, "y": 2}]),
    )

    meta = yaml.safe_load((fake_mcp_file.parent / "skills" / "android_demo" / "skill.yaml").read_text())

    assert "for android" in result
    assert meta["platforms"] == ["android"]
    assert meta["app_package"] == "com.example.android"
    assert meta["android_package"] == "com.example.android"
    assert meta["ios_bundle_id"] == ""
