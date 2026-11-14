"""_run_skill.py launches v2 skills with the SkillRun row bound for checkpoint resume.

The v1 runner records a SkillRun row; for a Schema v2 skill (no v1 load()) it now calls
run_action(..., run_id=row.id), so a `checkpoint:` step reads/writes that row through
engine/hitl.py SkillRunChannel (resume_signal / awaiting_human, the same columns that
POST /api/skills/runs/{id}/resume writes). Fake device + fake DB session, no phone.
"""
import sys

import pytest

import gitd.models.base as models_base
from gitd.skills import _run_skill
from gitd.skills.engine import dispatch as dispatch_mod
from gitd.skills.engine import runner as runner_mod


class FakeDevice:
    serial = "emulator-5554"

    def dump_xml(self):
        return "<hierarchy/>"


class Row:
    def __init__(self):
        self.status = "running"
        self.checkpoint_json = None
        self.resume_signal = None
        self.history = []


class Session:
    def __init__(self, row, run_id):
        self.row, self.run_id = row, run_id

    def get(self, model, run_id):
        return self.row if run_id == self.run_id else None

    def commit(self):
        self.row.history.append(self.row.status)
        if self.row.status == "awaiting_human":
            self.row.resume_signal = "resume"     # a human hits POST /runs/{id}/resume

    def close(self):
        pass


DEMO_LOGIN = """\
name: demo_login
version: 1.0.0
description: Open a login page and hand over to a human at a checkpoint.
platforms: [android]
app_package: com.android.chrome
android_package: com.android.chrome
skill_class: soft
author: ghost
license: MIT
fingerprint: {os: android, os_version: '*', hardware: '*', app_package: com.android.chrome, app_version: '*'}
state_probes:
  logged_in: {kind: element_present, text: Home}
actions:
- name: register
  provides_state: [logged_in]
  description: Open the login page and hand over to a human.
  ref_prompt: Log in to the demo site
  steps:
  - action: open_url
    url: https://example.com/login
  - checkpoint:
      reason: login
      prompt: Log in by hand on the live stream.
      timeout_s: 600
      success: {kind: url_contains, substring: /home}
  end_state_validator: {kind: url_contains, substring: /home}
  test_case:
    ref_prompt_variants: [Log in to the demo site]
    expected_success: true
"""


@pytest.fixture
def harness(monkeypatch, tmp_path):
    skill_dir = tmp_path / "demo_login"
    skill_dir.mkdir()
    (skill_dir / "skill.yaml").write_text(DEMO_LOGIN)
    real_dir = _run_skill._skill_dir
    monkeypatch.setattr(_run_skill, "_skill_dir", lambda name: skill_dir if name == "demo_login" else real_dir(name))
    row, run_id, finished = Row(), 4242, {}
    monkeypatch.setattr(models_base, "SessionLocal", lambda: Session(row, run_id))
    monkeypatch.setattr(_run_skill, "_record_start", lambda *a, **k: run_id)
    monkeypatch.setattr(_run_skill, "_record_finish",
                        lambda rid, ok, dur, err=None: finished.update(run_id=rid, ok=ok, err=err))
    monkeypatch.setattr(_run_skill, "get_device", lambda serial: FakeDevice())
    monkeypatch.setattr(runner_mod, "_get_device", lambda serial: FakeDevice())
    monkeypatch.setitem(dispatch_mod._HANDLERS, "open_url", lambda step, ctx, device: None)
    return row, run_id, finished


def _main(monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["_run_skill.py", *argv])
    with pytest.raises(SystemExit) as ei:
        _run_skill.main()
    return ei.value.code


def test_v2_soft_skill_checkpoint_resumes_through_skill_run_row(monkeypatch, harness):
    row, run_id, finished = harness
    seen = {}
    real = runner_mod.run_action

    def spy(*a, **k):
        seen["run_id"] = k.get("run_id")
        return real(*a, **k)

    monkeypatch.setattr(runner_mod, "run_action", spy)
    from gitd.skills.engine import validators as validators_mod
    monkeypatch.setitem(validators_mod._VALIDATORS, "url_contains", lambda spec, ctx, device: True)   # fake "landed on the home page"
    # demo_login is v2-only: open_url + checkpoint(success: url_contains /home)
    code = _main(monkeypatch, "--skill", "demo_login", "--action", "register", "--device", "emulator-5554")
    assert code == 0, finished
    assert seen["run_id"] == run_id
    assert row.history[:2] == ["awaiting_human", "running"]          # gate published, then resumed
    assert '"reason": "login"' in row.checkpoint_json
    assert finished == {"run_id": run_id, "ok": True, "err": None}


def test_v2_timeout_leaves_row_timed_out(monkeypatch, harness):
    row, run_id, finished = harness
    monkeypatch.setattr(Session, "commit", lambda self: self.row.history.append(self.row.status))
    from gitd.skills.engine.loader import load_skill

    skill = load_skill(_run_skill._skill_dir("demo_login"))
    step = skill.action("register").steps[1]["checkpoint"]
    monkeypatch.setitem(step, "timeout_s", 0.05)
    monkeypatch.setitem(step, "poll_s", 0.01)
    monkeypatch.setattr("gitd.skills.engine.load_skill", lambda path: skill)
    code = _main(monkeypatch, "--skill", "demo_login", "--action", "register", "--device", "emulator-5554")
    assert code == 1
    assert row.status == "timed_out"           # _record_finish keeps timed_out (resumable), never 'fail'
    assert finished["ok"] is False and finished["err"].startswith("CheckpointTimeoutError")


def test_v1_skills_keep_the_v1_path(monkeypatch, harness):
    called = []
    monkeypatch.setattr(_run_skill, "_run_v2", lambda *a, **k: called.append(a) or (True, None))
    # google_maps still has a v1 load(); asking for a missing workflow must not fall through to v2
    code = _main(monkeypatch, "--skill", "google_maps", "--workflow", "nope", "--device", "emulator-5554")
    assert code == 1 and called == []


def test_moved_skills_resolve_from_skillhub():
    assert _run_skill._skill_dir("google_maps").parts[-3:] == ("skillhub", "ghost", "google_maps")
    assert _run_skill._load_skill_metadata("tiktok")["name"] == "tiktok"
    assert _run_skill._v2_declares(_run_skill._skill_dir("tiktok"), "open_inbox")
    assert not _run_skill._v2_declares(_run_skill._skill_dir("tiktok"), "missing")
