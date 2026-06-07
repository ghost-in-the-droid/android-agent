from fastapi.testclient import TestClient

from gitd.app import app
from gitd.services.job_engine import _job_platform_preflight


def test_tiktok_scheduler_jobs_are_guarded_on_ios():
    assert _job_platform_preflight("ios:abc123", "post") == (
        "post jobs are Android-only until the iOS TikTok workflow is ported"
    )
    assert _job_platform_preflight("ios:abc123", "crawl") == (
        "crawl jobs are Android-only until the iOS TikTok workflow is ported"
    )
    assert _job_platform_preflight("ios:abc123", "app_explore") is None
    assert _job_platform_preflight("emulator-5554", "post") is None


def test_marketing_job_rejects_ios_device_before_enqueue(tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"fake")
    client = TestClient(app)

    response = client.post(
        "/api/marketing-jobs/enqueue",
        json={"video_path": str(video), "phone_serial": "ios:abc123", "caption": "draft"},
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["error"] == "unsupported_platform"
    assert detail["platform"] == "ios"
