"""Engine core behaviour that the mutation pass (tools/mutants.py) found untested.

Covers validator composition and leaf kinds, runner param resolution, the
end_state_validator gate, and the Layer-4 unknown-popup retry.
"""
import pytest

import gitd.skills.engine.pyimport as pyimport
import gitd.skills.engine.runner as runner
from gitd.skills.engine import run_action
from gitd.skills.engine.context import RunContext
from gitd.skills.engine.errors import ParamError, StepFailedError
from gitd.skills.engine.loader import Param, _parse_skill
from gitd.skills.engine.validators import evaluate

XML = (
    '<hierarchy>'
    '<node text="Inbox" content-desc="Inbox tab" resource-id="com.x:id/inbox" bounds="[0,0][10,10]"/>'
    '</hierarchy>'
)


class _Dev:
    serial = "stub"

    def __init__(self, xml=XML):
        self.xml = xml

    def dump_xml(self):
        return self.xml

    def dismiss_popups(self, xml=None, popups=None):
        return False


def _ev(spec, dev=None):
    return evaluate(spec, RunContext(action_name="a"), dev or _Dev())


TRUE = {"kind": "text_visible", "text": "Inbox"}
FALSE = {"kind": "text_visible", "text": "Outbox"}


# ── validators ──────────────────────────────────────────────────────────────

def test_text_visible_substring():
    assert _ev(TRUE) is True
    assert _ev(FALSE) is False


def test_element_present_by_desc_and_id():
    assert _ev({"kind": "element_present", "desc": "Inbox tab"}) is True
    assert _ev({"kind": "element_present", "desc": "Settings"}) is False
    assert _ev({"kind": "element_present", "id": "com.x:id/inbox"}) is True


def test_not_negates():
    assert _ev({"not": TRUE}) is False
    assert _ev({"not": FALSE}) is True


def test_any_of_is_or():
    assert _ev({"any_of": [FALSE, TRUE]}) is True
    assert _ev({"any_of": [FALSE, FALSE]}) is False


def test_all_of_is_and():
    assert _ev({"all_of": [TRUE, FALSE]}) is False
    assert _ev({"all_of": [TRUE, TRUE]}) is True
    assert _ev([TRUE, FALSE]) is False   # bare list = all_of


def test_empty_spec_passes():
    assert _ev(None) is True


def test_custom_python_result_is_respected(monkeypatch):
    monkeypatch.setattr(pyimport, "identity_from_ctx", lambda ctx: None)
    monkeypatch.setattr(pyimport, "resolve_callable", lambda ref, ident, what: (lambda device, ctx: False))
    assert _ev({"kind": "custom_python", "function": "validators:nope"}) is False
    monkeypatch.setattr(pyimport, "resolve_callable", lambda ref, ident, what: (lambda device, ctx: True))
    assert _ev({"kind": "custom_python", "function": "validators:yes"}) is True


# ── param resolution ────────────────────────────────────────────────────────

def test_unknown_param_rejected():
    with pytest.raises(ParamError, match="Unknown params"):
        runner._resolve_params([Param(name="a")], {"a": 1, "b": 2}, "s", "x")


def test_missing_required_param_rejected():
    with pytest.raises(ParamError, match="Missing required"):
        runner._resolve_params([Param(name="a", required=True)], {}, "s", "x")


def test_enum_membership():
    defs = [Param(name="mode", type="enum", values=["draft", "post"])]
    assert runner._resolve_params(defs, {"mode": "draft"}, "s", "x") == {"mode": "draft"}
    with pytest.raises(ParamError, match="not in"):
        runner._resolve_params(defs, {"mode": "delete"}, "s", "x")


@pytest.mark.parametrize("raw,expected", [("yes", True), ("true", True), ("1", True), ("no", False), ("off", False)])
def test_bool_coercion(raw, expected):
    assert runner._resolve_params([Param(name="b", type="bool")], {"b": raw}, "s", "x") == {"b": expected}


# ── runner: end_state_validator gate and Layer-4 retry ──────────────────────

