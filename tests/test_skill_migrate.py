"""ghost skill migrate: v1 -> Schema v2 in place (gitd/skills/engine/migrate.py). No phone."""
import json
import sys
from pathlib import Path
from textwrap import dedent

import pytest
import yaml

from gitd.skills.engine.cli import main as cli_main
from gitd.skills.engine.context import RunContext
from gitd.skills.engine.dispatch import dispatch
from gitd.skills.engine.loader import load_skill
from gitd.skills.engine.migrate import BEGIN, migrate_skill
from gitd.skills.engine.pyimport import CTX_SKILL_KEY, ident_for_skill
from gitd.skills.engine.validators import evaluate

REPO = Path(__file__).resolve().parents[1]


class FakeDevice:
    serial = "fake-serial"


def make_v1_python(root: Path, slug: str) -> Path:
    d = root / "skillhub" / "ghost" / slug
    (d / "actions").mkdir(parents=True)
    (d / "skill.yaml").write_text(dedent(f"""\
        # v1 comment that must survive
        name: {slug}
        version: 1.2.0
        description: Demo v1 skill
        platforms:
          - android
        app_package: com.example.demo
        android_package: com.example.demo
        exports:
          actions: [open_app, greet, greet_loud, report]
          workflows: [report, missing_flow]
        """))
    (d / "__init__.py").write_text(dedent("""\
        from pathlib import Path
        from gitd.skills.base import Skill
        from .actions.core import OpenApp, Greet, GreetLoud, Report


        def load():
            s = Skill(Path(__file__).parent)
            for cls in (OpenApp, Greet, GreetLoud, Report):
                s.register_action(cls)
            from .workflows import ReportFlow
            s.register_workflow(ReportFlow)
            return s
        """))
    (d / "actions" / "__init__.py").write_text("")
    (d / "actions" / "core.py").write_text(dedent('''\
        from gitd.skills.base import Action, ActionResult


        class OpenApp(Action):
            """Open the demo app. Second sentence is dropped."""
            name = "open_app"
            description = "Open the app"

            def execute(self):
                return ActionResult(success=True, data={"opened": True})


        class Greet(Action):
            """Say hello to someone."""
            name = "greet"

            def __init__(self, device, elements=None, *, who: str = "", times: int = 1, loud=False, **kw):
                super().__init__(device, elements)
                self.who, self.times, self.loud = who, times, loud

            def execute(self):
                text = ("HELLO " if self.loud else "hello ") + self.who
                return ActionResult(success=bool(self.who), data={"text": text * self.times},
                                    error="" if self.who else "who required")


        class GreetLoud(Greet):
            """Shout hello."""
            name = "greet_loud"


        class Report(Action):
            """Report an action-level status."""
            name = "report"

            def execute(self):
                return ActionResult(success=True, data={"kind": "action"})
        '''))
    (d / "workflows.py").write_text(dedent('''\
        from gitd.skills.base import ActionResult, Workflow


        class ReportFlow(Workflow):
            """Run the full report flow."""
            name = "report"

            def __init__(self, device, elements=None, target: str | None = None, **kw):
                super().__init__(device, elements)
                self.target = target

            def run(self):
                return ActionResult(success=True, data={"kind": "workflow", "target": self.target})
        '''))
    return d


def _ctx(skill, params=None):
    ctx = RunContext(action_name="x", params=params or {})
    ctx.extras["_current_skill_dir"] = str(skill.skill_dir)
    ctx.extras[CTX_SKILL_KEY] = ident_for_skill(skill)
    return ctx


