"""Optional skill icon: loader validation, registry field + files entry, lint warning."""

import hashlib
import importlib.util
from pathlib import Path

import pytest
import yaml

from gitd.skills.engine.cli import main as cli_main
from gitd.skills.engine.errors import SchemaError
from gitd.skills.engine.loader import MAX_ICON_BYTES, load_skill

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("_test_icon_build_registry", REPO / "tools" / "build_registry.py")
build_registry = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_registry)

BASE = {
    "name": "demo",
    "version": "1.0.0",
    "author": "alice",
    "description": "demo skill",
    "skill_class": "hard",
    "tos_risk": "low",
    "license": "MIT",
    "generated_with": "human",
    "fingerprint": {"os": "android", "app_package": "com.example"},
    "actions": [
        {
            "name": "go",
            "description": "go",
            "ref_prompt": "Start the example workflow",
            "steps": [{"action": "sleep", "duration_s": 1}],
            "end_state_validator": {"kind": "text_visible", "text": "ok"},
            "test_case": {"ref_prompt_variants": ["go"], "expected_success": True},
        }
    ],
}


def skill(tmp_path, icon_bytes=None, name="icon.webp", **extra) -> Path:
    d = tmp_path / "skillhub" / "alice" / "demo"
    d.mkdir(parents=True, exist_ok=True)
    (d / "skill.yaml").write_text(yaml.safe_dump({**BASE, **extra}))
    (d / "SOFT.md").write_text("# demo\n\n### go\n")
    if icon_bytes is not None:
        (d / name).parent.mkdir(parents=True, exist_ok=True)
        (d / name).write_bytes(icon_bytes)
    return d


def test_icon_defaults_to_icon_webp_when_present(tmp_path):
    assert load_skill(skill(tmp_path)).icon is None
    assert load_skill(skill(tmp_path, b"RIFF....WEBP")).icon == "icon.webp"


def test_explicit_icon_path(tmp_path):
    d = skill(tmp_path, b"\x89PNG", name="art/logo.png", icon="art/logo.png")
    assert load_skill(d).icon == "art/logo.png"


@pytest.mark.parametrize(
    "extra,data,match",
    [
        ({"icon": "missing.webp"}, None, "does not exist"),
        ({"icon": "../escape.webp"}, None, "inside the skill dir"),
        ({}, b"x" * (MAX_ICON_BYTES + 1), "limit is 16384"),
    ],
)
def test_icon_validation_errors(tmp_path, extra, data, match):
    with pytest.raises(SchemaError, match=match):
        load_skill(skill(tmp_path, data, **extra))


def test_icon_at_limit_is_fine(tmp_path):
    assert load_skill(skill(tmp_path, b"x" * MAX_ICON_BYTES)).icon == "icon.webp"


def test_registry_icon_field_and_files_hash(tmp_path):
    data = b"RIFF\x00\x00\x00\x00WEBPVP8 fake"
    skill(tmp_path, data)
    entry = build_registry.build_registry(tmp_path / "skillhub", now="2026-10-06T00:00:00Z")["skills"]["alice/demo"]
    assert entry["icon"] == "icon.webp"
    files = entry["versions"]["1.0.0"]["files"]
    assert files["icon.webp"] == "sha256:" + hashlib.sha256(data).hexdigest()
    (tmp_path / "skillhub" / "alice" / "demo" / "icon.webp").unlink()
    entry = build_registry.build_registry(tmp_path / "skillhub", now="2026-10-06T00:00:00Z")["skills"]["alice/demo"]
    assert entry["icon"] is None and "icon.webp" not in entry["versions"]["1.0.0"]["files"]


def test_lint_warns_only_without_icon(tmp_path, capsys):
    d = skill(tmp_path)
    cli_main(["lint", str(d)])
    assert "No app icon" in capsys.readouterr().out
    (d / "icon.webp").write_bytes(b"RIFF....WEBP")
    cli_main(["lint", str(d)])
    assert "No app icon" not in capsys.readouterr().out
