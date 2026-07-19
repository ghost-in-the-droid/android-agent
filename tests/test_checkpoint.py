"""C2: checkpoint poll loop + auto-detect + engine dispatch (device/DB-free)."""

from unittest.mock import MagicMock

from gitd.skills.base import RecordedStepAction
from gitd.skills.checkpoint import run_checkpoint, screen_condition_met


class _Clock:
    """Deterministic clock: advances by `step` each sleep()."""

    def __init__(self, step=1.0):
        self.t = 0.0
        self.step = step

    def now(self):
        return self.t

    def sleep(self, _):
        self.t += self.step


def _signals(*seq):
    it = iter(seq)
    return lambda: next(it, None)


def _run(**over):
    states = []
    kw = dict(
        reason="captcha", prompt="solve it", success=None, timeout_s=600,
        read_signal=lambda: None,
        check_success=lambda s: False,
        set_state=lambda status, cp: states.append(status),
        notify=lambda r, p: None,
        now=_Clock().now, sleep=lambda _: None,
    )
    kw.update(over)
    outcome = run_checkpoint(**kw)
    return outcome, states


def test_human_resume():
    outcome, states = _run(read_signal=_signals(None, "resume"))
    assert outcome.resolved and outcome.resolution == "human"
    assert states[0] == "awaiting_human" and states[-1] == "running"


def test_human_abort():
    outcome, states = _run(read_signal=_signals(None, "abort"))
    assert not outcome.resolved and outcome.resolution == "aborted"
    assert states[-1] == "aborted"


def test_auto_detect():
    hits = iter([False, True])
    outcome, states = _run(success={"url_contains": "/inbox"}, check_success=lambda s: next(hits))
    assert outcome.resolved and outcome.resolution == "auto"
    assert states[-1] == "running"


def test_timeout():
    clk = _Clock(step=300)  # each sleep advances 300s → crosses 600 on 2nd loop
    outcome, states = _run(timeout_s=600, now=clk.now, sleep=clk.sleep)
    assert not outcome.resolved and outcome.resolution == "timed_out"
    assert states[-1] == "timed_out"
    assert "timed_out after 600" in outcome.error


def test_manual_override_beats_auto():
    # both fire the same cycle — manual (checked first) wins
    outcome, _ = _run(read_signal=_signals("resume"), success={"screen_has": "x"}, check_success=lambda s: True)
    assert outcome.resolution == "human"


def test_indefinite_timeout_never_expires():
    clk = _Clock(step=100000)
    outcome, _ = _run(timeout_s=0, now=clk.now, sleep=clk.sleep, read_signal=_signals(None, None, "resume"))
    assert outcome.resolved and outcome.resolution == "human"


def test_invalid_reason_normalized_to_generic():
    outcome, _ = _run(reason="banana", read_signal=_signals("resume"))
    assert outcome.data["checkpoint"] == "generic"


# ── screen_condition_met ──────────────────────────────────────────────

def test_screen_has_matches_ui_tree():
    dev = MagicMock()
    dev.dump_xml.return_value = "<node text='Welcome to your Inbox'/>"
    assert screen_condition_met(dev, {"screen_has": "inbox"}) is True
    assert screen_condition_met(dev, {"screen_has": "nope"}) is False


def test_url_contains_falls_back_to_ui_tree():
    dev = MagicMock()
    dev.serial = "d"
    dev.dump_xml.return_value = "<node text='https://mail.proton.me/u/0/inbox'/>"
    # get_current_url will fail/return nothing in test → falls back to the tree
    assert screen_condition_met(dev, {"url_contains": "/inbox"}) is True


# ── engine dispatch ───────────────────────────────────────────────────

def test_engine_skips_checkpoint_without_run_or_success():
    # No run_id to signal + no auto-detect → cannot gate on a human; skip vs hang.
    dev = MagicMock()
    act = RecordedStepAction(dev, {"action": "checkpoint", "reason": "sms"}, 0, run_id=None)
    res = act.execute()
    assert res.success and res.data["resolution"] == "skipped"
