"""Agent package policy regressions; every transport and foreground is mocked."""
import inspect
import shlex
import subprocess
from types import SimpleNamespace

import pytest

from gitd.bots.common import package_policy as policy
from gitd.bots.common.adb import Device
from gitd.services import agent_tools

DENIED = "com.android.vending"
ALLOWED = "com.example.board"


@pytest.fixture
def phone(monkeypatch):
    monkeypatch.setenv("GHOST_DENY_PACKAGES", f" {DENIED}, ,com.example.private ")
    monkeypatch.setattr(policy.time, "sleep", lambda _: None)
    state = SimpleNamespace(package=ALLOWED, commands=[], inputs=[], target=ALLOWED, on_input=None, home_error=False)

    def raw(device, *args):
        state.commands.append((device, args))
        if args == ("shell", "input", "keyevent", "KEYCODE_HOME"):
            if state.home_error:
                return subprocess.CompletedProcess(args, 1, "", "mock HOME failed")
            state.package = ALLOWED
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[:3] == ("shell", "dumpsys", "window"):
            output = f"mCurrentFocus=Window{{abc u0 {state.package}/.Main}}" if state.package else "mCurrentFocus=null"
        elif args[:3] == ("shell", "dumpsys", "activity"):
            output = ""
        else:
            pytest.fail(f"Unexpected unmocked policy command: {args}")
        return subprocess.CompletedProcess(args, 0, output, "")

    def unchecked(self, args, timeout):
        if tuple(args[:2]) == ("shell", "dumpsys"):
            return policy._raw(self.serial, *args)
        state.inputs.append(tuple(args))
        if tuple(args[:4]) == ("shell", "cmd", "package", "resolve-activity"):
            output = f"{state.target}/.Main\n" if state.target else "No activity found"
        else:
            if state.on_input:
                state.on_input()
            output = "OK"
        return subprocess.CompletedProcess(args, 0, output, "")

    monkeypatch.setattr(policy, "_raw", raw)
    monkeypatch.setattr(Device, "_run_unchecked", unchecked)
    return state


def homes(phone):
    return [cmd for _, cmd in phone.commands if cmd == ("shell", "input", "keyevent", "KEYCODE_HOME")]


def test_empty_policy_has_no_probe_or_behavior_change(monkeypatch):
    monkeypatch.setenv("GHOST_DENY_PACKAGES", " , ")
    monkeypatch.setattr(policy, "_raw", lambda *a: pytest.fail("disabled guard must not probe"))
    with policy.package_session("mock"):
        policy.require_package(DENIED)
    assert policy.guard_mcp_function(lambda device: "normal")("mock") == "normal"


def test_exact_trimmed_package_match(phone):
    assert policy.denied_packages() == {DENIED, "com.example.private"}
    policy.require_package(DENIED + ".example")
    with pytest.raises(policy.PackagePolicyError, match="refusing denied package"):
        policy.require_package(DENIED + "/.Main")
    assert not homes(phone)


@pytest.mark.parametrize("name,args", [
    ("launch_app", {"package": DENIED, "fresh": True}),
    ("launch_intent", {"component": DENIED + "/.Main"}),
    ("open_url", {"bundle_id": DENIED}),
    ("web_search", {"bundle_id": DENIED}),
])
def test_agent_explicit_targets_are_refused_before_dispatch(phone, monkeypatch, name, args):
    monkeypatch.setattr(agent_tools, "_execute_tool_impl", lambda *a: pytest.fail("denied launch executed"))
    result = agent_tools.execute_tool(name, {"device": "mock", **args})
    assert "refusing denied package" in result and DENIED in result
    assert not homes(phone)


@pytest.mark.parametrize("args", [
    ("shell", "monkey", "-p", DENIED, "1"),
    ("shell", "am", "start", "-n", DENIED + "/.Main"),
    ("shell", "am", "start", "-p", DENIED),
])
def test_skill_low_level_explicit_launch_refused(phone, args):
    with pytest.raises(policy.PackagePolicyError, match=DENIED):
        Device("mock").adb(*args)
    assert not phone.inputs


@pytest.mark.parametrize("uri", ["market://details?id=com.example.game", "https://play.google.com/store/apps/details?id=com.example.game"])
def test_implicit_intent_resolves_denied_target_without_launch(phone, uri):
    phone.target = DENIED
    with pytest.raises(policy.PackagePolicyError, match=DENIED):
        Device("mock").adb("shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", uri)
    assert len(phone.inputs) == 1
    assert "resolve-activity" in phone.inputs[0]
    assert uri in shlex.split(" ".join(phone.inputs[0]))