def test_python_v1_skill_migrates_and_runs(tmp_path):
    slug = "migfixture_py"
    d = make_v1_python(tmp_path, slug)
    r = migrate_skill(d)
    assert r.status == "migrated", r.reason
    assert r.actions == ["report", "open_app", "greet", "greet_loud", "report_action"]
    assert r.skipped == ["workflow:missing_flow"]

    text = (d / "skill.yaml").read_text()
    assert text.startswith("# v1 comment that must survive") and BEGIN in text
    assert "&id" not in text and "*id" not in text
    raw = yaml.safe_load(text)
    assert raw["exports"]["actions"][0] == "open_app"          # v1 keys kept for the v1 runtime

    skill = load_skill(d)
    assert (skill.author, skill.license, skill.generated_with, skill.skill_class) == (
        "ghost", "MIT", "ghost skill migrate", "hard")
    assert skill.fingerprint.app_package == "com.example.demo" and skill.fingerprint.os == "android"
    assert skill.warnings == []
    greet = skill.action("greet")
    assert greet.ref_prompt == "Say hello to someone"
    assert [(p.name, p.type, p.required, p.default) for p in greet.params] == [
        ("who", "str", False, None), ("times", "int", False, 1), ("loud", "bool", False, False)]
    assert [p.name for p in skill.action("greet_loud").params] == ["who", "times", "loud"]   # inherited __init__
    assert skill.action("open_app").ref_prompt == "Open the demo app"
    assert skill.action("report").steps == [{"python_action": "helpers:run_report"}]
    assert skill.action("report").test_case["ref_prompt_variants"] == ["Run the full report flow"]

    # adapters run the v1 classes (package imported from the skill dir by file path)
    sys.modules.pop(f"gitd.skills.{slug}", None)
    ctx = _ctx(skill, {"who": "ann", "times": 2})
    dispatch({"python_action": "helpers:run_greet"}, ctx, FakeDevice())
    assert ctx.result["text"] == "hello annhello ann" and ctx.result["v1_ok"] is True
    assert evaluate(skill.action("greet").end_state_validator, ctx, None) is True

    ctx = _ctx(skill, {"target": "t1"})
    dispatch({"python_action": "helpers:run_report"}, ctx, FakeDevice())
    assert ctx.result["kind"] == "workflow" and ctx.result["target"] == "t1"
    ctx = _ctx(skill)
    dispatch({"python_action": "helpers:run_report_action"}, ctx, FakeDevice())
    assert ctx.result["kind"] == "action"

    from gitd.skills.engine.errors import StepFailedError
    with pytest.raises(StepFailedError):
        dispatch({"python_action": "helpers:run_greet"}, _ctx(skill), FakeDevice())   # v1 failure surfaces


def test_migrate_is_idempotent_and_keeps_v2_skills(tmp_path):
    d = make_v1_python(tmp_path, "migfixture_idem")
    migrate_skill(d)
    before = {p.name: p.read_text() for p in d.iterdir() if p.is_file()}
    assert migrate_skill(d).status == "migrated"
    assert {p.name: p.read_text() for p in d.iterdir() if p.is_file()} == before
    tt = migrate_skill(REPO / "skillhub" / "ghost" / "tiktok", dry_run=True)
    assert tt.status == "already_v2"


def test_recorded_skill_migrates(tmp_path):
    d = tmp_path / "skillhub" / "ghost" / "rec_demo"
    (d / "workflows").mkdir(parents=True)
    (d / "skill.yaml").write_text(dedent("""\
        name: rec_demo
        version: 1.0.0
        description: Auto-generated skill from 2 recorded steps
        platforms: [android]
        app_package: com.example.mail
        default_params:
          workflows:
            recorded:
              subject: Hi
        """))
    (d / "workflows" / "recorded.json").write_text(json.dumps([{"action": "launch", "package": "com.example.mail"}]))
    r = migrate_skill(d)
    assert r.status == "migrated" and r.actions == ["recorded"]
    a = load_skill(d).action("recorded")
    assert [(p.name, p.required) for p in a.params] == [("subject", True)]
    assert "RecordedWorkflow" in (d / "helpers.py").read_text()


def test_flow_md_soft_skill_migrates(tmp_path):
    d = tmp_path / "skillhub" / "ghost" / "signup_demo"
    d.mkdir(parents=True)
    (d / "skill.yaml").write_text(dedent("""\
        name: signup_demo
        version: 0.1.0
        description: Register a demo account. SOFT SKILL.
        platforms: [android]
        app_package: com.android.chrome
        skill_class: soft
        entry_url: https://example.com/signup
        checkpoints:
          - reason: sms
            prompt: "Enter the code"
            success:
              screen_has: "Welcome"
        """))
    (d / "FLOW.md").write_text("# signup_demo\n\nExplored on a test phone. Needs a real number.\n\n| a | b |\n")
    r = migrate_skill(d)
    assert r.status == "migrated" and r.actions == ["signup"]
    s = load_skill(d)
    assert s.skill_class == "soft" and not (d / "helpers.py").exists()
    a = s.action("signup")
    assert a.steps[0] == {"action": "open_url", "url": "https://example.com/signup"}
    cp = a.steps[1]["checkpoint"]
    assert cp["reason"] == "login" and "Needs a real number" in cp["prompt"]
    assert cp["success"] == {"kind": "text_visible", "text": "Welcome"} == a.end_state_validator
    assert a.ref_prompt == "Register a demo account"


