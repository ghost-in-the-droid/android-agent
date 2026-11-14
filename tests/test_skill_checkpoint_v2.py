"""v2 `checkpoint:` step (dispatch + runner + engine/hitl.py). Fake device, no phone, no DB."""
import threading
import time
from pathlib import Path
from textwrap import dedent

import pytest

from gitd.skills.engine import hitl, load_skill, run_action
from gitd.skills.engine import runner as runner_mod
from gitd.skills.engine.context import RunContext
from gitd.skills.engine.dispatch import dispatch
from gitd.skills.engine.errors import CheckpointTimeoutError, ParamError


class FakeDevice:
    serial = "fake-serial"

    def dump_xml(self):
        return "<hierarchy/>"


def make_skill(tmp_path: Path, checkpoint: str, helpers: str = "") -> Path:
    d = tmp_path / "skillhub" / "alice" / "gate"
    d.mkdir(parents=True, exist_ok=True)
    (d / "skill.yaml").write_text(dedent("""\
        name: gate
        version: 1.0.0
        author: alice
        license: MIT
        generated_with: human
        skill_class: soft
        fingerprint: {os: android, app_package: com.example}
        actions:
          - name: go
            ref_prompt: "pass the gate"
            steps:
              - {action: open_url, url: "https://example.com/{who}"}
              - checkpoint: %s
            params:
              - {name: who, type: str, default: me}
            end_state_validator: {kind: custom_python, function: "helpers:always"}
        """) % checkpoint)
    (d / "helpers.py").write_text("def always(device, context):\n    return True\n" + helpers)
    return d


@pytest.fixture
def fake_device(monkeypatch):
    dev = FakeDevice()
    monkeypatch.setattr(runner_mod, "_get_device", lambda serial: dev)
    from gitd.skills.engine import dispatch as dispatch_mod
    monkeypatch.setitem(dispatch_mod._HANDLERS, "open_url", lambda step, ctx, device: None)
    return dev


PREMIUM_SKILLS = Path(__file__).resolve().parents[1] / "premium" / "skills" / "ghost"


@pytest.mark.skipif(not PREMIUM_SKILLS.is_dir(), reason="premium skills are not part of the public tree")
@pytest.mark.parametrize("slug", ["proton_signup", "x_signup", "gmx_signup"])
def test_soft_signup_skills_run_in_dry_mode(slug):
    skill = load_skill(PREMIUM_SKILLS / slug)
    r = run_action(skill, skill.actions[0].name, dry_run=True)
    assert r.success, r.error
    assert r.data["dry_run"] is True
    assert [c["resolution"] for c in r.data["checkpoints"]] == ["dry_run"]
    notes = [t.note for t in r.trace]
    assert notes[0] == "dry run: skipped (needs a device)"
    assert notes[1].startswith("checkpoint login: dry run")
    assert r.as_dict()["trace"][1]["note"] == notes[1]


def test_human_resume_via_local_channel(tmp_path, fake_device):
    skill = load_skill(make_skill(tmp_path, '{reason: captcha, prompt: "solve it", timeout_s: 5, poll_s: 0.01}'))
    ch = hitl.LocalChannel(echo=False)
    threading.Timer(0.05, ch.resume).start()
    r = run_action(skill, "go", device_serial="x", checkpoint_channel=ch)
    assert r.success, r.error
    assert r.data["checkpoints"] == [{"reason": "captcha", "prompt": "solve it", "timeout_s": 5, "resolution": "human"}]
    assert ch.notices == [("captcha", "solve it")]
    assert [s for s, _ in ch.states] == ["awaiting_human", "running"]
    assert ch.states[0][1]["prompt"] == "solve it"
    assert r.trace[1].note == "checkpoint captcha: resolved (human)"


def test_success_validator_resumes_automatically(tmp_path, fake_device):
    helpers = "CALLS = []\n\ndef cleared(device, context):\n    CALLS.append(1)\n    return len(CALLS) >= 3\n"
    skill = load_skill(make_skill(
        tmp_path, '{reason: sms, prompt: code, timeout_s: 5, poll_s: 0.01, '
                  'success: {kind: custom_python, function: "helpers:cleared"}}', helpers))
    ch = hitl.LocalChannel(echo=False)
    r = run_action(skill, "go", device_serial="x", checkpoint_channel=ch)
    assert r.success, r.error
    assert r.data["checkpoints"][0]["resolution"] == "auto"


def test_abort_is_typed(tmp_path, fake_device):
    skill = load_skill(make_skill(tmp_path, '{reason: login, prompt: p, timeout_s: 5, poll_s: 0.01}'))
    ch = hitl.LocalChannel(echo=False)
    ch.abort()
    r = run_action(skill, "go", device_serial="x", checkpoint_channel=ch)
    assert not r.success and r.error["kind"] == "CheckpointAbortedError"
    assert r.error["step_index"] == 1 and r.error["payload"]["resolution"] == "aborted"
    assert ch.states[-1][0] == "aborted"


