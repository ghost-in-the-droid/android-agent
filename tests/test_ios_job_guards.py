from fastapi.testclient import TestClient
from sqlalchemy import text

from gitd.app import app
from gitd.models.base import SessionLocal
from gitd.routers.scheduler import _scheduler_platform_error
from gitd.services.db_helpers import create_scheduled_job
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


def test_scheduler_create_rejects_ios_android_only_job_before_enqueue():
    client = TestClient(app)

    response = client.post(
        "/api/schedules",
        json={
            "name": "iOS post should fail",
            "job_type": "post",
            "phone_serial": "ios:abc123",
            "schedule_type": "interval",
            "interval_minutes": 60,
            "config_json": {"action": "draft"},
        },
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["error"] == "unsupported_platform"
    assert detail["platform"] == "ios"
    assert detail["job_type"] == "post"
    assert "Android-only" in detail["message"]


def test_scheduler_allows_ios_supported_skill_job():
    assert (
        _scheduler_platform_error(
            {
                "job_type": "skill_workflow",
                "phone_serial": "ios:abc123",
                "config_json": {"skill": "tiktok_ios", "workflow": "profile_smoke"},
            }
        )
        is None
    )

    err = _scheduler_platform_error(
        {
            "job_type": "skill_workflow",
            "phone_serial": "ios:abc123",
            "config_json": {"skill": "tiktok", "workflow": "upload_video"},
        }
    )
    assert err["error"] == "unsupported_platform"
    assert err["skill"] == "tiktok"
    assert "does not support ios" in err["message"]


def test_scheduler_update_rejects_moving_android_only_job_to_ios():
    client = TestClient(app)
    sid = None
    try:
        created = client.post(
            "/api/schedules",
            json={
                "name": "android post schedule",
                "job_type": "post",
                "phone_serial": "emulator-5554",
                "schedule_type": "interval",
                "interval_minutes": 60,
                "config_json": {"action": "draft"},
            },
        )
        assert created.status_code == 200
        sid = created.json()["id"]

        response = client.put(f"/api/schedules/{sid}", json={"phone_serial": "ios:abc123"})

        assert response.status_code == 400
        detail = response.json()["detail"]
        assert detail["error"] == "unsupported_platform"
        assert detail["platform"] == "ios"
        assert detail["job_type"] == "post"
    finally:
        if sid:
            client.delete(f"/api/schedules/{sid}")


def test_scheduler_run_now_rejects_legacy_ios_android_only_schedule():
    client = TestClient(app)
    db = SessionLocal()
    sid = None
    try:
        sid = create_scheduled_job(
            db,
            name="legacy ios post",
            job_type="post",
            phone_serial="ios:abc123",
            schedule_type="interval",
            interval_minutes=60,
            config_json={"action": "draft"},
            is_enabled=1,
        )

        response = client.post(f"/api/schedules/{sid}/run-now")

        assert response.status_code == 400
        detail = response.json()["detail"]
        assert detail["error"] == "unsupported_platform"
        assert detail["platform"] == "ios"
        assert detail["job_type"] == "post"
    finally:
        if sid:
            db.execute(text("DELETE FROM scheduled_jobs WHERE id = :sid"), {"sid": sid})
            db.execute(text("DELETE FROM job_queue WHERE scheduled_job_id = :sid"), {"sid": sid})
            db.commit()
        db.close()