def _skill(tmp_path, steps, validator):
    return _parse_skill({
        "name": "core", "version": "0.1.0", "author": "t", "license": "MIT", "generated_with": "test",
        "skill_class": "hard", "fingerprint": {"os": "android", "app_package": "com.x"},
        "actions": [{
            "name": "a", "ref_prompt": "do a", "params": [],
            "steps": steps,
            "end_state_validator": validator,
            "test_case": {"ref_prompt_variants": ["do a"], "expected_success": True},
        }],
    }, tmp_path)


def test_failing_end_state_validator_fails_the_run(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "_get_device", lambda serial: _Dev())
    steps = [{"action": "sleep", "duration_s": 0}]
    ok = run_action(_skill(tmp_path, steps, TRUE), "a", device_serial="stub")
    assert ok.success is True
    bad = run_action(_skill(tmp_path, steps, FALSE), "a", device_serial="stub")
    assert bad.success is False
    assert bad.error["kind"] == "ValidatorFailedError"


def _layer4(monkeypatch, outcomes):
    """Patch dispatch to fail/succeed per `outcomes` and fake a new popup appearing."""
    calls = []

    def fake_dispatch(step, ctx, device):
        calls.append(step)
        if not outcomes[len(calls) - 1]:
            raise StepFailedError("blocked by popup")

    dev = _Dev()
    monkeypatch.setattr(runner, "_get_device", lambda serial: dev)
    monkeypatch.setattr(runner, "_fast_dump", lambda d: d.xml)
    monkeypatch.setattr(runner, "dispatch", fake_dispatch)
    monkeypatch.setattr(runner, "looks_like_new_popup", lambda before, after: True)
    monkeypatch.setattr(runner, "try_dismiss_cascade", lambda d: None)
    monkeypatch.setattr(runner, "capture_unknown_popup", lambda d, ctx: "/tmp/popup.png")
    monkeypatch.setattr(runner.time, "sleep", lambda s: None)
    return calls


def test_layer4_retry_recovers_after_unknown_popup(monkeypatch, tmp_path):
    calls = _layer4(monkeypatch, [False, True])
    res = run_action(_skill(tmp_path, [{"action": "tap_element", "text": "Inbox"}], TRUE), "a", device_serial="stub")
    assert res.success is True
    assert len(calls) == 2


def test_layer4_retry_failure_raises_unknown_popup(monkeypatch, tmp_path):
    calls = _layer4(monkeypatch, [False, False])
    res = run_action(_skill(tmp_path, [{"action": "tap_element", "text": "Inbox"}], TRUE), "a", device_serial="stub")
    assert res.success is False
    assert res.error["kind"] == "UnknownPopupError"
    assert len(calls) == 2


def test_fast_dump_never_returns_stale_file_when_dump_fails(monkeypatch):
    """A failed uiautomator dump must fall back to device.dump_xml, not cat a stale file."""
    import subprocess
    from types import SimpleNamespace
    from gitd.skills.engine import dispatch

    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        if "uiautomator" in " ".join(cmd):
            return SimpleNamespace(returncode=1, stdout="ERROR: could not get idle state.\n", stderr="")
        return SimpleNamespace(returncode=0, stdout="<hierarchy>STALE</hierarchy>", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    device = SimpleNamespace(serial="emulator-5554", dump_xml=lambda: "<hierarchy>PORTAL</hierarchy>")
    assert dispatch._fast_dump(device) == "<hierarchy>PORTAL</hierarchy>"
    assert not any("cat" in c for c in calls)


def test_fast_dump_prefers_portal_over_uiautomator(monkeypatch):
    import subprocess
    from types import SimpleNamespace
    from gitd.skills.engine import dispatch

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("uiautomator called")))
    device = SimpleNamespace(serial="emulator-5554", dump_portal_xml=lambda: "<hierarchy>P</hierarchy>",
                             dump_xml=lambda: "unused")
    assert dispatch._fast_dump(device) == "<hierarchy>P</hierarchy>"


