"""Skill Hub loader resolution + skill-local Python imports (contract sections 1 + 2)."""
import os
import sys
from pathlib import Path

import pytest

from gitd.skills.engine import loader as loader_mod
from gitd.skills.engine.context import RunContext
from gitd.skills.engine.dispatch import dispatch
from gitd.skills.engine.errors import ParamError, SkillNotFoundError
from gitd.skills.engine.loader import load_skill, resolve_skill_dir
from gitd.skills.engine.pyimport import CTX_SKILL_KEY, ident_for_skill, module_name, resolve_for_skill
from gitd.skills.engine.validators import evaluate
from gitd.skills.refs import parse_ref, version_key

REPO = Path(__file__).resolve().parents[1]

SKILL_YAML = """\
name: {slug}
version: {version}
author: {author}
description: "test skill"
skill_class: hard
license: MIT
generated_with: human
fingerprint:
  os: android
  app_package: com.example
actions:
  - name: ping
    ref_prompt: "ping it"
    steps:
      - python_action: "helpers:ping"
    end_state_validator:
      - {{kind: custom_python, function: "validators:ok"}}
"""

HELPERS = """\
STATE = {{"version": "{version}", "calls": 0}}

def ping(device, params, context):
    STATE["calls"] += 1
    return {{"success": True, "data": {{"pong": STATE["version"], "calls": STATE["calls"]}}}}
"""

VALIDATORS = """\
def ok(device, context):
    return context.result.get("pong") is not None
"""


def make_skill(root: Path, author="alice", slug="demo", version="1.0.0") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "skill.yaml").write_text(SKILL_YAML.format(author=author, slug=slug, version=version))
    (root / "helpers.py").write_text(HELPERS.format(version=version))
    (root / "validators.py").write_text(VALIDATORS)
    return root


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """Empty installed dir + empty repo hub, both under tmp."""
    installed = tmp_path / "installed"
    hub = tmp_path / "repo" / "skillhub"
    installed.mkdir()
    hub.mkdir(parents=True)
    monkeypatch.setenv("GHOST_SKILLS_DIR", str(installed))
    monkeypatch.setattr(loader_mod, "find_skillhub_root", lambda: hub)
    return installed, hub


# ── refs ────────────────────────────────────────────────────────────────────

def test_parse_ref_defaults_and_pins():
    r = parse_ref("Alice/Demo")
    assert (r.author, r.slug, r.version, r.pinned) == ("alice", "demo", "latest", False)
    assert parse_ref("ghost/tiktok@2.0.0").pinned
    assert parse_ref("ghost/tiktok@main").version == "main"
    for bad in ("tiktok", "a/b/c", "a/b@notaversion", "../x", ""):
        with pytest.raises(ValueError):
            parse_ref(bad)


def test_version_key_orders_semver():
    vs = ["1.0.0", "1.10.0", "1.2.0", "2.0.0-rc1", "2.0.0", "1.2.0-alpha"]
    assert sorted(vs, key=version_key) == ["1.0.0", "1.2.0-alpha", "1.2.0", "1.10.0", "2.0.0-rc1", "2.0.0"]


# ── resolution order ────────────────────────────────────────────────────────

def test_path_wins(tmp_path, isolated):
    d = make_skill(tmp_path / "anywhere" / "demo")
    assert load_skill(d).name == "demo"
    assert load_skill(d / "skill.yaml").skill_dir == d.resolve()


def test_installed_latest_symlink_then_txt_then_highest(isolated):
    installed, _hub = isolated
    root = installed / "alice" / "demo"
    for v in ("1.0.0", "1.2.0", "1.10.0"):
        make_skill(root / v, version=v)
    # no pointer: highest semver
    assert load_skill("alice/demo").version == "1.10.0"
    # latest.txt pointer
    (root / "latest.txt").write_text("1.2.0\n")
    assert load_skill("alice/demo").version == "1.2.0"
    # @latest symlink wins over latest.txt
    if hasattr(os, "symlink"):
        (root / "@latest").symlink_to("1.0.0")
        assert load_skill("alice/demo@latest").version == "1.0.0"
    # pinned
    assert load_skill("alice/demo@1.10.0").version == "1.10.0"


