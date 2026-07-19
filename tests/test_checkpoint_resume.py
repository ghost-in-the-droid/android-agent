"""C1: checkpoint control columns + resume/abort endpoint."""

import pytest
from fastapi import HTTPException

from gitd.routers.skills import api_skill_run_resume


@pytest.fixture(autouse=True)
def _tables():
    from gitd.models.base import Base, engine, ensure_additive_columns

    Base.metadata.create_all(engine)
    ensure_additive_columns()
    yield


def _mk_run(status="awaiting_human"):
    from gitd.models.base import SessionLocal
    from gitd.models.skill_compat import SkillRun

    db = SessionLocal()
    run = SkillRun(
        device_serial="devCP", skill_name="proton_signup", kind="hard",
        target_type="workflow", target_name="recorded", status=status,
        checkpoint_json='{"reason": "captcha", "prompt": "solve the puzzle"}',
    )
    db.add(run)
    db.commit()
    rid = run.id
    db.close()
    return rid


def test_ensure_additive_columns_adds_checkpoint_fields():
    from gitd.models.base import SessionLocal
    from gitd.models.skill_compat import SkillRun

    rid = _mk_run()
    db = SessionLocal()
    try:
        row = db.get(SkillRun, rid)
        assert row.resume_signal is None  # column exists, default null
        assert row.checkpoint_json is not None
    finally:
        db.close()


def test_resume_sets_signal():
    from gitd.models.base import SessionLocal
    from gitd.models.skill_compat import SkillRun

    rid = _mk_run()
    db = SessionLocal()
    try:
        res = api_skill_run_resume(rid, {"action": "resume"}, db)
        assert res == {"ok": True, "run_id": rid, "action": "resume"}
        assert db.get(SkillRun, rid).resume_signal == "resume"
    finally:
        db.close()


def test_resume_defaults_to_resume_action():
    from gitd.models.base import SessionLocal
    from gitd.models.skill_compat import SkillRun

    rid = _mk_run()
    db = SessionLocal()
    try:
        api_skill_run_resume(rid, {}, db)
        assert db.get(SkillRun, rid).resume_signal == "resume"
    finally:
        db.close()


def test_abort_sets_signal():
    from gitd.models.base import SessionLocal
    from gitd.models.skill_compat import SkillRun

    rid = _mk_run()
    db = SessionLocal()
    try:
        api_skill_run_resume(rid, {"action": "abort"}, db)
        assert db.get(SkillRun, rid).resume_signal == "abort"
    finally:
        db.close()


def test_invalid_action_400():
    from gitd.models.base import SessionLocal

    rid = _mk_run()
    db = SessionLocal()
    try:
        with pytest.raises(HTTPException) as ei:
            api_skill_run_resume(rid, {"action": "explode"}, db)
        assert ei.value.status_code == 400
    finally:
        db.close()


def test_missing_run_404():
    from gitd.models.base import SessionLocal

    db = SessionLocal()
    try:
        with pytest.raises(HTTPException) as ei:
            api_skill_run_resume(999999, {"action": "resume"}, db)
        assert ei.value.status_code == 404
    finally:
        db.close()


def test_not_awaiting_conflict_409():
    from gitd.models.base import SessionLocal

    rid = _mk_run(status="running")
    db = SessionLocal()
    try:
        with pytest.raises(HTTPException) as ei:
            api_skill_run_resume(rid, {"action": "resume"}, db)
        assert ei.value.status_code == 409
    finally:
        db.close()


def test_engine_checkpoint_auto_resolves_via_real_db():
    """Integration: a checkpoint step drives the real SkillRun status through the
    DB callbacks (awaiting_human → running) and auto-resolves when its condition
    is met on the (mocked) device screen."""
    from unittest.mock import MagicMock

    from gitd.models.base import SessionLocal
    from gitd.models.skill_compat import SkillRun
    from gitd.skills.base import RecordedStepAction

    db = SessionLocal()
    run = SkillRun(device_serial="d", skill_name="s", kind="hard",
                   target_type="workflow", target_name="recorded", status="running")
    db.add(run)
    db.commit()
    rid = run.id
    db.close()

    dev = MagicMock()
    dev.serial = "d"
    dev.dump_xml.return_value = "<node text='mail.proton.me/u/0/inbox'/>"
    step = {"action": "checkpoint", "reason": "captcha", "success": {"screen_has": "/inbox"}}
    res = RecordedStepAction(dev, step, 0, run_id=rid).execute()
    assert res.success and res.data["resolution"] == "auto"

    db = SessionLocal()
    try:
        row = db.get(SkillRun, rid)
        assert row.status == "running"          # resumed
        assert row.checkpoint_json is not None   # recorded what it waited on
    finally:
        db.close()
