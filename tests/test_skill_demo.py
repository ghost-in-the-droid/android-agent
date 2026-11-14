"""Optional skill demo: loader limits, lint warnings, registry + index records. Tiny generated files.

ffprobe is never executed here: lint's probe is replaced by a fake (or disabled).
"""

import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

import gitd.skills.engine.cli as cli
from gitd.skills.engine.errors import SchemaError
from gitd.skills.engine.loader import DEMO_MAX_BYTES, DEMO_WARN_BYTES, load_skill

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("_test_demo_build_registry", REPO / "tools" / "build_registry.py")
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


def blob(path: Path, size: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"\x1aE\xdf\xa3")  # content is irrelevant: nothing decodes it
        if size > 4:
            f.seek(size - 1)
            f.write(b"\0")
    return path


def skill(tmp_path, demos=(), **extra) -> Path:
    d = tmp_path / "skillhub" / "alice" / "demo"
    d.mkdir(parents=True, exist_ok=True)
    (d / "skill.yaml").write_text(yaml.safe_dump({**BASE, **extra}))
    (d / "SOFT.md").write_text("# demo\n\n### go\n")
    (d / "icon.webp").write_bytes(b"RIFF....WEBP")
    for name, size in demos:
        blob(d / name, size)
    return d


@pytest.fixture(autouse=True)
def no_real_ffprobe(monkeypatch):
    monkeypatch.setattr(cli, "_probe_media", lambda path: None)


def test_default_demo_order_and_explicit_path(tmp_path):
    assert load_skill(skill(tmp_path)).demo is None
    assert load_skill(skill(tmp_path, [("demo.gif", 10)])).demo == "demo.gif"
    assert load_skill(skill(tmp_path, [("demo.mp4", 10)])).demo == "demo.mp4"
    assert load_skill(skill(tmp_path, [("demo.webm", 10)])).demo == "demo.webm"
    d = skill(tmp_path, [("media/clip.mp4", 10)], demo="media/clip.mp4")
    assert load_skill(d).demo == "media/clip.mp4"


@pytest.mark.parametrize(
    "demos,extra,match",
    [
        ([("demo.mov", 10)], {"demo": "demo.mov"}, "webm, mp4 or gif"),
        ([], {"demo": "missing.webm"}, "does not exist"),
        ([], {"demo": "../x.webm"}, "inside the skill dir"),
        ([("demo.webm", DEMO_MAX_BYTES + 1)], {}, "limit is 3145728"),
    ],
)
def test_demo_validation_errors(tmp_path, demos, extra, match):
    with pytest.raises(SchemaError, match=match):
        load_skill(skill(tmp_path, demos, **extra))


def test_demo_at_hard_limit_loads(tmp_path):
    assert load_skill(skill(tmp_path, [("demo.webm", DEMO_MAX_BYTES)])).demo == "demo.webm"


def _lint(d, capsys):
    cli.main(["lint", str(d)])
    return capsys.readouterr().out


def test_lint_size_and_gif_warnings(tmp_path, capsys):
    out = _lint(skill(tmp_path, [("demo.webm", DEMO_WARN_BYTES)]), capsys)
    assert "Demo" not in out
    out = _lint(skill(tmp_path, [("demo.webm", DEMO_WARN_BYTES + 1)]), capsys)
    assert "keep it under 1572864 (1.5 MB)" in out
    for f in (tmp_path / "skillhub" / "alice" / "demo").glob("demo.*"):
        f.unlink()
    out = _lint(skill(tmp_path, [("demo.gif", 100)]), capsys)
    assert "prefer webm/mp4" in out


def test_lint_probe_warnings(tmp_path, capsys, monkeypatch):
    d = skill(tmp_path, [("demo.mp4", 100)])
    monkeypatch.setattr(cli, "_probe_media", lambda path: (45.2, 1080, 1920))
    out = _lint(d, capsys)
    assert "runs 45 s; keep it to 30 s or less" in out and "1080x1920; keep the long side to 720 px" in out
    monkeypatch.setattr(cli, "_probe_media", lambda path: (12.0, 720, 404))
    assert "Demo" not in _lint(d, capsys)