def test_unwrappable_skill_is_legacy_and_untouched(tmp_path):
    d = tmp_path / "skillhub" / "ghost" / "bare"
    d.mkdir(parents=True)
    (d / "skill.yaml").write_text("name: bare\nversion: 1.0.0\napp_package: com.x\n")
    before = (d / "skill.yaml").read_text()
    r = migrate_skill(d)
    assert r.status == "legacy" and "FLOW.md" in r.reason
    assert (d / "skill.yaml").read_text() == before
    other = tmp_path / "elsewhere" / "noauthor"
    make_v1_python(tmp_path / "x", "noauthor").rename(other.parent.mkdir(parents=True) or other)
    assert migrate_skill(other).status == "legacy"                       # author unknown
    assert migrate_skill(other, author="alice", dry_run=True).status == "migrated"


def test_cli_migrate(tmp_path, capsys):
    d = make_v1_python(tmp_path, "migfixture_cli")
    assert cli_main(["migrate", str(d), "--dry-run"]) == 0
    assert BEGIN not in (d / "skill.yaml").read_text()
    assert cli_main(["migrate", str(d)]) == 0
    assert "missing_flow" in capsys.readouterr().out
    assert cli_main(["validate", str(d)]) == 0
    bare = tmp_path / "skillhub" / "ghost" / "bare"
    bare.mkdir()
    (bare / "skill.yaml").write_text("name: bare\nversion: 1.0.0\n")
    assert cli_main(["migrate", str(bare)]) == 1


@pytest.mark.parametrize("slug", ["google_maps", "play_store", "safari", "send_gmail_email", "tiktok_ios",
                                  "tiktok"])
def test_all_official_skills_validate(slug):
    assert cli_main(["validate", str(REPO / "skillhub" / "ghost" / slug)]) == 0


# ── SOFT.md generation (B3) ─────────────────────────────────────────────────

def test_soft_md_generated_per_action_and_lint_clean(tmp_path, capsys):
    from gitd.skills.engine.migrate import SOFT_MARK
    d = make_v1_python(tmp_path, "migfixture_soft")
    (d / "elements.yaml").write_text("search_box:\n  resource_id: com.example:id/search\n")
    r = migrate_skill(d)
    assert d / "SOFT.md" in r.written
    soft = (d / "SOFT.md").read_text()
    assert soft.startswith("---\n" + SOFT_MARK + "\n")
    for name in r.actions:
        assert f"### `{name}(" in soft
    assert "`Greet` in `actions/core.py`" in soft and "Say hello to someone." in soft
    assert "- `times` (int, default `1`)" in soft
    assert "`search_box`: resource_id=`com.example:id/search`" in soft
    assert "—" not in soft
    capsys.readouterr()
    assert cli_main(["lint", str(d)]) == 0
    out = capsys.readouterr().out
    assert "missing SOFT.md section" not in out
    assert "No app icon" in out                                # fixture has no icon.webp
    assert f"0 error(s), {1 + len(r.actions)} warning(s)" in out   # + one 'no demo clip' per action


def test_hand_written_soft_md_is_kept(tmp_path):
    d = make_v1_python(tmp_path, "migfixture_handsoft")
    (d / "SOFT.md").write_text("# hand written\n")
    r = migrate_skill(d)
    assert (d / "SOFT.md").read_text() == "# hand written\n" and d / "SOFT.md" not in r.written


def test_flow_md_embedded_in_soft_md(tmp_path):
    d = tmp_path / "skillhub" / "ghost" / "signup_md"
    d.mkdir(parents=True)
    (d / "skill.yaml").write_text(
        "name: signup_md\nversion: 0.1.0\ndescription: Register — demo\nplatforms: [android]\n"
        "app_package: com.android.chrome\nskill_class: soft\nentry_url: https://example.com/s\n"
        "checkpoints:\n  - reason: sms\n    success: {url_contains: /done}\n")
    (d / "FLOW.md").write_text("# signup_md\n\nIntro line.\n\n## Steps\n\n| # | step |\n|---|---|\n| — | upsell |\n")
    assert migrate_skill(d).status == "migrated"
    soft = (d / "SOFT.md").read_text()
    assert "## Flow (from FLOW.md)" in soft and "### Steps" in soft and "| - | upsell |" in soft
    assert "Register: demo" in soft and '"substring": "/done"' in soft and "—" not in soft


@pytest.mark.parametrize("slug", ["google_maps", "play_store", "safari", "send_gmail_email", "tiktok_ios",
                                  "tiktok"])
def test_official_skills_lint_without_warnings(slug, capsys):
    d = REPO / "skillhub" / "ghost" / slug
    assert cli_main(["lint", str(d)]) == 0
    out = capsys.readouterr().out
    # acceptable warnings: a missing app icon (app not on Play / F-Droid) and actions without a demos/ clip
    skill = load_skill(d)
    expected = (0 if (d / "icon.webp").is_file() else 1) + sum(a.name not in skill.demos for a in skill.actions)
    assert f"0 error(s), {expected} warning(s)" in out