def test_unknown_intent_target_fails_closed(phone):
    phone.target = ""
    with pytest.raises(policy.PackagePolicyError, match="cannot resolve intent target"):
        Device("mock").adb("shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", "example://link")
    assert len(phone.inputs) == 1


def test_raw_input_text_with_unbalanced_quote_is_guarded_not_crashed(phone):
    # The per-character `input text` fallbacks send unquoted text; an apostrophe
    # used to raise shlex's ValueError out of every guarded adb call.
    assert Device("mock").adb("shell", "input", "text", "it's") == "OK"
    assert phone.inputs == [("shell", "input", "text", "it's")]
    phone.package = DENIED
    with pytest.raises(policy.PackagePolicyError, match="action stopped"):
        Device("mock").adb("shell", "input", "text", "it's")


def test_am_start_activity_alias_is_guarded_like_am_start(phone):
    with pytest.raises(policy.PackagePolicyError, match=DENIED):
        Device("mock").adb("shell", "am", "start-activity", "-n", DENIED + "/.Main")
    assert not phone.inputs
    assert Device("mock").adb("shell", "am", "start-activity", "-n", ALLOWED + "/.Main") == "OK"
    assert "resolve-activity" in phone.inputs[0]


@pytest.mark.parametrize("flags", [("-S",), ("-W", "-S"), ("-D", "-R", "3"), ("--windowingMode", "1", "-N")])
def test_am_only_flags_are_dropped_before_resolution(phone, flags):
    assert Device("mock").adb("shell", "am", "start", *flags, "-n", ALLOWED + "/.Main") == "OK"
    resolve = shlex.split(" ".join(phone.inputs[0]))
    assert "resolve-activity" in resolve
    assert not set(flags) & set(resolve) and "3" not in resolve and "1" not in resolve
    assert phone.inputs[1] == ("shell", "am", "start", *flags, "-n", ALLOWED + "/.Main")


def test_allowed_intent_is_resolved_then_launched(phone):
    assert Device("mock").adb("shell", "am", "start", "-n", ALLOWED + "/.Main") == "OK"
    assert len(phone.inputs) == 2
    assert "resolve-activity" in phone.inputs[0]
    assert phone.inputs[1][:3] == ("shell", "am", "start")


def test_tap_that_opens_store_sends_home_once_and_latches_even_if_caught(phone):
    phone.on_input = lambda: setattr(phone, "package", DENIED)
    with pytest.raises(policy.PackagePolicyError, match="sent HOME once"):
        with policy.package_session("mock"):
            try:
                Device("mock").tap(10, 20)
            except policy.PackagePolicyError:
                pass  # a broad catch in a helper cannot permit the next input
            Device("mock").tap(30, 40)
    assert len(phone.inputs) == 1
    assert len(homes(phone)) == 1


def test_already_denied_foreground_is_evacuated_before_input(phone):
    phone.package = DENIED
    with pytest.raises(policy.PackagePolicyError, match="action stopped"):
        Device("mock").tap(10, 20)
    assert not phone.inputs
    assert len(homes(phone)) == 1


def test_recovery_failure_is_reported_without_retry(phone):
    phone.package = DENIED
    phone.home_error = True
    with pytest.raises(policy.PackagePolicyError, match="HOME attempted once but failed"):
        with policy.package_session("mock"):
            pytest.fail("must not execute body")
    assert len(homes(phone)) == 1


def test_unknown_foreground_refuses_before_input(phone):
    phone.package = ""
    with pytest.raises(policy.PackagePolicyError, match="cannot verify foreground"):
        Device("mock").tap(10, 20)
    assert not phone.inputs and not homes(phone)


@pytest.mark.parametrize("batch", ["chain", "flow"])
def test_batch_stops_before_second_action_and_recovers_once(phone, monkeypatch, batch):
    from gitd import mcp_server

    calls = []
    original = agent_tools._execute_tool_impl

    def action(name, args):
        if name == "chain":
            return original(name, args)
        calls.append(name)
        phone.package = DENIED
        return "tapped"

    monkeypatch.setattr(agent_tools, "_execute_tool_impl", action)
    steps = [{"tool": "tap", "args": {"x": 1, "y": 2}}, {"tool": "type_text", "args": {"text": "install"}}]
    if batch == "chain":
        result = agent_tools.execute_tool("chain", {"device": "mock", "actions": steps})
    else:
        import json
        result = mcp_server.run_flow("mock", json.dumps(steps))
    assert "GHOST_DENY_PACKAGES" in result
    assert calls == ["tap"]
    assert len(homes(phone)) == 1


