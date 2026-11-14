"""ghost skill import --androidworld: static parse of a tiny android_world fixture. No network, no exec."""
from pathlib import Path
from textwrap import dedent

import pytest
import yaml

from gitd.skills.engine.androidworld import (
    GENERATED_WITH,
    MARKER,
    action_name,
    app_packages,
    import_android_world,
    parse_android_world,
    parse_textproto,
)
from gitd.skills.engine.cli import main as cli_main
from gitd.skills.engine.loader import load_skill

REGISTRY = '''\
from android_world.task_evals.single import clock
from android_world.task_evals.single import recipe

def get_information_retrieval_task_path() -> None:
  return None

class TaskRegistry:
  _TASKS = (
      clock.ClockTimerEntry,
      recipe.RecipeDeleteSingleRecipe,
  )
'''

CLOCK = '''\
import random
from android_world.env import adb_utils
from android_world.task_evals import task_eval
raise RuntimeError("fixture must never be executed")

class _ClockEval(task_eval.TaskEval):
  """Base class for clock tasks."""
  app_names = ("clock",)

class ClockTimerEntry(_ClockEval):
  """Task for checking if timer is set (but not started)."""
  complexity = 1
  schema = {
      "type": "object",
      "properties": {"hours": {"type": "integer"}, "minutes": {"type": "integer"}},
      "required": ["hours", "minutes"],
  }
  template = (
      "Create a timer with {hours} hours and {minutes}"
      " minutes. Do not start the timer."
  )

  def is_successful(self, env) -> float:
    ui_elements = env.get_state().ui_elements
    activity = adb_utils.get_current_activity(env.controller)[0]
    return 1.0 if _is_timer_set(ui_elements, activity) else 0.0
'''

RECIPE = '''\
from android_world.task_evals.common_validators import sqlite_validators
_APP_NAME = 'broccoli app'

class _RecipeDelete(sqlite_validators.SQLiteApp):
  app_names = (_APP_NAME,)
  template = ''

class RecipeDeleteSingleRecipe(_RecipeDelete):
  """Delete one recipe — with noise."""
  complexity = 2.5

  @property
  def goal(self) -> str:
    titles = ', '.join(self.params['rows'])
    return f'Delete the following recipes from {_APP_NAME}: {titles}.'

  def is_successful(self, env) -> float:
    return sqlite_validators.verify_rows_deleted(env, self.db_path)
'''

TEXTPROTO = '''\
# information retrieval fixture
tasks {
  name: "SimpleCalendarEventsOnDate"
  prompt: "What events do I have {date} in Simple Calendar Pro? Answer with the titles only."
  complexity: 1
  relevant_state {
    state: { calendar { app_name: "simple calendar pro" events { title: "{title}" } } }
  }
  success_criteria {
    expectations {
      field_transformation { operation: IDENTITY field_name: "title" }
      match_type: STRING_MATCH
    }
  }
  task_params { name: "date" possible_values: "October 15 2023" }
}
'''

ADB_UTILS = '''\
import immutabledict
_PATTERN_TO_ACTIVITY = immutabledict.immutabledict({
    'clock|deskclock': 'com.google.android.deskclock/com.android.deskclock.DeskClock',
    'broccoli app|broccoli': 'com.flauschcode.broccoli/.MainActivity',
    'simple calendar pro|calendar': 'com.simplemobiletools.calendar.pro/.activities.MainActivity',
})
'''


@pytest.fixture
def checkout(tmp_path) -> Path:
    root = tmp_path / "android_world_checkout"
    files = {
        "android_world/registry.py": REGISTRY,
        "android_world/task_evals/single/clock.py": CLOCK,
        "android_world/task_evals/single/recipe.py": RECIPE,
        "android_world/task_evals/information_retrieval/proto/tasks.textproto": TEXTPROTO,
        "android_world/env/adb_utils.py": ADB_UTILS,
        "LICENSE": "Apache License\nVersion 2.0, January 2004\n",
    }
    for rel, text in files.items():
        f = root / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(dedent(text))
    return root


def test_parse_static_tasks_and_ir(checkout):
    tasks = {t.name: t for t in parse_android_world(checkout)}
    assert set(tasks) == {"ClockTimerEntry", "RecipeDeleteSingleRecipe", "SimpleCalendarEventsOnDate"}

    clock = tasks["ClockTimerEntry"]
    assert clock.apps == ["clock"] and clock.complexity == 1 and clock.family == "android"
    assert clock.template == "Create a timer with {hours} hours and {minutes} minutes. Do not start the timer."
    assert clock.params == [{"name": "hours", "type": "int", "required": True},
                            {"name": "minutes", "type": "int", "required": True}]
    assert clock.evaluator_ref.endswith("clock.py:23")
    assert "the UI tree" in clock.evaluator and "adb_utils.get_current_activity" in clock.calls

    recipe = tasks["RecipeDeleteSingleRecipe"]
    assert recipe.apps == ["broccoli app"]                      # module constant resolved through the base
    assert recipe.template == "Delete the following recipes from broccoli app: {titles}."
    assert [p["name"] for p in recipe.params] == ["titles"]
    assert any("goal property" in n for n in recipe.notes)
    assert "the app's SQLite database" in recipe.evaluator

    ir = tasks["SimpleCalendarEventsOnDate"]
    assert ir.family == "information_retrieval" and ir.apps == ["simple calendar pro"]
    assert [p["name"] for p in ir.params] == ["date"]
    assert "title" in ir.evaluator and "STRING_MATCH" in ir.evaluator


