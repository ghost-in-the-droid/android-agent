# ruff: noqa: F811 -- imported pytest fixtures are injected by parameter name
"""Skill lifecycle `status:` (active | blocked | deprecated): loader, registry, install warning."""

import importlib.util
import sys
from pathlib import Path

import pytest
import yaml

from gitd.skills import hub
from gitd.skills.engine.errors import SchemaError
from gitd.skills.engine.loader import load_skill

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_skillhub_install import _never, env, fake_cdn  # noqa: E402,F401  (pytest fixtures)

_spec = importlib.util.spec_from_file_location(
    "_test_tools_build_registry_status", REPO / "tools" / "build_registry.py"
)
build_registry = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_registry)

BASE = {
    "name": "demo",
    "version": "1.0.0",
    "author": "alice",
    "license": "MIT",
    "generated_with": "hand",
    "tos_risk": "low",
    "actions": [
        {
            "name": "go",
            "ref_prompt": "Start the example workflow",
            "steps": [{"action": "sleep", "duration_s": 1}],
            "end_state_validator": {"kind": "text_visible", "text": "ok"},
        }
    ],
}


def _skill(tmp_path, **extra) -> Path:
    d = tmp_path / "skillhub" / "alice" / "demo"
    d.mkdir(parents=True, exist_ok=True)
    (d / "skill.yaml").write_text(yaml.safe_dump({**BASE, **extra}))
    return d


# ── loader ──


def test_status_defaults_to_active(tmp_path):
    assert load_skill(_skill(tmp_path)).status == "active"


@pytest.mark.parametrize("value", ["active", "blocked", "deprecated", "draft"])
def test_valid_statuses_load(tmp_path, value):
    assert load_skill(_skill(tmp_path, status=value)).status == value


@pytest.mark.parametrize("value", ["broken", "Blocked", " blocked", True])
def test_invalid_status_is_an_error(tmp_path, value):
    with pytest.raises(SchemaError, match="status"):
        load_skill(_skill(tmp_path, status=value))


@pytest.mark.skipif(not (REPO / "premium/skills/ghost").is_dir(), reason="premium skills are not part of the public tree")
def test_real_signup_skills_status():
    assert load_skill(REPO / "premium/skills/ghost/x_signup").status == "blocked"
    assert load_skill(REPO / "premium/skills/ghost/gmx_signup").status == "blocked"
    assert load_skill(REPO / "premium/skills/ghost/proton_signup").status == "active"


# ── registry ──


def test_registry_emits_status_and_blocked_flag(tmp_path):
    _skill(tmp_path, status="blocked")
    d = tmp_path / "skillhub" / "bob" / "ok"
    d.mkdir(parents=True)
    (d / "skill.yaml").write_text(yaml.safe_dump({**BASE, "name": "ok", "author": "bob"}))
    reg = build_registry.build_registry(tmp_path / "skillhub", now="2026-10-05T12:00:00Z")
    blocked, ok = reg["skills"]["alice/demo"], reg["skills"]["bob/ok"]
    assert (blocked["status"], blocked["flags"]) == ("blocked", {"blocked": True})
    assert (ok["status"], ok["flags"]) == ("active", {"blocked": False})


def test_real_registry_has_no_blocked_skills():
    reg = build_registry.build_registry(REPO / "skillhub", now="2026-10-05T12:00:00Z")
    blocked = {k for k, e in reg["skills"].items() if e["flags"]["blocked"]}
    assert blocked == set()


# ── install ──


def test_blocked_skill_installs_with_warning(env, fake_cdn, capsys):
    reg = env["registry"]
    reg["skills"]["ghost/demo"].update(status="blocked", flags={"blocked": True})
    got = hub.install("ghost/demo", registry=reg, confirm=_never)
    assert got.version == "1.0.0"
    err = capsys.readouterr().err
    assert "ghost/demo@1.0.0 is marked BLOCKED" in err


def test_blocked_flag_alone_still_warns(env, fake_cdn, capsys):
    reg = env["registry"]
    reg["skills"]["ghost/demo"].pop("status", None)
    reg["skills"]["ghost/demo"]["flags"] = {"blocked": True}
    hub.install("ghost/demo", registry=reg, confirm=_never)
    assert "BLOCKED" in capsys.readouterr().err


def test_active_skill_installs_without_status_warning(env, fake_cdn, capsys):
    hub.install("ghost/demo", registry=env["registry"], confirm=_never)
    err = capsys.readouterr().err
    assert "BLOCKED" not in err and "DEPRECATED" not in err


def test_draft_skill_installs_with_warning(env, fake_cdn, capsys):
    reg = env["registry"]
    reg["skills"]["ghost/demo"].update(status="draft", flags={"blocked": False})
    assert hub.install("ghost/demo", registry=reg, confirm=_never).version == "1.0.0"
    assert "ghost/demo@1.0.0 is a DRAFT scaffold" in capsys.readouterr().err


def test_registry_keeps_draft_status(tmp_path):
    _skill(tmp_path, status="draft")
    reg = build_registry.build_registry(tmp_path / "skillhub", now="2026-10-05T12:00:00Z")
    assert (reg["skills"]["alice/demo"]["status"], reg["skills"]["alice/demo"]["flags"]) == (
        "draft",
        {"blocked": False},
    )
    from gitd.skills.engine.loader import VALID_STATUSES

    assert set(build_registry.VALID_STATUSES) == set(VALID_STATUSES)