def test_timeout_raises_checkpoint_timeout_error(tmp_path, fake_device):
    skill = load_skill(make_skill(tmp_path, '{reason: email, prompt: "enter code", timeout_s: 0.05, poll_s: 0.01}'))
    ch = hitl.LocalChannel(echo=False)
    r = run_action(skill, "go", device_serial="x", checkpoint_channel=ch)
    assert not r.success
    err = r.error
    assert err["kind"] == "CheckpointTimeoutError"
    assert err["payload"] == {"reason": "email", "prompt": "enter code", "timeout_s": 0.05, "resolution": "timed_out"}
    assert "timeout_s" in err["hint"]
    assert ch.states[-1][0] == "timed_out"
    assert r.trace[-1].error and r.trace[-1].note.startswith("checkpoint email: checkpoint timed_out")


def test_timeout_zero_waits_indefinitely(tmp_path, fake_device):
    skill = load_skill(make_skill(tmp_path, '{reason: generic, prompt: p, timeout_s: 0, poll_s: 0.01}'))
    ch = hitl.LocalChannel(echo=False)
    threading.Timer(0.3, ch.resume).start()          # well past any short timeout
    t0 = time.monotonic()
    r = run_action(skill, "go", device_serial="x", checkpoint_channel=ch)
    assert r.success and time.monotonic() - t0 >= 0.25
    assert r.data["checkpoints"][0]["resolution"] == "human"


def test_no_channel_no_success_is_skipped(tmp_path, fake_device):
    skill = load_skill(make_skill(tmp_path, '{reason: login, prompt: p}'))
    r = run_action(skill, "go", device_serial="x")
    assert r.success and r.data["checkpoints"][0]["resolution"] == "skipped"


def test_bad_spec_is_param_error():
    with pytest.raises(ParamError):
        dispatch({"checkpoint": "nope"}, RunContext(action_name="a"), FakeDevice())


def test_timeout_error_as_dict():
    e = CheckpointTimeoutError("t", payload={"reason": "sms"}, hint="h")
    d = e.as_dict()
    assert d["kind"] == "CheckpointTimeoutError" and d["payload"] == {"reason": "sms"} and d["hint"] == "h"


# ── SkillRunChannel: shaped like origin/main RecordedStepAction._run_checkpoint ──

class _Row:
    status = "running"
    checkpoint_json = None
    resume_signal = "resume"


class _Session:
    def __init__(self, row):
        self.row, self.committed, self.closed = row, False, False

    def get(self, model, run_id):
        return self.row if run_id == 7 else None

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True


def test_skill_run_channel_reads_and_writes_run_row(monkeypatch):
    import gitd.models.base as models_base

    row = _Row()
    sessions = []
    monkeypatch.setattr(models_base, "SessionLocal", lambda: sessions.append(_Session(row)) or sessions[-1])
    ch = hitl.SkillRunChannel(7)
    assert ch.read_signal() == "resume"
    ch.set_state("awaiting_human", {"reason": "sms", "prompt": "p"})
    assert row.status == "awaiting_human" and row.resume_signal is None
    assert '"reason": "sms"' in row.checkpoint_json
    ch.set_state("timed_out", None)
    assert row.status == "timed_out"
    assert all(s.closed for s in sessions)
    assert hitl.SkillRunChannel(8).read_signal() is None


def test_run_id_selects_skill_run_channel(tmp_path, fake_device, monkeypatch):
    seen = {}

    class Recorder(hitl.SkillRunChannel):
        def read_signal(self):
            seen["run_id"] = self.run_id
            return "resume"

        def set_state(self, status, checkpoint):
            seen.setdefault("states", []).append(status)

        def notify(self, reason, prompt):
            seen["notified"] = reason

    monkeypatch.setattr(hitl, "SkillRunChannel", Recorder)
    skill = load_skill(make_skill(tmp_path, '{reason: captcha, prompt: p, timeout_s: 5, poll_s: 0.01}'))
    r = run_action(skill, "go", device_serial="x", run_id=42)
    assert r.success, r.error
    assert seen == {"run_id": 42, "states": ["awaiting_human", "running"], "notified": "captcha"}


@pytest.mark.parametrize("spec", ['{reason: banana, prompt: p}', '{reason: sms, timeout_s: -1}',
                                  '{reason: sms, timeout_s: soon}', '{reason: sms, success: yes}'])
def test_loader_rejects_bad_checkpoint_steps(tmp_path, spec):
    from gitd.skills.engine.errors import SchemaError
    with pytest.raises(SchemaError, match="checkpoint"):
        load_skill(make_skill(tmp_path, spec))