def test_probe_skips_silently_without_ffprobe(tmp_path, monkeypatch):
    monkeypatch.undo()  # the real _probe_media, but no ffprobe on PATH
    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert cli._probe_media(blob(tmp_path / "x.webm", 10)) is None


def test_registry_demo_record_excluded_from_files(tmp_path):
    skill(tmp_path, [("media/clip.mp4", 2048)], demo="media/clip.mp4")
    side = {}
    reg = build_registry.build_registry(tmp_path / "skillhub", now="2026-10-06T00:00:00Z", side=side)
    entry = reg["skills"]["alice/demo"]
    assert entry["demo"] == {"path": "media/clip.mp4", "bytes": 2048, "type": "video/mp4"}
    assert "media/clip.mp4" not in entry["versions"]["1.0.0"]["files"]
    assert side["index"]["alice.demo"]["versions"][-1]["demo"] == entry["demo"]
    assert entry["quality"]["signals"]["demo"] is True


def test_registry_default_demo_types_and_signal(tmp_path):
    d = skill(tmp_path, [("demo.gif", 300)])
    entry = build_registry.build_registry(tmp_path / "skillhub", now="2026-10-06T00:00:00Z")["skills"]["alice/demo"]
    assert entry["demo"] == {"path": "demo.gif", "bytes": 300, "type": "image/gif"}
    assert "demo.gif" not in entry["versions"]["1.0.0"]["files"]
    (d / "demo.gif").unlink()
    blob(d / "demo.webm", DEMO_MAX_BYTES + 1)  # over the hard limit: no demo signal
    entry = build_registry.build_registry(tmp_path / "skillhub", now="2026-10-06T00:00:00Z")["skills"]["alice/demo"]
    assert entry["demo"]["type"] == "video/webm" and entry["quality"]["signals"]["demo"] is False
    (d / "demo.webm").unlink()
    entry = build_registry.build_registry(tmp_path / "skillhub", now="2026-10-06T00:00:00Z")["skills"]["alice/demo"]
    assert entry["demo"] is None and entry["quality"]["signals"]["demo"] is False


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_tagged_version_demo_from_git(tmp_path):
    repo = tmp_path
    d = skill(tmp_path, [("demo.webm", 4096)])
    env = {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
        "PATH": "/usr/bin:/bin:/usr/local/bin",
        "HOME": str(tmp_path),
    }
    for args in (["init", "-q"], ["add", "."], ["commit", "-q", "-m", "v1"], ["tag", "alice/demo-v1.0.0"]):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, env=env)
    (d / "skill.yaml").write_text(yaml.safe_dump({**BASE, "version": "1.1.0"}))
    (d / "demo.webm").unlink()
    side = {}
    build_registry.build_registry(tmp_path / "skillhub", now="2026-10-06T00:00:00Z", side=side)
    by_version = {r["version"]: r["demo"] for r in side["index"]["alice.demo"]["versions"]}
    assert by_version == {"1.0.0": {"path": "demo.webm", "bytes": 4096, "type": "video/webm"}, "1.1.0": None}


# ── before / after pair: demos/before-after.<ext> + demos/before-after.json ────────────────────

BA_METRICS = {
    "schema_version": 1,
    "action": "go",
    "prompt": "Start the example workflow",
    "ok_means": "verified_task_check",
    "before": {"seconds": 52.2, "tokens": 254235, "tool_calls": 18, "ok": False},
    "after": {"seconds": 27.5, "tokens": 21500, "tool_calls": 5, "ok": True},
    "notes": "same prompt, same phone",
}