def test_portal_miss_is_memoized_per_serial_then_reprobed(monkeypatch):
    """A device without Portal must not pay the probe on every a11y read."""
    from gitd.bots.common import adb

    clock = {"t": 1000.0}
    monkeypatch.setattr(adb.time, "monotonic", lambda: clock["t"])
    monkeypatch.setattr(adb.Device, "_portal_skip_until", {})
    probes = {"no-portal": 0, "with-portal": 0}

    def probe(self):
        probes[self.serial] += 1
        return {"className": "x"} if self.serial == "with-portal" else None

    monkeypatch.setattr(adb.Device, "_probe_portal_json", probe)
    phone, emu = adb.Device("no-portal"), adb.Device("with-portal")
    assert phone.dump_portal_json() is None and phone.dump_portal_json() is None
    assert probes["no-portal"] == 1                      # second read skipped the probe
    assert emu.dump_portal_json() and emu.dump_portal_json()
    assert probes["with-portal"] == 2                    # hits are never memoized as misses
    clock["t"] += adb.Device.PORTAL_RETRY_S + 1
    phone.dump_portal_json()
    assert probes["no-portal"] == 2                      # re-probed after the cooldown


def test_launch_intent_quotes_values_with_spaces():
    from gitd.skills.engine import dispatch
    from gitd.skills.engine.context import RunContext

    calls = []
    device = type("D", (), {"adb": lambda self, *a: calls.append(a)})()
    dispatch._launch_intent({"action": "launch_intent", "intent_action": "android.intent.action.DIAL",
                             "data": "tel:+1 555 0100", "extras": {"label": "Tea time"}},
                            RunContext(action_name="t"), device)
    args = calls[0]
    assert args[0] == "shell"
    assert "'tel:+1 555 0100'" in args and "'Tea time'" in args


def test_dump_xml_failed_uiautomator_returns_empty_hierarchy(monkeypatch):
    from gitd.bots.common import adb

    dev = adb.Device("no-portal-x")
    monkeypatch.setattr(dev, "dump_portal_xml", lambda: None)
    monkeypatch.setattr(dev, "adb_soft", lambda *a, **k: adb.ADBResult(1, "ERROR: could not get idle state.", ""))
    xml = dev.dump_xml()
    assert xml == adb.EMPTY_HIERARCHY and "No such file" not in xml


def test_portal_answering_without_tree_is_not_memoized(monkeypatch):
    from gitd.bots.common import adb

    monkeypatch.setattr(adb.Device, "_portal_skip_until", {})
    monkeypatch.setattr(adb.Device, "_portal_answered", set())
    probes = []

    def probe(self):  # Portal reachable but "No active window" right after a launch
        probes.append(1)
        adb.Device._portal_answered.add(self.serial)
        return None

    monkeypatch.setattr(adb.Device, "_probe_portal_json", probe)
    dev = adb.Device("emu-transient")
    dev.dump_portal_json(); dev.dump_portal_json()
    assert len(probes) == 2


def test_find_bounds_prefers_on_screen_match_and_tap_rejects_off_screen():
    import pytest
    from gitd.skills.engine import dispatch
    from gitd.skills.engine.errors import StepFailedError

    xml = ('<hierarchy><node text="" resource-id="a:id/url_bar" bounds="[0,317][-1122,728]"/>'
           '<node text="" resource-id="a:id/url_bar" bounds="[10,20][110,60]"/>'
           '<node text="Gone" bounds="[0,-500][100,-400]"/></hierarchy>')
    assert dispatch._find_bounds(xml, "id", "a:id/url_bar") == (10, 20, 110, 60)
    assert dispatch._find_bounds(xml, "text", "Gone") == (0, -500, 100, -400)   # presence still reported
    taps = []
    device = type("D", (), {"tap": lambda self, x, y, *a: taps.append((x, y)), "serial": None,
                            "dump_xml": lambda self: xml})()
    with pytest.raises(StepFailedError, match="off screen"):
        dispatch._tap_element({"action": "tap_element", "text": "Gone"}, None, device)
    assert taps == []



def test_find_bounds_matches_labels_with_html_entities():
    from gitd.skills.engine import dispatch

    xml = ('<hierarchy><node text="Battery &amp; charging" bounds="[0,100][500,160]"/>'
           '<node bounds="[0,200][500,260]" content-desc="Don&#x27;t allow"/>'
           '<node text="Battery" bounds="[0,300][500,360]"/></hierarchy>')
    assert dispatch._find_bounds(xml, "text", "Battery & charging") == (0, 100, 500, 160)
    assert dispatch._find_bounds(xml, "desc", "Don't allow") == (0, 200, 500, 260)  # bounds-first order
    assert dispatch._find_bounds(xml, "text", "Battery") == (0, 300, 500, 360)  # still exact
    assert dispatch._find_bounds(xml, "text", "Battery &amp; charging") is None  # needle is plain text


