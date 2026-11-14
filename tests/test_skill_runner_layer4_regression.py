"""Regression: a failing a11y-reader step must surface StepFailedError, not NameError (xml_before)."""
from gitd.skills.engine import run_action
from gitd.skills.engine.loader import _parse_skill


class _FakeDevice:
    serial = "fake"
    def __init__(self):
        self.xml = "<hierarchy><node text='home' clickable='true' bounds='[0,0][10,10]'/></hierarchy>"
    def dump_xml(self):
        return self.xml
    def dismiss_popups(self, xml=None, popups=None):
        return False
    def adb(self, *a, **k):
        return ""
    def tap(self, x, y):
        pass


def _skill(tmp_path):
    return _parse_skill({
        "name": "l4", "version": "0.1.0", "author": "t", "license": "MIT", "generated_with": "test",
        "skill_class": "hard", "fingerprint": {"os": "android", "app_package": "com.x"},
        "actions": [{
            "name": "a", "ref_prompt": "do a", "params": [],
            "steps": [{"action": "tap_element", "text": "does-not-exist"}],
            "end_state_validator": {"kind": "text_visible", "text": "never"},
            "test_case": {"ref_prompt_variants": ["do a"], "expected_success": True},
        }],
    }, tmp_path)


def test_reader_step_failure_is_typed_not_nameerror(monkeypatch, tmp_path):
    import gitd.skills.engine.runner as runner
    dev = _FakeDevice()
    monkeypatch.setattr(runner, "_fast_dump", lambda d: d.xml)
    monkeypatch.setattr(runner, "_get_device", lambda serial: dev)
    res = run_action(_skill(tmp_path), "a", params={}, device_serial="fake")
    assert res.success is False
    assert res.error is not None
    assert "NameError" not in str(res.error)
    assert res.error.get("kind") in {"StepFailedError", "step_failed", "TimeoutError", "timeout"} or "step" in str(res.error).lower()