def ba_skill(tmp_path, metrics=BA_METRICS, clip=("demos/before-after.webm", 2048), demos=()):
    d = skill(tmp_path, [clip, *demos] if clip else list(demos))
    if metrics is not None:
        (d / "demos").mkdir(exist_ok=True)
        (d / "demos" / "before-after.json").write_text(
            json.dumps(metrics) if isinstance(metrics, dict) else metrics
        )
    return d


def test_before_after_files_are_reserved_not_action_problems(tmp_path):
    s = load_skill(ba_skill(tmp_path, demos=[("demos/go.webm", 10)]))
    assert s.before_after == "demos/before-after.webm"
    assert s.before_after_metrics["after"]["tokens"] == 21500
    assert s.demos == {"go": "demos/go.webm"} and s._demo_problems == []
    assert s.demo == "demos/go.webm"  # the pair never becomes the default clip


def test_before_after_pair_alone_is_not_the_default_demo(tmp_path):
    s = load_skill(ba_skill(tmp_path))
    assert s.before_after == "demos/before-after.webm" and s.demo is None and s.demos == {}


def test_before_after_clip_without_metrics_and_mp4_fallback(tmp_path):
    s = load_skill(ba_skill(tmp_path, metrics=None, clip=("demos/before-after.mp4", 10)))
    assert s.before_after == "demos/before-after.mp4" and s.before_after_metrics is None


def test_before_after_clip_over_limit_is_an_error(tmp_path):
    with pytest.raises(SchemaError, match="limit is 3145728"):
        load_skill(ba_skill(tmp_path, clip=("demos/before-after.webm", DEMO_MAX_BYTES + 1)))


@pytest.mark.parametrize(
    "metrics,match",
    [
        ("{not json", "not valid JSON"),
        ({**BA_METRICS, "schema_version": 2}, "schema_version must be 1"),
        ({**BA_METRICS, "after": {"seconds": 1, "tokens": 1}}, "`after` needs"),
        ({**BA_METRICS, "before": {**BA_METRICS["before"], "tokens": -1}}, "`before.tokens` must be a number"),
        ({**BA_METRICS, "before": {**BA_METRICS["before"], "ok": "yes"}}, "`before.ok` must be true or false"),
        ({**BA_METRICS, "ok_means": "vibes"}, "ok_means must be one of"),
        ({**BA_METRICS, "notes": 3}, "`notes` must be a string"),
    ],
)
def test_before_after_metrics_validation(tmp_path, metrics, match):
    with pytest.raises(SchemaError, match=match):
        load_skill(ba_skill(tmp_path, metrics=metrics))


def test_registry_before_after_record(tmp_path):
    ba_skill(tmp_path, demos=[("demos/go.webm", 10)])
    side = {}
    reg = build_registry.build_registry(tmp_path / "skillhub", now="2026-10-06T00:00:00Z", side=side)
    entry = reg["skills"]["alice/demo"]
    assert entry["before_after"] == {
        "clip": {"path": "demos/before-after.webm", "bytes": 2048, "type": "video/webm"},
        "metrics": BA_METRICS,
    }
    assert "demos/before-after.webm" not in entry["versions"]["1.0.0"]["files"]
    assert "demos/before-after.json" not in entry["versions"]["1.0.0"]["files"]
    assert entry["demo"] == {"path": "demos/go.webm", "bytes": 10, "type": "video/webm"}
    assert entry["demos"] == {"go": entry["demo"]}
    assert entry["quality"]["signals"]["demo"] is True
    assert entry["quality"]["signals"]["before_after"] is True  # scoring v1.3 docs item, same files


def test_registry_without_pair_is_null(tmp_path):
    skill(tmp_path, [("demo.webm", 10)])
    entry = build_registry.build_registry(tmp_path / "skillhub", now="2026-10-06T00:00:00Z")["skills"]["alice/demo"]
    assert entry["before_after"] is None and entry["quality"]["signals"]["before_after"] is False