def test_direct_mcp_tap_is_guarded_and_signature_preserved(phone, monkeypatch):
    from gitd import mcp_server

    class PortalDevice:
        def __init__(self, serial):
            pass

        def tap(self, *args, **kwargs):
            phone.package = DENIED

    monkeypatch.setattr(mcp_server, "get_device", PortalDevice)
    # Some MCP handlers directly construct Android Device instead of the factory.
    monkeypatch.setattr(mcp_server, "Device", PortalDevice)
    assert "device" in inspect.signature(mcp_server.tap).parameters
    assert "GHOST_DENY_PACKAGES" in mcp_server.tap("mock", 1, 2)
    assert len(homes(phone)) == 1


def make_skill(steps, package=ALLOWED, apps=None):
    from gitd.skills.engine.loader import ActionDef, Fingerprint, SkillDef
    return SkillDef(name="mock-policy", version="1.0.0", fingerprint=Fingerprint(app_package=package, apps=apps or []),
                    actions=[ActionDef(name="go", steps=steps)])


@pytest.mark.parametrize("extra", [False, True])
def test_denied_skill_fingerprint_is_refused_before_device_resolution(phone, monkeypatch, extra):
    from gitd.skills.engine import run_action
    monkeypatch.setattr("gitd.skills.engine.runner._get_device", lambda *a: pytest.fail("must refuse before device"))
    skill = make_skill([], package=ALLOWED if extra else DENIED, apps=[DENIED] if extra else [])
    result = run_action(skill, "go", device_serial="mock")
    assert not result.success and result.status == "refused"
    assert result.error["kind"] == "package_denied"
    assert not phone.commands


def test_skill_stops_after_a_step_switches_foreground(phone, monkeypatch):
    from gitd.skills.engine import dispatch, run_action

    calls = []

    def tap(step, ctx, device):
        calls.append(step)
        phone.package = DENIED

    monkeypatch.setitem(dispatch._HANDLERS, "tap", tap)
    monkeypatch.setattr("gitd.skills.engine.runner._get_device", lambda _: Device("mock"))
    skill = make_skill([{"action": "tap", "x": 1, "y": 2}, {"action": "tap", "x": 3, "y": 4}])
    result = run_action(skill, "go", device_serial="mock")
    assert result.status == "refused" and result.error["kind"] == "package_denied"
    assert len(calls) == 1 and len(homes(phone)) == 1


def test_service_open_url_denies_implicit_store_intent(phone):
    from gitd.services.browser import open_url
    phone.target = DENIED
    result = open_url("mock", "market://details?id=com.example.game")
    assert not result["ok"] and DENIED in result["result"]
    assert len(phone.inputs) == 1


def test_new_call_can_proceed_after_previous_call_was_evacuated(phone):
    phone.package = DENIED
    with pytest.raises(policy.PackagePolicyError):
        with policy.package_session("mock"):
            pass
    with policy.package_session("mock"):
        Device("mock").tap(10, 20)
    assert len(phone.inputs) == 1 and len(homes(phone)) == 1


def test_python_helper_cannot_swallow_denial_and_continue_skill(phone, monkeypatch):
    from gitd.skills.engine import dispatch, run_action

    calls = []

    def helper(device, params, context):
        phone.on_input = lambda: setattr(phone, "package", DENIED)
        try:
            device.tap(1, 2)
        except Exception:
            calls.append("caught")
        return {"ok": True}

    monkeypatch.setattr("gitd.skills.engine.pyimport.resolve_callable", lambda *a, **k: helper)
    monkeypatch.setattr("gitd.skills.engine.runner._get_device", lambda _: Device("mock"))
    monkeypatch.setitem(dispatch._HANDLERS, "tap", lambda *a: calls.append("unsafe next step"))
    result = run_action(make_skill([{"python_action": "helpers:swallow"}, {"action": "tap", "x": 1, "y": 2}]),
                        "go", device_serial="mock")
    assert not result.success and result.error["kind"] == "package_denied"
    assert calls == ["caught"] and len(homes(phone)) == 1


def test_denied_dry_run_does_not_probe_device(phone):
    from gitd.skills.engine import run_action
    result = run_action(make_skill([], package=DENIED), "go", device_serial="mock", dry_run=True)
    assert result.status == "refused" and not phone.commands


def test_allowed_dry_run_does_not_probe_device(phone):
    from gitd.skills.engine import run_action
    result = run_action(make_skill([{"action": "tap", "x": 1, "y": 2}]), "go", device_serial="mock", dry_run=True)
    assert result.success and not phone.commands


def test_foreground_transport_failure_refuses_action(phone, monkeypatch):
    def unavailable(*args):
        raise TimeoutError("mock timeout")
    monkeypatch.setattr(policy, "_raw", unavailable)
    with pytest.raises(policy.PackagePolicyError, match="cannot verify foreground.*mock timeout"):
        Device("mock").tap(1, 2)
    assert not phone.inputs