def test_installed_beats_repo(isolated):
    installed, hub = isolated
    make_skill(installed / "alice" / "demo" / "1.0.0", version="1.0.0")
    make_skill(hub / "alice" / "demo", version="2.0.0")
    assert load_skill("alice/demo").version == "1.0.0"


def test_repo_fallback_respects_pin(isolated):
    _installed, hub = isolated
    make_skill(hub / "alice" / "demo", version="2.0.0")
    assert load_skill("alice/demo").version == "2.0.0"
    assert load_skill("alice/demo@2.0.0").version == "2.0.0"
    with pytest.raises(SkillNotFoundError):
        load_skill("alice/demo@1.0.0")


def test_main_ref_warns_and_resolves(isolated, caplog):
    _installed, hub = isolated
    make_skill(hub / "alice" / "demo")
    with caplog.at_level("WARNING"):
        assert load_skill("alice/demo@main").name == "demo"
    assert "@main" in caplog.text


def test_not_found_has_install_hint(isolated):
    with pytest.raises(SkillNotFoundError) as ei:
        load_skill("alice/missing@1.2.3")
    assert ei.value.hint == "ghost skill install alice/missing@1.2.3"
    assert ei.value.payload["looked_in"]
    # still a FileNotFoundError for pre-hub callers
    with pytest.raises(FileNotFoundError):
        resolve_skill_dir("no/such/path/at/all")


def test_official_tiktok_resolves_from_repo_hub(tmp_path, monkeypatch):
    monkeypatch.setenv("GHOST_SKILLS_DIR", str(tmp_path / "empty"))
    s = load_skill("ghost/tiktok")
    assert s.skill_dir == REPO / "skillhub" / "ghost" / "tiktok"
    assert s.author == "ghost" and s.name == "tiktok"


# ── skill-local python imports ──────────────────────────────────────────────

def _ctx_for(skill) -> RunContext:
    ctx = RunContext(action_name="ping")
    ctx.extras["_current_skill_dir"] = str(skill.skill_dir)
    ctx.extras[CTX_SKILL_KEY] = ident_for_skill(skill)
    return ctx


def test_python_action_and_custom_python_import_by_file_path(tmp_path, isolated):
    skill = load_skill(make_skill(tmp_path / "s" / "demo"))
    ctx = _ctx_for(skill)
    dispatch({"python_action": "helpers:ping"}, ctx, None)
    assert ctx.result["pong"] == "1.0.0"
    assert evaluate({"kind": "custom_python", "function": "validators:ok"}, ctx, None) is True
    name = module_name("alice", "demo", "1.0.0", "helpers")
    assert name == "ghost_skill_alice_demo_1_0_0_helpers"
    assert name in sys.modules


def test_two_versions_get_separate_modules(tmp_path, isolated):
    a = load_skill(make_skill(tmp_path / "v1" / "demo", version="1.0.0"))
    b = load_skill(make_skill(tmp_path / "v2" / "demo", version="2.0.0"))
    fa = resolve_for_skill("helpers:ping", a)
    fb = resolve_for_skill("helpers:ping", b)
    assert fa.__module__ != fb.__module__
    assert fa(None, {}, None)["data"]["pong"] == "1.0.0"
    assert fb(None, {}, None)["data"]["pong"] == "2.0.0"


def test_identity_falls_back_to_skill_yaml(tmp_path, isolated):
    skill = load_skill(make_skill(tmp_path / "s2" / "demo", version="3.1.4"))
    ctx = RunContext(action_name="ping")
    ctx.extras["_current_skill_dir"] = str(skill.skill_dir)   # no identity dict
    dispatch({"python_action": "helpers:ping"}, ctx, None)
    assert ctx.result["pong"] == "3.1.4"


@pytest.mark.parametrize("ref,needle", [
    ("gitd.skills.demo.helpers:ping", "not supported in v2"),
    ("..helpers:ping", "inside the skill dir"),
    ("helpers", "<file>:<function>"),
])
def test_bad_refs_rejected(tmp_path, isolated, ref, needle):
    skill = load_skill(make_skill(tmp_path / "s3" / "demo"))
    with pytest.raises(ParamError) as ei:
        resolve_for_skill(ref, skill)
    assert needle in str(ei.value)


