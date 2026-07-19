"""M3: skill writer kind + soft-skill creation + loader/detail surfacing."""

import yaml

import gitd.routers.skills as skills_router
from gitd.services.skill_creation import create_recorded_skill, create_soft_skill


def test_recorded_skill_writes_kind_hard(tmp_path):
    create_recorded_skill(
        name="rec1",
        steps=[{"action": "tap", "x": 1, "y": 2}],
        app_package="com.x",
        skills_dir=str(tmp_path),
    )
    meta = yaml.safe_load((tmp_path / "rec1" / "skill.yaml").read_text())
    assert meta["kind"] == "hard"
    assert (tmp_path / "rec1" / "workflows" / "recorded.json").exists()


def test_soft_skill_writes_guidance_no_steps(tmp_path):
    res = create_soft_skill(
        name="soft1",
        guidance="# Reddit\nWatch out for the login wall; dismiss it before scrolling.",
        app_package="com.reddit.frontpage",
        description="Reddit tips",
        skills_dir=str(tmp_path),
    )
    assert res["kind"] == "soft"
    sdir = tmp_path / "soft1"
    meta = yaml.safe_load((sdir / "skill.yaml").read_text())
    assert meta["kind"] == "soft"
    assert meta["app_package"] == "com.reddit.frontpage"
    assert (sdir / "guidance.md").exists()
    assert "login wall" in (sdir / "guidance.md").read_text()
    assert not (sdir / "workflows" / "recorded.json").exists()


def test_soft_skill_requires_guidance(tmp_path):
    try:
        create_soft_skill(name="empty", guidance="   ", skills_dir=str(tmp_path))
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_loader_and_detail_surface_kind_and_guidance(tmp_path, monkeypatch):
    # Point the router's skills dir at a temp dir with one soft + one hard skill.
    create_soft_skill(name="softx", guidance="Be careful.", app_package="com.a", skills_dir=str(tmp_path))
    create_recorded_skill(name="hardx", steps=[{"action": "home"}], app_package="com.b", skills_dir=str(tmp_path))
    monkeypatch.setattr(skills_router, "_SKILLS_DIR", tmp_path)

    loaded = skills_router._load_all_skills()
    assert loaded["softx"]["kind"] == "soft"
    assert loaded["softx"]["has_guidance"] is True
    assert loaded["hardx"]["kind"] == "hard"
    assert loaded["hardx"]["has_guidance"] is False

    detail = skills_router.api_skill_detail("softx")
    assert detail["kind"] == "soft"
    assert detail["guidance"].startswith("Be careful.")