def test_resumed_activity_fallback_catches_denied_package(phone, monkeypatch):
    original = policy._raw

    def fallback(device, *args):
        if args[:3] == ("shell", "dumpsys", "window"):
            return subprocess.CompletedProcess(args, 0, "mCurrentFocus=null", "")
        if args[:3] == ("shell", "dumpsys", "activity"):
            return subprocess.CompletedProcess(args, 0, f"topResumedActivity=ActivityRecord{{a u0 {DENIED}/.Main t1}}", "")
        return original(device, *args)

    monkeypatch.setattr(policy, "_raw", fallback)
    with pytest.raises(policy.PackagePolicyError, match=DENIED):
        with policy.package_session("mock"):
            pytest.fail("must not act")
    assert len(homes(phone)) == 1


def test_ios_foreground_uses_active_app_info_and_home_once(phone, monkeypatch):
    calls = []
    ios = SimpleNamespace(
        _execute_mobile=lambda *a: {"bundleId": DENIED},
        press_key=lambda key, **kw: calls.append(key),
    )
    monkeypatch.setattr("gitd.bots.common.device.get_device", lambda _: ios)
    with pytest.raises(policy.PackagePolicyError, match=DENIED):
        with policy.package_session("ios:mock"):
            pytest.fail("must not act")
    assert calls == ["HOME"] and not phone.commands


def test_mcp_denied_launch_has_no_force_stop_or_launch_side_effect(phone, monkeypatch):
    from gitd import mcp_server
    monkeypatch.setattr(agent_tools, "_execute_tool_impl", lambda *a: pytest.fail("must not launch or stop"))
    result = mcp_server.launch_app("mock", DENIED, fresh=True)
    assert "refusing denied package" in result and not phone.inputs and not homes(phone)


def test_wait_checks_selected_session_device_after_delayed_switch(phone, monkeypatch):
    monkeypatch.setenv("GHOST_DEVICE", "mock")

    @policy.guard_mcp_function
    def wait(seconds=1):
        phone.package = DENIED
        return "waited"

    assert "denied foreground package" in wait()
    assert len(homes(phone)) == 1

def test_empty_foreground_transition_retries_then_verifies(phone,monkeypatch):
    owners=iter(['','',ALLOWED]);calls=[]
    def foreground(device):calls.append(device);return next(owners)
    monkeypatch.setattr(policy,'_foreground',foreground)
    policy.check_foreground('mock')
    assert len(calls)==3 and not homes(phone)


def test_persistently_empty_foreground_still_fails_closed(phone,monkeypatch):
    calls=[];slept=[]
    monkeypatch.setattr(policy.time,'sleep',slept.append)
    monkeypatch.setattr(policy,'_foreground',lambda device:calls.append(device) or '')
    with pytest.raises(policy.PackagePolicyError,match='cannot verify foreground'):
        policy.check_foreground('mock')
    assert len(calls)==len(policy._FOREGROUND_RETRY_DELAYS)+1 and not phone.inputs
    assert slept==list(policy._FOREGROUND_RETRY_DELAYS) and 1.0<=sum(slept)<=2.0


def test_slow_transition_owner_appears_late_within_backoff(phone,monkeypatch):
    # Slow phones report no owner for ~1 s during launches; that must not refuse the action.
    owners=iter(['','','','',ALLOWED]);calls=[]
    monkeypatch.setattr(policy.time,'sleep',lambda s:None)
    def foreground(device):calls.append(device);return next(owners)
    monkeypatch.setattr(policy,'_foreground',foreground)
    policy.check_foreground('mock')
    assert len(calls)==5 and not homes(phone)


def test_transient_probe_error_is_retried_then_verifies(phone,monkeypatch):
    seq=iter([TimeoutError('adb hiccup'),ALLOWED])
    monkeypatch.setattr(policy.time,'sleep',lambda s:None)
    def foreground(device):
        v=next(seq)
        if isinstance(v,Exception):raise v
        return v
    monkeypatch.setattr(policy,'_foreground',foreground)
    policy.check_foreground('mock')
    assert not homes(phone)


def test_denied_owner_after_empty_probe_is_immediately_evacuated(phone,monkeypatch):
    owners=iter(['',DENIED]);calls=[]
    def foreground(device):calls.append(device);return next(owners)
    monkeypatch.setattr(policy,'_foreground',foreground)
    with pytest.raises(policy.PackagePolicyError,match='sent HOME once'):
        policy.check_foreground('mock')
    assert len(calls)==2 and len(homes(phone))==1 and not phone.inputs


def test_android_foreground_uses_full_window_focus_line(phone):
    assert policy._foreground('mock')==ALLOWED
    assert phone.commands==[('mock',('shell','dumpsys','window','|','grep','-m1','mCurrentFocus'))]
