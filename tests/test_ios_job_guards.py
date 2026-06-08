import json
import sys
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from gitd.app import app
from gitd.models.base import SessionLocal
from gitd.routers import bot
from gitd.routers.scheduler import _scheduler_platform_error
from gitd.services.db_helpers import create_scheduled_job, enqueue_job
from gitd.services.job_engine import (
    _account_preflight,
    _build_scheduled_cmd,
    _job_platform_preflight,
    _skill_config_preflight,
)
from gitd.services.scheduler_service import _enqueue_due_schedule


def test_tiktok_scheduler_jobs_are_guarded_on_ios():
    assert _job_platform_preflight("ios:abc123", "post") == (
        "post jobs are Android-only until the iOS TikTok workflow is ported"
    )
    assert _job_platform_preflight("ios:abc123", "crawl") == (
        "crawl jobs are Android-only until the iOS TikTok workflow is ported"
    )
    assert _job_platform_preflight("ios:abc123", "app_explore") is None
    assert _job_platform_preflight("emulator-5554", "post") is None


def test_ios_tiktok_skill_account_preflight_passes_on_matching_account(monkeypatch):
    calls = []

    def fake_expected_account_matches(device: str, expected: str):
        calls.append((device, expected))
        return {"ok": True, "reason": None}

    monkeypatch.setattr(
        "gitd.services.account_health.expected_account_matches",
        fake_expected_account_matches,
    )

    err = _account_preflight(
        "ios:abc123",
        "skill_workflow",
        {"skill": "tiktok_ios", "workflow": "profile_smoke", "account": "@ghost"},
    )

    assert err is None
    assert calls == [("ios:abc123", "@ghost")]


def test_ios_tiktok_skill_account_preflight_blocks_observed_mismatch(monkeypatch):
    calls = []

    def fake_expected_account_matches(device: str, expected: str):
        calls.append((device, expected))
        return {
            "ok": False,
            "reason": "wrong active account: have @other, expected @ghost",
        }

    monkeypatch.setattr(
        "gitd.services.account_health.expected_account_matches",
        fake_expected_account_matches,
    )

    err = _account_preflight(
        "ios:abc123",
        "skill_workflow",
        {"skill": "tiktok_ios", "workflow": "profile_smoke", "account": "@ghost"},
    )

    assert err == "wrong active account: have @other, expected @ghost"
    assert calls == [("ios:abc123", "@ghost")]


def test_non_tiktok_skill_account_config_does_not_trigger_account_preflight(monkeypatch):
    def fail_expected_account_matches(device: str, expected: str):
        raise AssertionError("non-TikTok skills should not use TikTok account preflight")

    monkeypatch.setattr(
        "gitd.services.account_health.expected_account_matches",
        fail_expected_account_matches,
    )

    err = _account_preflight(
        "ios:abc123",
        "skill_workflow",
        {"skill": "safari", "workflow": "read_news", "account": "@ghost"},
    )

    assert err is None


