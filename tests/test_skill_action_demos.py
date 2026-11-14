"""One demo per action: demos/<action>.webm|mp4|gif (+ .spec.yaml). Tiny generated files, no ffprobe."""

import importlib.util
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

import gitd.skills.engine.cli as cli
from gitd.skills.engine.errors import SchemaError
from gitd.skills.engine.loader import DEMO_MAX_BYTES, discover_action_demos, load_skill

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "_test_action_demos_build_registry", REPO / "tools" / "build_registry.py"
)
build_registry = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_registry)
_qspec = importlib.util.spec_from_file_location("_test_action_demos_quality", REPO / "tools" / "quality.py")
quality_mod = importlib.util.module_from_spec(_qspec)
_qspec.loader.exec_module(quality_mod)

ACTION = {
    "description": "x",
    "steps": [{"action": "sleep", "duration_s": 1}],
    "end_state_validator": {"kind": "text_visible", "text": "ok"},
}
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
            **ACTION,
            "name": "open_app",
            "ref_prompt": "Open the example application",
            "test_case": {"ref_prompt_variants": ["open"], "expected_success": True},
        },
        {
            **ACTION,
            "name": "search",
            "ref_prompt": "Search the example application",
            "test_case": {"ref_prompt_variants": ["search"], "expected_success": True},
        },
    ],
}


def blob(path: Path, size: int = 64) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"\x1aE\xdf\xa3")
        if size > 4:
            f.seek(size - 1)
            f.write(b"\0")
    return path


def skill(tmp_path, files=(), **extra) -> Path:
    d = tmp_path / "skillhub" / "alice" / "demo"
    d.mkdir(parents=True, exist_ok=True)
    (d / "skill.yaml").write_text(yaml.safe_dump({**BASE, **extra}))
    (d / "SOFT.md").write_text("# demo\n\n### open_app\n\n### search\n")
    (d / "icon.webp").write_bytes(b"RIFF....WEBP")
    for name, size in files:
        if name.endswith(".spec.yaml"):
            (d / name).parent.mkdir(parents=True, exist_ok=True)
            (d / name).write_text("steps: []\n")
        else:
            blob(d / name, size)
    return d


@pytest.fixture(autouse=True)
def no_real_ffprobe(monkeypatch):
    monkeypatch.setattr(cli, "_probe_media", lambda path: None)


def test_discover_prefers_webm_and_reports_problems():
    clips, dups, problems = discover_action_demos(
        [
            "demos/search.gif",
            "demos/search.webm",
            "demos/open_app.mp4",
            "demos/open_app.spec.yaml",
            "demos/.DS_Store",
            "skill.yaml",
            "demos/nope.webm",
            "demos/search.mov",
            "demos/sub/x.webm",
            "demos/ghost.spec.yaml",
        ],
        ["open_app", "search"],
    )
    assert clips == {"open_app": "demos/open_app.mp4", "search": "demos/search.webm"}
    assert dups == {"search": ["demos/search.gif"]}
    assert len(problems) == 4 and any("'nope'" in p for p in problems) and any("sub-dirs" in p for p in problems)


def test_loader_discovers_clips_and_default(tmp_path):
    d = skill(tmp_path, [("demos/search.webm", 100), ("demos/open_app.mp4", 50), ("demos/search.spec.yaml", 0)])
    s = load_skill(d)
    assert s.demos == {"search": "demos/search.webm", "open_app": "demos/open_app.mp4"}
    assert s.demo == "demos/open_app.mp4"  # first action (in action order) with a clip


def test_default_falls_back_to_legacy_and_explicit_wins(tmp_path):
    d = skill(tmp_path, [("demo.webm", 10)])
    assert load_skill(d).demo == "demo.webm" and load_skill(d).demos == {}
    blob(d / "demos" / "search.webm")
    assert load_skill(d).demo == "demos/search.webm"  # an action clip beats the legacy file
    d = skill(tmp_path, demo="demo.webm")
    assert load_skill(d).demo == "demo.webm"