def test_tiktok_refs_all_resolve_by_file_path(tmp_path, monkeypatch):
    monkeypatch.setenv("GHOST_SKILLS_DIR", str(tmp_path / "empty"))
    skill = load_skill("ghost/tiktok")
    refs = set()

    def walk(obj):
        if isinstance(obj, dict):
            if "python_action" in obj:
                refs.add(obj["python_action"])
            if obj.get("kind") == "custom_python":
                refs.add(obj["function"])
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)

    for a in skill.actions:
        walk([a.pre_hooks, a.steps, a.end_state_validator])
    for sr in skill.subroutines:
        walk(sr.steps)
    assert refs and all(not r.startswith("gitd.") for r in refs)
    for r in refs:
        assert callable(resolve_for_skill(r, skill))


# ── v1 runtime compat after the move ────────────────────────────────────────

def test_v1_runtime_still_finds_moved_skills():
    import importlib

    from gitd.routers.skills import _load_all_skills

    skills = _load_all_skills()
    for slug in ("tiktok", "google_maps", "safari"):
        assert slug in skills, slug
        assert "skillhub" in skills[slug]["path"]
    assert importlib.import_module("gitd.skills.google_maps").load() is not None


# ── Amendment A schema fields (D6) ──────────────────────────────────────────

def _d6_skill(tmp_path, author="alice", extra="", drop=()):
    d = make_skill(tmp_path / "d6" / author, author=author)
    text = (d / "skill.yaml").read_text()
    for key in drop:
        text = "\n".join(l for l in text.splitlines() if not l.startswith(key + ":")) + "\n"
    (d / "skill.yaml").write_text(text + extra)
    return d


def test_d6_fields_parse(tmp_path):
    from textwrap import dedent
    extra = dedent("""\
        side_effects: [sends_message]
        destructive: false
        tos_risk: medium
        locale: [en-US, de-DE]
        """)
    s = load_skill(_d6_skill(tmp_path, extra=extra))
    assert (s.license, s.generated_with, s.side_effects, s.tos_risk, s.locale) == (
        "MIT", "human", ["sends_message"], "medium", ["en-US", "de-DE"])
    assert s.warnings == []
    assert s.fingerprint.theme == "*"


@pytest.mark.parametrize("drop", [("license",), ("generated_with",)])
def test_d6_required_fields_error_for_community_warn_for_official(tmp_path, drop):
    from gitd.skills.engine.errors import SchemaError
    with pytest.raises(SchemaError):
        load_skill(_d6_skill(tmp_path, drop=drop))
    s = load_skill(_d6_skill(tmp_path, author="ghost", drop=drop))
    assert len(s.warnings) == 1 and drop[0] in s.warnings[0]


@pytest.mark.parametrize("extra", [
    "license_bad: x\nside_effects: [launches_rockets]\n",
    "tos_risk: extreme\n",
    "destructive: maybe\n",
    "locale: [not a locale]\n",
    "fingerprint_extra: 1\n",
])
def test_d6_bad_values_are_errors(tmp_path, extra):
    from gitd.skills.engine.errors import SchemaError
    if extra.startswith("fingerprint_extra"):
        d = _d6_skill(tmp_path)
        y = (d / "skill.yaml").read_text().replace("  app_package: com.example", "  app_package: com.example\n  theme: neon")
        (d / "skill.yaml").write_text(y)
    else:
        d = _d6_skill(tmp_path, extra=extra)
    with pytest.raises(SchemaError):
        load_skill(d)


def test_d6_destructive_needs_gate(tmp_path):
    from gitd.skills.engine.errors import SchemaError
    with pytest.raises(SchemaError, match="confirm_before"):
        load_skill(_d6_skill(tmp_path, extra="destructive: true\n"))
    d = _d6_skill(tmp_path, extra="destructive: true\n")
    y = (d / "skill.yaml").read_text().replace('    ref_prompt: "ping it"', '    ref_prompt: "ping it"\n    confirm_before: "Really ping?"')
    (d / "skill.yaml").write_text(y)
    assert load_skill(d).destructive is True


def test_official_tiktok_warns_until_migrated(tmp_path, monkeypatch):
    monkeypatch.setenv("GHOST_SKILLS_DIR", str(tmp_path / "empty"))
    warnings = load_skill("ghost/tiktok").warnings
    assert any("license" in w for w in warnings) and any("generated_with" in w for w in warnings)
