"""M7: compat matrix carries skill kind + soft-skill smoke-check verify."""

import pytest

from gitd.services.skill_creation import create_soft_skill
from gitd.skills._run_skill import _soft_smoke_check, _upsert_compat


@pytest.fixture(autouse=True)
def _tables():
    from gitd.models.base import Base, engine, ensure_additive_columns

    Base.metadata.create_all(engine)
    ensure_additive_columns()
    yield


def test_ensure_additive_columns_is_idempotent():
    from gitd.models.base import ensure_additive_columns

    # Second call must not raise even though the columns already exist.
    ensure_additive_columns()
    ensure_additive_columns()


def test_skill_run_and_compat_have_kind_column():
    from gitd.models.base import SessionLocal
    from gitd.models.skill_compat import SkillRun

    db = SessionLocal()
    try:
        run = SkillRun(
            device_serial="devK", skill_name="s1", kind="soft",
            target_type="guidance", target_name="guidance", status="ok",
        )
        db.add(run)
        db.commit()
        _upsert_compat(db, run)
        from gitd.models.skill_compat import SkillCompat

        compat = db.query(SkillCompat).filter_by(device_serial="devK", skill_name="s1").first()
        assert compat is not None
        assert compat.kind == "soft"
        assert compat.status == "ok"
    finally:
        db.close()


def test_soft_smoke_check_ok_without_app_package(tmp_path):
    create_soft_skill(name="sc_ok", guidance="be careful", skills_dir=str(tmp_path))
    ok, err = _soft_smoke_check("sc_ok", {"app_package": ""}, "dev-any", skills_dir=tmp_path)
    assert ok and err is None


def test_soft_smoke_check_fails_on_missing_guidance(tmp_path):
    (tmp_path / "sc_bad").mkdir()
    ok, err = _soft_smoke_check("sc_bad", {}, "dev-any", skills_dir=tmp_path)
    assert not ok and "guidance" in err


def test_soft_smoke_check_fails_when_app_absent(tmp_path, monkeypatch):
    create_soft_skill(name="sc_app", guidance="tips", app_package="com.missing", skills_dir=str(tmp_path))
    import gitd.skills._run_skill as rs

    class _Dev:
        def get_app_version(self, pkg):
            return None  # not installed

    monkeypatch.setattr(rs, "get_device", lambda d: _Dev())
    ok, err = _soft_smoke_check("sc_app", {"app_package": "com.missing"}, "devX", skills_dir=tmp_path)
    assert not ok and "not installed" in err