@pytest.mark.parametrize(
    "files,match",
    [
        ([("demos/nope.webm", 10)], "no action named 'nope'"),
        ([("demos/search.mov", 10)], "not a webm/mp4/gif"),
        ([("demos/a/search.webm", 10)], "sub-dirs"),
        ([("demos/ghost.spec.yaml", 0)], "no action named 'ghost'"),
        ([("demos/search.webm", DEMO_MAX_BYTES + 1)], "limit is 3145728"),
    ],
)
def test_loader_rejects_bad_demo_files(tmp_path, files, match):
    with pytest.raises(SchemaError, match=match):
        load_skill(skill(tmp_path, files))


def test_registry_records_and_signals(tmp_path):
    d = skill(tmp_path, [("demos/open_app.webm", 300)])
    side = {}
    reg = build_registry.build_registry(tmp_path / "skillhub", now="2026-10-06T00:00:00Z", side=side)
    e = reg["skills"]["alice/demo"]
    assert e["demos"] == {"open_app": {"path": "demos/open_app.webm", "bytes": 300, "type": "video/webm"}}
    assert e["demo"] == e["demos"]["open_app"]
    assert not any(n.startswith("demos/") for n in e["versions"]["1.0.0"]["files"])
    rec = side["index"]["alice.demo"]["versions"][-1]
    assert rec["demos"] == e["demos"] and rec["demo"] == e["demo"]
    sig = e["quality"]["signals"]
    assert sig["demo"] is True and sig["demo_all_actions"] is False

    blob(d / "demos" / "search.mp4", 200)
    e = build_registry.build_registry(tmp_path / "skillhub", now="2026-10-06T00:00:00Z")["skills"]["alice/demo"]
    assert set(e["demos"]) == {"open_app", "search"} and e["quality"]["signals"]["demo_all_actions"] is True


def test_docs_points_split():
    q = quality_mod.quality
    base = {"manifest_valid": True, "readme": True, "failure_modes": True}
    assert q(base, now="2026-10-06T00:00:00Z")["categories"]["docs"] == 10
    assert q({**base, "demo": True}, now="2026-10-06T00:00:00Z")["categories"]["docs"] == 14  # demo_any 4 (v1.3)
    full = {**base, "demo": True, "demo_all_actions": True}
    assert q(full, now="2026-10-06T00:00:00Z")["categories"]["docs"] == 17  # + demo_all_actions 3
    assert q({**full, "before_after": True}, now="2026-10-06T00:00:00Z")["categories"]["docs"] == 20  # + pair 3 = cap


def test_lint_warns_per_action_and_duplicates(tmp_path, capsys):
    d = skill(tmp_path, [("demos/search.webm", 10), ("demos/search.gif", 10)])
    cli.main(["lint", str(d)])
    out = capsys.readouterr().out
    assert "open_app: no demo clip (demos/open_app.webm)" in out
    assert "search: no demo clip" not in out
    assert "demos/search.gif: duplicate clip" in out


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_tagged_version_demos_from_git(tmp_path):
    d = skill(tmp_path, [("demos/search.webm", 4096)])
    env = {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
        "PATH": "/usr/bin:/bin:/usr/local/bin",
        "HOME": str(tmp_path),
    }
    for args in (["init", "-q"], ["add", "."], ["commit", "-q", "-m", "v1"], ["tag", "alice/demo-v1.0.0"]):
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True, env=env)
    (d / "skill.yaml").write_text(yaml.safe_dump({**BASE, "version": "1.1.0"}))
    shutil.rmtree(d / "demos")
    side = {}
    build_registry.build_registry(tmp_path / "skillhub", now="2026-10-06T00:00:00Z", side=side)
    recs = {r["version"]: r for r in side["index"]["alice.demo"]["versions"]}
    clip = {"path": "demos/search.webm", "bytes": 4096, "type": "video/webm"}
    assert recs["1.0.0"]["demos"] == {"search": clip} and recs["1.0.0"]["demo"] == clip
    assert recs["1.1.0"]["demos"] == {} and recs["1.1.0"]["demo"] is None
