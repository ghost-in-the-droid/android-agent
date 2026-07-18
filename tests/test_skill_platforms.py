import json
import subprocess
import sys

from fastapi.testclient import TestClient

from gitd.app import app
from gitd.routers.skills import _load_all_skills
from gitd.services.agent_tools import execute_tool
from gitd.skills.platforms import (
    normalize_platforms,
    skill_platform_error,
    skill_platforms,
    skill_supports_device,
    skill_target_for_device,
)


def test_skill_platform_inference_and_targets():
    assert normalize_platforms(["iOS", "android", "ios", "unknown"]) == ["ios", "android"]
    assert skill_platforms({"app_package": "com.example.android"}) == ["android"]
    assert skill_platforms({"ios_bundle_id": "com.example.ios"}) == ["ios"]
    assert skill_platforms({"platforms": ["ios"], "app_package": "com.example.android"}) == ["ios"]
    assert skill_platforms({}) == ["android"]

    meta = {"app_package": "com.android.chrome", "ios_bundle_id": "com.google.chrome.ios", "platforms": ["android", "ios"]}
    assert skill_supports_device(meta, "emulator-5554") is True
    assert skill_supports_device(meta, "ios:abc123") is True
    assert skill_target_for_device(meta, "emulator-5554") == "com.android.chrome"
    assert skill_target_for_device(meta, "ios:abc123") == "com.google.chrome.ios"


def test_installed_skills_expose_platform_metadata():
    skills = _load_all_skills()

    assert skills["_base"]["platforms"] == ["android", "ios"]
    assert skills["_base"]["supports_android"] is True
    assert skills["_base"]["supports_ios"] is True

    assert skills["tiktok"]["platforms"] == ["android"]
    assert skills["tiktok"]["supports_ios"] is False
    assert skills["tiktok"]["android_package"] == "com.zhiliaoapp.musically"

    assert skills["safari"]["platforms"] == ["ios"]
    assert skills["safari"]["supports_ios"] is True
    assert skills["safari"]["ios_bundle_id"] == "com.google.chrome.ios"
    assert skills["safari"]["elements_ios_count"] >= 1

    assert skills["tiktok_ios"]["platforms"] == ["ios"]
    assert skills["tiktok_ios"]["supports_ios"] is True
    assert skills["tiktok_ios"]["supports_android"] is False
    assert skills["tiktok_ios"]["ios_bundle_id"] == "com.zhiliaoapp.musically"
    assert skills["tiktok_ios"]["elements_ios_count"] >= 1


def test_skill_platform_error_payload_is_stable():
    err = skill_platform_error("tiktok", {"platforms": ["android"]}, "ios:abc123")

    assert err["ok"] is False
    assert err["error"] == "unsupported_platform"
    assert err["skill"] == "tiktok"
    assert err["platform"] == "ios"
    assert err["supported_platforms"] == ["android"]


def test_rest_skills_include_device_support_flags_and_guard_runs():
    client = TestClient(app)

    listed = client.get("/api/skills", params={"device": "ios:abc123"})
    assert listed.status_code == 200
    by_dir = {item["dir"]: item for item in listed.json()}
    assert by_dir["_base"]["supported_on_device"] is True
    assert by_dir["tiktok"]["supported_on_device"] is False
    assert by_dir["safari"]["supported_on_device"] is True
    assert "Upload/posting is not implemented yet" in by_dir["tiktok_ios"]["platform_limitations"]["ios"][0]
    assert by_dir["tiktok_ios"]["default_params"]["workflows"]["search_smoke"]["query"] == "#fyp"

    tiktok_run = client.post(
        "/api/skills/tiktok/run",
        json={"device": "ios:abc123", "workflow": "upload_video", "params": {}},
    )
    assert tiktok_run.status_code == 400
    assert tiktok_run.json()["detail"]["error"] == "unsupported_platform"

    safari_run = client.post(
        "/api/skills/safari/run",
        json={"device": "emulator-5554", "workflow": "open_ghost_site", "params": {}},
    )
    assert safari_run.status_code == 400
    assert safari_run.json()["detail"]["error"] == "unsupported_platform"


def test_agent_skill_tools_filter_and_guard_by_device():
    payload = json.loads(execute_tool("list_skills", {"device": "ios:abc123", "supported_only": True}))
    by_name = {item["name"]: item for item in payload}
    names = set(by_name)

    assert "base" in names
    assert "safari" in names
    assert "tiktok_ios" in names
    assert "tiktok" not in names
    assert "Upload/posting is not implemented yet" in by_name["tiktok_ios"]["platform_limitations"]["ios"][0]
    assert by_name["tiktok_ios"]["default_params"]["workflows"]["search_smoke"]["max_lines"] == 80

    result = execute_tool("run_skill", {"device": "ios:abc123", "skill": "tiktok", "workflow": "upload_video"})
    assert result.startswith("ERROR: Skill 'tiktok' does not support ios")


def test_mcp_skill_listing_filters_and_exposes_ios_context():
    from gitd import mcp_server

    payload = json.loads(mcp_server.list_skills("ios:abc123", supported_only=True))
    by_name = {item["name"]: item for item in payload}

    assert "tiktok" not in by_name
    assert by_name["tiktok_ios"]["supported_on_device"] is True
    assert "Upload/posting is not implemented yet" in by_name["tiktok_ios"]["platform_limitations"]["ios"][0]
    assert by_name["tiktok_ios"]["default_params"]["workflows"]["search_smoke"]["query"] == "#fyp"


def test_skill_runner_rejects_unsupported_platform_before_device_access():
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "gitd.skills._run_skill",
            "--skill",
            "tiktok",
            "--workflow",
            "upload_video",
            "--device",
            "ios:abc123",
            "--params",
            "{}",
        ],
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 2
    assert "does not support ios" in result.stderr
