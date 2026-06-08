import json

from fastapi.testclient import TestClient
from sqlalchemy import text

from gitd.app import app
from gitd.models.base import SessionLocal
from gitd.services._job_helpers import _parse_job_result_data, _parse_job_summary, _summarize_job_result_data


def _read_news_skill_data() -> dict:
    return {
        "completed_steps": 1,
        "step_results": [
            {
                "name": "read_news",
                "success": True,
                "data": {
                    "ok": True,
                    "platform": "ios",
                    "headlines": [
                        {"title": "First useful headline", "url": "https://text.npr.org/a"},
                        {"title": "Second useful headline", "url": "https://text.npr.org/b"},
                    ],
                    "articles": [
                        {"page_title": "First useful headline", "body_snippet": "Article body"},
                    ],
                },
                "error": None,
                "duration_ms": 123,
            }
        ],
    }


def test_scheduler_log_parser_extracts_skill_result_json(tmp_path):
    payload = _read_news_skill_data()
    log_path = tmp_path / "sched_job.log"
    log_path.write_text(
        "Loaded skill: safari\n"
        "Running workflow: read_news\n"
        "Result: success=True duration=123ms\n"
        f"Data: {json.dumps(payload)}\n",
        encoding="utf-8",
    )

    parsed = _parse_job_result_data(123, log_path=str(log_path))

    assert parsed == payload
    assert _summarize_job_result_data(parsed) == (
        "read_news: 2 headlines | 1 article | first: First useful headline"
    )
    assert _parse_job_summary(123, log_path=str(log_path)) == (
        "read_news: 2 headlines | 1 article | first: First useful headline"
    )


def test_scheduler_history_result_endpoint_returns_structured_skill_data(tmp_path):
    payload = _read_news_skill_data()
    log_path = tmp_path / "sched_job.log"
    log_path.write_text(f"Data: {json.dumps(payload)}\n", encoding="utf-8")
    db = SessionLocal()
    run_id = None
    try:
        db.execute(
            text(
                "INSERT INTO job_runs "
                "(phone_serial, job_type, priority, config_json, status, "
                "duration_s, exit_code, error_msg, log_file, trigger) "
                "VALUES (:phone_serial, :job_type, :priority, :config_json, :status, "
                ":duration_s, :exit_code, :error_msg, :log_file, :trigger)"
            ),
            {
                "phone_serial": "ios:abc123",
                "job_type": "skill_workflow",
                "priority": 2,
                "config_json": json.dumps({"skill": "safari", "workflow": "read_news"}),
                "status": "completed",
                "duration_s": 3,
                "exit_code": 0,
                "error_msg": None,
                "log_file": str(log_path),
                "trigger": "scheduled",
            },
        )
        run_id = db.execute(text("SELECT last_insert_rowid()")).scalar()
        db.commit()

        response = TestClient(app).get(f"/api/scheduler/history/{run_id}/result")

        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True
        assert body["summary"] == "read_news: 2 headlines | 1 article | first: First useful headline"
        assert body["result"]["step_results"][0]["data"]["articles"][0]["body_snippet"] == "Article body"
    finally:
        if run_id is not None:
            db.execute(text("DELETE FROM job_runs WHERE id = :id"), {"id": run_id})
            db.commit()
        db.close()