def test_os_popup_sweep_denies_android14_permission_dialog():
    from gitd.skills.engine import os_popups

    xml = ('<hierarchy><node text="Allow Foo to send you notifications?" bounds="[0,0][10,10]"/>'
           '<node text="Allow" bounds="[133,1231][947,1378]"/>'
           '<node text="Don’t allow" bounds="[133,1388][947,1535]"/></hierarchy>')
    taps = []
    device = type("D", (), {"tap": lambda self, x, y, *a: taps.append((x, y)), "serial": None,
                            "dump_xml": lambda self: xml})()
    assert os_popups.sweep(device) is True
    assert taps == [(540, 1461)]


def test_skill_declared_popups_never_trigger_generic_dismiss_taps(monkeypatch):
    """v2 runs of a skill with popup_detectors or os_popup_policy rely on Layers 1, 2 and 4
    only: the device's generic Cancel/Skip/Later fallback must not tap anything."""
    from gitd.bots.common import adb
    from gitd.skills.engine.context import RunContext
    from gitd.skills.engine.dispatch import skill_dismiss_popups

    xml = ('<hierarchy><node text="Cancel" clickable="true" bounds="[100,900][300,1000]"/>'
           '<node text="Skip" clickable="true" bounds="[400,900][600,1000]"/></hierarchy>')
    dev = adb.Device("generic-test")
    taps = []
    monkeypatch.setattr(dev, "tap", lambda x, y, delay=0.6: taps.append((x, y)))
    monkeypatch.setattr(dev, "back", lambda delay=1.0: taps.append("BACK"))
    for extras in ({"_skill_popup_detectors": [{"detect": "Rate us", "button": "Later"}]},
                   {"_skill_popup_detectors": [], "_os_popup_policy": {"deny_permissions": ["contacts"]}}):
        ctx = RunContext(action_name="a", extras=dict(extras))
        assert skill_dismiss_popups(dev, ctx, xml) is False
    assert taps == []
    # A skill that declares nothing keeps the legacy generic fallback.
    assert skill_dismiss_popups(dev, RunContext(action_name="a"), xml) is True and len(taps) == 1


def test_layer1_runs_only_when_a_system_dialog_has_focus(monkeypatch):
    import subprocess
    from types import SimpleNamespace
    from gitd.skills.engine import os_popups

    focus = {"v": "mCurrentFocus=Window{1 u0 com.example/.Main}"}
    dumps = []
    monkeypatch.setattr(subprocess, "run", lambda cmd, **k: SimpleNamespace(stdout=focus["v"], returncode=0))
    monkeypatch.setattr(os_popups, "sweep", lambda device, policy=None: dumps.append(policy) or True)
    dev = SimpleNamespace(serial="emulator-5554")
    assert os_popups.sweep_if_system_dialog(dev, {"deny_permissions": ["contacts"]}) is False
    focus["v"] = ("mCurrentFocus=Window{2 u0 com.google.android.permissioncontroller/"
                  "com.android.permissioncontroller.permission.ui.GrantPermissionsActivity}")
    assert os_popups.sweep_if_system_dialog(dev, {"deny_permissions": ["contacts"]}) is True
    assert dumps == [{"deny_permissions": ["contacts"]}]


def test_immersive_mode_cling_is_dismissed_by_layer1():
    from gitd.skills.engine import os_popups

    xml = ('<hierarchy><node text="Viewing full screen" bounds="[0,265][1080,455]"/>'
           '<node text="Got it" bounds="[744,592][975,718]"/></hierarchy>')
    taps = []
    device = type("D", (), {"tap": lambda self, x, y, *a: taps.append((x, y)), "serial": None,
                            "dump_xml": lambda self: xml})()
    assert os_popups.sweep(device) is True and taps == [(859, 655)]