def test_textproto_reader_and_packages(checkout):
    tree = parse_textproto('a: "x" b { c: 1 d { e: "y\\"z" } } # comment\nf: ENUM')
    assert tree == [("a", "x"), ("b", [("c", "1"), ("d", [("e", 'y"z')])]), ("f", "ENUM")]
    pk = app_packages(checkout)
    assert pk["clock"] == "com.google.android.deskclock" and pk["broccoli"] == "com.flauschcode.broccoli"
    assert action_name("ClockTimerEntry") == "clock_timer_entry"
    assert action_name("SaveCopyOfReceiptTaskEval") == "save_copy_of_receipt_task_eval"


def test_import_writes_valid_draft_skills(checkout, tmp_path, capsys):
    out = tmp_path / "skillhub" / "androidworld"
    results = import_android_world(checkout, out)
    assert {r["slug"] for r in results} == {"clock", "broccoli-app",
                                            "simple-calendar-pro"}
    d = out / "clock"
    assert {p.name for p in d.iterdir()} == {"skill.yaml", "validators.py", "SOFT.md", "README.md", "LICENSE"}
    text = (d / "skill.yaml").read_text()
    assert MARKER in text and "Apache License 2.0" in text
    raw = yaml.safe_load(text)
    assert (raw["status"], raw["license"], raw["generated_with"]) == ("draft", "Apache-2.0", GENERATED_WITH)
    assert raw["fingerprint"]["app_package"] == "com.google.android.deskclock"
    assert raw["source"]["upstream"].endswith("google-research/android_world")

    skill = load_skill(d)
    a = skill.action("clock_timer_entry")
    assert a.ref_prompt.startswith("Create a timer with {hours} hours")
    assert a.end_state_validator == {"kind": "custom_python", "function": "validators:clock_timer_entry"}
    assert a.steps[0]["action"] == "launch_app" and a.steps[0]["note"].startswith("TODO imported node:")
    assert a.test_case["ref_prompt_variants"] == [a.ref_prompt]
    assert "clock.py:23" in (d / "validators.py").read_text()
    assert "### `clock_timer_entry(hours, minutes)`" in (d / "SOFT.md").read_text()
    assert "Attribution" in (d / "README.md").read_text() and (d / "LICENSE").read_text().startswith("Apache")

    rec = yaml.safe_load((out / "broccoli-app" / "skill.yaml").read_text())
    assert rec["side_effects"] == ["deletes_data"]
    assert "—" not in (out / "broccoli-app" / "skill.yaml").read_text()

    for r in results:
        assert cli_main(["validate", r["path"]]) == 0
        capsys.readouterr()
        assert cli_main(["lint", r["path"]]) == 0
        lint = capsys.readouterr().out
        assert "0 error(s)" in lint
        # fixture skills have no icon.webp (icons are fetched separately by tools/fetch_app_icons.py)
        assert all("TODO imported node" in line or "No app icon" in line or "no demo clip" in line
                   for line in lint.splitlines() if "⚠" in line)

    # the stub validator never passes until ported
    from gitd.skills.engine.context import RunContext
    from gitd.skills.engine.pyimport import resolve_for_skill
    ctx = RunContext(action_name="clock_timer_entry", params={"hours": 1, "minutes": 2})
    assert resolve_for_skill("validators:clock_timer_entry", skill, what="custom_python")(None, ctx) is False


def test_reimport_is_idempotent_and_respects_hand_edits(checkout, tmp_path):
    out = tmp_path / "skills"
    import_android_world(checkout, out)
    before = {p: p.read_bytes() for p in out.rglob("*") if p.is_file()}
    import_android_world(checkout, out)
    assert {p: p.read_bytes() for p in out.rglob("*") if p.is_file()} == before
    hand = out / "clock" / "skill.yaml"
    hand.write_text(hand.read_text().replace(MARKER, "hand edited"))
    res = {r["slug"]: r["status"] for r in import_android_world(checkout, out)}
    assert res["clock"] == "skipped: hand-edited"
    assert "hand edited" in hand.read_text()


def test_cli_import_androidworld(checkout, tmp_path, capsys):
    out = tmp_path / "cli_out"
    assert cli_main(["import", "--androidworld", str(checkout), "--out", str(out)]) == 0
    assert "3 task(s) in 3 draft skill(s)" in capsys.readouterr().out
    assert (out / "simple-calendar-pro" / "validators.py").is_file()


def test_not_a_checkout(tmp_path):
    with pytest.raises(ValueError, match="registry.py not found"):
        parse_android_world(tmp_path)