def test_legacy_bot_queue_rejects_ios_tiktok_post_before_launch(monkeypatch):
    def fail_launch(job):
        raise AssertionError("_launch_job should not be called for unsupported iOS bot jobs")

    monkeypatch.setattr(bot, "_launch_job", fail_launch)
    with bot._queue_lock:
        queue_len = len(bot._queue)

    response = TestClient(app).post(
        "/api/bot/queue/add",
        json={"job_type": "post", "device": "ios:abc123", "video": "/tmp/clip.mp4"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["error"] == "unsupported_platform"
    assert body["platform"] == "ios"
    assert body["job_type"] == "post"
    assert body["device"] == "ios:abc123"
    assert body["supported_platforms"] == ["android"]
    with bot._queue_lock:
        assert len(bot._queue) == queue_len


def test_legacy_bot_build_cmd_rejects_ios_publish_draft():
    with pytest.raises(ValueError, match="Android-only.*iOS TikTok"):
        bot._build_cmd({"job_type": "publish_draft", "device": "ios:abc123", "grid_index": 0})


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


def test_marketing_job_enqueues_ios_profile_smoke_without_video():
    client = TestClient(app)
    db = SessionLocal()
    job_id = None
    try:
        response = client.post(
            "/api/marketing-jobs/enqueue",
            json={
                "phone_serial": "ios:abc123",
                "action": "profile_smoke",
                "account": "@ghost",
                "max_lines": 12,
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["action"] == "profile_smoke"
        assert body["job_type"] == "skill_workflow"
        assert body["skill"] == "tiktok_ios"
        assert body["workflow"] == "profile_smoke"
        job_id = int(body["job_id"].removeprefix("ghost-job-"))

        row = (
            db.execute(text("SELECT * FROM job_queue WHERE id = :id"), {"id": job_id})
            .mappings()
            .one()
        )
        config = json.loads(row["config_json"])
        assert row["phone_serial"] == "ios:abc123"
        assert row["job_type"] == "skill_workflow"
        assert row["trigger"] == "marketing_agent"
        assert row["max_duration_s"] == 300
        assert config == {
            "skill": "tiktok_ios",
            "workflow": "profile_smoke",
            "params": {"max_lines": 12},
            "source": "marketing_jobs",
            "action": "profile_smoke",
            "account": "@ghost",
        }
    finally:
        if job_id:
            db.execute(text("DELETE FROM job_queue WHERE id = :id"), {"id": job_id})
            db.commit()
        db.close()


def test_marketing_job_enqueues_ios_search_smoke_with_query():
    client = TestClient(app)
    db = SessionLocal()
    job_id = None
    try:
        response = client.post(
            "/api/marketing-jobs/enqueue",
            json={
                "phone_serial": "ios:abc123",
                "action": "search_smoke",
                "query": "#news",
                "account": "@ghost",
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["action"] == "search_smoke"
        assert body["job_type"] == "skill_workflow"
        assert body["skill"] == "tiktok_ios"
        assert body["workflow"] == "search_smoke"
        assert body["params"] == {"query": "#news"}
        job_id = int(body["job_id"].removeprefix("ghost-job-"))

        row = (
            db.execute(text("SELECT * FROM job_queue WHERE id = :id"), {"id": job_id})
            .mappings()
            .one()
        )
        config = json.loads(row["config_json"])
        assert row["phone_serial"] == "ios:abc123"
        assert row["job_type"] == "skill_workflow"
        assert row["trigger"] == "marketing_agent"
        assert row["max_duration_s"] == 300
        assert config == {
            "skill": "tiktok_ios",
            "workflow": "search_smoke",
            "params": {"query": "#news"},
            "source": "marketing_jobs",
            "action": "search_smoke",
            "account": "@ghost",
        }
    finally:
        if job_id:
            db.execute(text("DELETE FROM job_queue WHERE id = :id"), {"id": job_id})
            db.commit()
        db.close()


def test_marketing_job_enqueues_ios_open_app_smoke_without_params():
    client = TestClient(app)
    db = SessionLocal()
    job_id = None
    try:
        response = client.post(
            "/api/marketing-jobs/enqueue",
            json={
                "phone_serial": "ios:abc123",
                "action": "open_app_smoke",
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["action"] == "open_app_smoke"
        assert body["workflow"] == "open_app_smoke"
        assert body["params"] == {}
        job_id = int(body["job_id"].removeprefix("ghost-job-"))

        row = (
            db.execute(text("SELECT * FROM job_queue WHERE id = :id"), {"id": job_id})
            .mappings()
            .one()
        )
        assert json.loads(row["config_json"]) == {
            "skill": "tiktok_ios",
            "workflow": "open_app_smoke",
            "params": {},
            "source": "marketing_jobs",
            "action": "open_app_smoke",
        }
    finally:
        if job_id:
            db.execute(text("DELETE FROM job_queue WHERE id = :id"), {"id": job_id})
            db.commit()
        db.close()


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
    assert (
        _scheduler_platform_error(
            {
                "job_type": "skill_workflow",
                "phone_serial": "ios:abc123",
                "config_json": {"skill": "safari", "workflow": "read_news"},
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


def _arg_after(cmd: list[str], flag: str) -> str:
    return cmd[cmd.index(flag) + 1]


def test_ios_scheduled_skill_and_explorer_commands_use_current_interpreter():
    skill_cmd = _build_scheduled_cmd(
        "skill_workflow",
        {"skill": "safari", "workflow": "read_news", "params": {"url": "https://text.npr.org/"}},
        "ios:abc123",
    )
    action_cmd = _build_scheduled_cmd(
        "skill_action",
        {"skill": "safari", "action": "read_news", "params": {"max_headlines": 1}},
        "ios:abc123",
    )
    explorer_cmd = _build_scheduled_cmd(
        "app_explore",
        {"package": "com.google.chrome.ios", "max_depth": 1, "max_states": 3},
        "ios:abc123",
    )

    assert skill_cmd is not None
    assert action_cmd is not None
    assert explorer_cmd is not None
    for cmd in (skill_cmd, action_cmd, explorer_cmd):
        assert cmd[:2] == [sys.executable, "-u"]
        assert _arg_after(cmd, "--device") == "ios:abc123"

    assert skill_cmd.count("--skill") == 1
    assert _arg_after(skill_cmd, "--skill") == "safari"
    assert _arg_after(skill_cmd, "--workflow") == "read_news"
    assert "--action" not in skill_cmd
    assert json.loads(_arg_after(skill_cmd, "--params")) == {"url": "https://text.npr.org/"}

    assert action_cmd.count("--skill") == 1
    assert _arg_after(action_cmd, "--skill") == "safari"
    assert _arg_after(action_cmd, "--action") == "read_news"
    assert "--workflow" not in action_cmd
    assert json.loads(_arg_after(action_cmd, "--params")) == {"max_headlines": 1}

    assert _arg_after(explorer_cmd, "--package") == "com.google.chrome.ios"


def test_scheduled_skill_jobs_reject_malformed_config_before_subprocess():
    assert _skill_config_preflight("skill_workflow", {"skill": "safari"}) == (
        "skill_workflow jobs require config.workflow"
    )
    assert _skill_config_preflight("skill_action", {"skill": "safari"}) == (
        "skill_action jobs require config.action"
    )
    assert _skill_config_preflight("skill_workflow", {"workflow": "read_news"}) == (
        "skill_workflow jobs require config.skill"
    )
    assert _skill_config_preflight(
        "skill_workflow",
        {"skill": "safari", "workflow": "read_news", "params": []},
    ) == "skill_workflow jobs require config.params to be an object"
    assert _build_scheduled_cmd("skill_workflow", {"skill": "safari"}, "ios:abc123") is None


def test_scheduler_create_rejects_ios_skill_job_missing_workflow():
    client = TestClient(app)

    response = client.post(
        "/api/schedules",
        json={
            "name": "iOS malformed skill",
            "job_type": "skill_workflow",
            "phone_serial": "ios:abc123",
            "schedule_type": "interval",
            "interval_minutes": 60,
            "config_json": {"skill": "safari"},
        },
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail == {
        "error": "invalid_config",
        "platform": "ios",
        "job_type": "skill_workflow",
        "message": "skill_workflow jobs require config.workflow",
        "skill": "safari",
    }


def test_scheduler_allows_ios_app_explore_schedule_and_run_now():
    client = TestClient(app)
    db = SessionLocal()
    sid = None
    qid = None
    config = {"package": "com.google.chrome.ios", "max_depth": 1, "max_states": 3}
    try:
        created = client.post(
            "/api/schedules",
            json={
                "name": "iOS Chrome app explore",
                "job_type": "app_explore",
                "phone_serial": "ios:abc123",
                "schedule_type": "interval",
                "interval_minutes": 60,
                "config_json": config,
                "max_duration_s": 300,
            },
        )
        assert created.status_code == 200
        sid = created.json()["id"]

        run_now = client.post(f"/api/schedules/{sid}/run-now")
        assert run_now.status_code == 200
        qid = run_now.json()["queue_id"]

        row = (
            db.execute(text("SELECT * FROM job_queue WHERE id = :id"), {"id": qid})
            .mappings()
            .one()
        )
        assert row["scheduled_job_id"] == sid
        assert row["phone_serial"] == "ios:abc123"
        assert row["job_type"] == "app_explore"
        assert json.loads(row["config_json"]) == config

        queued = client.get("/api/scheduler/queue").json()
        item = next(item for item in queued if item["id"] == qid)
        assert item["platform"] == "ios"
        assert item["schedule_name"] == "iOS Chrome app explore"
    finally:
        if qid:
            db.execute(text("DELETE FROM job_queue WHERE id = :id"), {"id": qid})
        if sid:
            db.execute(text("DELETE FROM scheduled_jobs WHERE id = :id"), {"id": sid})
        db.commit()
        db.close()


def test_scheduler_restart_preserves_ios_schedule_timeout():
    client = TestClient(app)
    db = SessionLocal()
    sid = None
    run_id = None
    new_job_id = None
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    config = {"skill": "safari", "workflow": "read_news", "params": {"url": "https://text.npr.org/"}}
    try:
        sid = create_scheduled_job(
            db,
            name="ios news short timeout",
            job_type="skill_workflow",
            phone_serial="ios:abc123",
            schedule_type="interval",
            interval_minutes=60,
            config_json=config,
            max_duration_s=300,
            is_enabled=1,
        )
        db.execute(
            text(
                "INSERT INTO job_runs "
                "(scheduled_job_id, phone_serial, job_type, priority, config_json, status, "
                "enqueued_at, started_at, finished_at, duration_s, trigger) "
                "VALUES (:sid, :phone, :job_type, :priority, :config_json, :status, "
                ":enqueued_at, :started_at, :finished_at, :duration_s, :trigger)"
            ),
            {
                "sid": sid,
                "phone": "ios:abc123",
                "job_type": "skill_workflow",
                "priority": 1,
                "config_json": json.dumps(config),
                "status": "completed",
                "enqueued_at": now,
                "started_at": now,
                "finished_at": now,
                "duration_s": 15,
                "trigger": "manual",
            },
        )
        run_id = db.execute(text("SELECT last_insert_rowid()")).scalar()
        db.commit()

        response = client.post(f"/api/scheduler/runs/{run_id}/restart")
        assert response.status_code == 200
        body = response.json()
        assert body["platform"] == "ios"
        new_job_id = body["new_job_id"]

        row = (
            db.execute(text("SELECT * FROM job_queue WHERE id = :id"), {"id": new_job_id})
            .mappings()
            .one()
        )
        assert row["phone_serial"] == "ios:abc123"
        assert row["job_type"] == "skill_workflow"
        assert row["priority"] == 1
        assert row["max_duration_s"] == 300
    finally:
        if new_job_id:
            db.execute(text("DELETE FROM job_queue WHERE id = :id"), {"id": new_job_id})
        if run_id:
            db.execute(text("DELETE FROM job_runs WHERE id = :id"), {"id": run_id})
        if sid:
            db.execute(text("DELETE FROM scheduled_jobs WHERE id = :id"), {"id": sid})
        db.commit()
        db.close()


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


def test_scheduler_tick_records_legacy_ios_android_only_schedule_without_queueing():
    db = SessionLocal()
    sid = None
    run_id = None
    try:
        sid = create_scheduled_job(
            db,
            name="legacy ios post daemon",
            job_type="post",
            phone_serial="ios:abc123",
            schedule_type="interval",
            interval_minutes=60,
            config_json={"action": "draft"},
            is_enabled=1,
        )
        sched = (
            db.execute(text("SELECT * FROM scheduled_jobs WHERE id = :sid"), {"sid": sid})
            .mappings()
            .one()
        )

        result = _enqueue_due_schedule(db, dict(sched), datetime.now())

        assert result["ok"] is False
        assert result["error"] == "post jobs are Android-only until the iOS TikTok workflow is ported"
        run_id = result["run_id"]

        queued = db.execute(
            text("SELECT COUNT(*) FROM job_queue WHERE scheduled_job_id = :sid"),
            {"sid": sid},
        ).scalar()
        assert queued == 0

        run = (
            db.execute(text("SELECT * FROM job_runs WHERE id = :id"), {"id": run_id})
            .mappings()
            .one()
        )
        assert run["scheduled_job_id"] == sid
        assert run["phone_serial"] == "ios:abc123"
        assert run["job_type"] == "post"
        assert run["status"] == "failed"
        assert run["trigger"] == "scheduled"
        assert run["duration_s"] == 0
        assert run["error_msg"] == (
            "preflight: post jobs are Android-only until the iOS TikTok workflow is ported"
        )
    finally:
        if sid:
            db.execute(text("DELETE FROM job_queue WHERE scheduled_job_id = :sid"), {"sid": sid})
            db.execute(text("DELETE FROM job_runs WHERE scheduled_job_id = :sid"), {"sid": sid})
            db.execute(text("DELETE FROM scheduled_jobs WHERE id = :sid"), {"sid": sid})
            db.commit()
        db.close()


def test_scheduler_responses_include_platform_metadata_for_ios_jobs():
    client = TestClient(app)
    db = SessionLocal()
    sid = None
    qid = None
    run_id = None
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    config = {"skill": "safari", "workflow": "read_news", "params": {"url": "https://text.npr.org/"}}
    try:
        sid = create_scheduled_job(
            db,
            name="ios news skill",
            job_type="skill_workflow",
            phone_serial="ios:abc123",
            schedule_type="daily",
            daily_times=["23:59"],
            config_json=config,
            is_enabled=1,
        )
        qid = enqueue_job(
            db,
            scheduled_job_id=sid,
            phone_serial="ios:abc123",
            job_type="skill_workflow",
            config_json=config,
            status="pending",
            trigger="manual",
        )
        db.execute(
            text(
                "INSERT INTO job_runs "
                "(scheduled_job_id, phone_serial, job_type, priority, config_json, status, "
                "enqueued_at, started_at, finished_at, duration_s, trigger) "
                "VALUES (:sid, :phone, :job_type, :priority, :config_json, :status, "
                ":enqueued_at, :started_at, :finished_at, :duration_s, :trigger)"
            ),
            {
                "sid": sid,
                "phone": "ios:abc123",
                "job_type": "skill_workflow",
                "priority": 2,
                "config_json": json.dumps(config),
                "status": "completed",
                "enqueued_at": now,
                "started_at": now,
                "finished_at": now,
                "duration_s": 1,
                "trigger": "manual",
            },
        )
        run_id = db.execute(text("SELECT last_insert_rowid()")).scalar()
        db.commit()

        schedules = client.get("/api/schedules").json()
        schedule = next(item for item in schedules if item["id"] == sid)
        assert schedule["platform"] == "ios"
        assert schedule["last_run"]["platform"] == "ios"

        queue = client.get("/api/scheduler/queue").json()
        queued = next(item for item in queue if item["id"] == qid)
        assert queued["platform"] == "ios"
        assert queued["schedule_name"] == "ios news skill"

        status = client.get("/api/scheduler/status").json()
        assert status["ios:abc123"]["platform"] == "ios"
        assert status["ios:abc123"]["pending"] >= 1

        history = client.get("/api/scheduler/history").json()
        run = next(item for item in history if item["id"] == run_id)
        assert run["platform"] == "ios"
        assert run["schedule_name"] == "ios news skill"

        timeline = client.get("/api/scheduler/timeline").json()
        future = next(item for item in timeline["future"] if item["scheduled_job_id"] == sid)
        past = next(item for item in timeline["past"] if item["id"] == run_id)
        assert future["platform"] == "ios"
        assert past["platform"] == "ios"
    finally:
        if qid:
            db.execute(text("DELETE FROM job_queue WHERE id = :id"), {"id": qid})
        if run_id:
            db.execute(text("DELETE FROM job_runs WHERE id = :id"), {"id": run_id})
        if sid:
            db.execute(text("DELETE FROM scheduled_jobs WHERE id = :id"), {"id": sid})
        db.commit()
        db.close()
