"""The demo harness must isolate fixtures without clearing someone else's apps."""

from contextlib import contextmanager

import pytest

from tools.showcase_replay import DemoReplay, ReplayCase, ResetRefused


class Device:
    def __init__(self, system=(), clear="Success", home=True, focus="com.android.launcher"):
        self.focus = focus
        self.system, self.clear, self.home = system, clear, home
        self.calls = []

    def adb(self, *args):
        self.calls.append(args)
        if args == ("shell", "pm", "list", "packages", "-s"):
            return "\n".join("package:" + p for p in ("com.android.systemui", *self.system))
        if args[:3] == ("shell", "pm", "clear"):
            return self.clear
        if args == ("shell", "dumpsys", "window"):
            return "mCurrentFocus=Window{abc u0 " + self.focus + "/.Window}"
        if args == ("shell", "dumpsys", "activity", "activities"):
            return (
                "mResumedActivity: ActivityRecord{abc u0 com.android.launcher/.HomeActivity t1}\nmActivityType=home"
                if self.home
                else "mResumedActivity: ActivityRecord{abc u0 com.other/.Screen t1}"
            )
        if args[:4] == ("shell", "cmd", "package", "resolve-activity"):
            return (
                args[-1] + "/.MainActivity"
                if "android.intent.category.LAUNCHER" in args
                else "com.android.launcher/.HomeActivity"
            )
        return ""


@contextmanager
def capture(events):
    events.append("capture_start")
    try:
        yield
    finally:
        events.append("capture_stop")


def case(package="org.fossify.math"):
    return ReplayCase("ghost/calculator", "calculate", package, {"expression": "12*3"})


@pytest.mark.parametrize(
    "package,baseline,owned,system",
    [
        ("com.personal.notes", set(), {"com.personal.notes"}, ()),
        ("org.fossify.math", {"org.fossify.math"}, {"org.fossify.math"}, ()),
        ("org.fossify.math", set(), set(), ()),
        ("com.google.android.deskclock", set(), {"com.google.android.deskclock"}, ("com.google.android.deskclock",)),
    ],
)
def test_clear_refuses_personal_preexisting_unowned_and_system_apps(package, baseline, owned, system):
    device = Device(system=system)
    protocol = DemoReplay(device, baseline_packages=baseline, installed_by_lane=owned, sleep=lambda _: None)
    with pytest.raises(ResetRefused):
        protocol.clear_demo(package)
    assert not any(c[:3] == ("shell", "pm", "clear") for c in device.calls)


def test_snapshot_authorization_permits_only_named_preexisting_demo_apps():
    device = Device()
    protocol = DemoReplay(
        device,
        baseline_packages={"org.fossify.math"},
        installed_by_lane=set(),
        snapshot_reset_packages={"org.fossify.math"},
        snapshot_name="saved-snapshot",
        sleep=lambda _: None,
    )
    protocol.clear_demo("org.fossify.math")
    assert ("shell", "pm", "clear", "org.fossify.math") in device.calls
    with pytest.raises(ResetRefused):
        protocol.clear_demo("org.tasks")


def test_snapshot_exception_never_permits_a_system_package():
    protocol = DemoReplay(
        Device(system=("com.google.android.deskclock",)),
        baseline_packages={"com.google.android.deskclock"},
        installed_by_lane=set(),
        snapshot_reset_packages={"com.google.android.deskclock"},
        snapshot_name="saved",
        sleep=lambda _: None,
    )
    with pytest.raises(ResetRefused):
        protocol.clear_demo("com.google.android.deskclock")


def test_reset_seed_home_record_launch_action_order_and_each_run_is_reset():
    events = []
    device = Device()
    protocol = DemoReplay(device, baseline_packages=set(), installed_by_lane={"org.fossify.math"}, sleep=lambda _: None)

    def seed():
        assert device.calls[-1] == ("shell", "pm", "clear", "org.fossify.math")
        events.append("seed")
        return {"fixture": "none", "verified": True}

    def execute():
        events.append("execute")
        return {"success": True}

    for _ in range(2):
        result = protocol.run(case(), seed=seed, execute=execute, capture=lambda: capture(events))
        assert result["protocol_complete"]
        names = [e["event"] for e in result["protocol"]]
        assert (
            names.index("pm_clear")
            < names.index("seed_verified")
            < names.index("home_verified")
            < names.index("capture_started")
            < names.index("action_started")
        )
    assert events == ["seed", "capture_start", "execute", "capture_stop"] * 2
    assert device.calls.count(("shell", "pm", "clear", "org.fossify.math")) == 2


@pytest.mark.parametrize(
    "clear,fixture,home", [("Failed", True, True), ("Success", False, True), ("Success", True, False)]
)
def test_failed_clear_fixture_or_home_prevents_recording_and_action(clear, fixture, home):
    events = []
    protocol = DemoReplay(
        Device(clear=clear, home=home),
        baseline_packages=set(),
        installed_by_lane={"org.fossify.math"},
        sleep=lambda _: None,
    )
    with pytest.raises(ResetRefused):
        protocol.run(
            case(),
            seed=lambda: {"verified": fixture},
            execute=lambda: events.append("execute"),
            capture=lambda: capture(events),
        )
    assert events == []


def test_seed_exception_prevents_recording():
    events = []
    protocol = DemoReplay(
        Device(), baseline_packages=set(), installed_by_lane={"org.fossify.math"}, sleep=lambda _: None
    )

    def bad_seed():
        raise RuntimeError("fixture could not be prepared")

    with pytest.raises(RuntimeError):
        protocol.run(case(), seed=bad_seed, execute=lambda: events.append("execute"), capture=lambda: capture(events))
    assert not events


def test_action_failure_still_stops_capture_and_is_not_passed():
    events = []
    protocol = DemoReplay(
        Device(), baseline_packages=set(), installed_by_lane={"org.fossify.math"}, sleep=lambda _: None
    )
    result = protocol.run(
        case(), seed=lambda: {"verified": True}, execute=lambda: {"success": False}, capture=lambda: capture(events)
    )
    assert not result["result"]["success"]
    assert events == ["capture_start", "capture_stop"]


def test_system_clock_uses_verified_ui_reset_and_is_labelled_separately():
    events = []
    device = Device(system=("com.google.android.deskclock",))
    protocol = DemoReplay(
        device, baseline_packages={"com.google.android.deskclock"}, installed_by_lane=set(), sleep=lambda _: None
    )
    result = protocol.run(
        ReplayCase("ghost/clock", "list_alarms", "com.google.android.deskclock", {}),
        ui_reset=lambda: {"verified": True, "alarms": 0, "timers": 0, "stopwatch": "reset"},
        seed=lambda: {"verified": True},
        execute=lambda: {"success": True},
        capture=lambda: capture(events),
    )
    assert result["reset_mode"] == "verified_ui_reset"
    assert not any(c[:3] == ("shell", "pm", "clear") for c in device.calls)


def test_empty_system_inventory_refuses_clear():
    device = Device()
    device.adb = lambda *args: ""
    protocol = DemoReplay(device, baseline_packages=set(), installed_by_lane={"org.fossify.math"})
    with pytest.raises(ResetRefused):
        protocol.clear_demo("org.fossify.math")


def test_old_leftover_results_do_not_count_as_isolated_fixture_passes():
    from types import SimpleNamespace

    from tools.replay_showcase import verify_fixture_result

    result = SimpleNamespace(success=True, data={"value": 6170})
    assert not verify_fixture_result(ReplayCase("ghost/calculator", "read_result", "org.fossify.math", {}), result)
    result.data = {"results": ["36", "36"], "formulas": ["12*3", "12*3"]}
    assert not verify_fixture_result(ReplayCase("ghost/calculator", "get_history", "org.fossify.math", {}), result)
    result.data = {"tasks": [{"title": "Isolated buy stamps"}, {"title": "Leftover task"}]}
    assert not verify_fixture_result(ReplayCase("ghost/tasks", "list_tasks", "org.tasks", {}), result)


def test_cannot_resolve_demo_launch_does_not_execute_action_and_stops_capture():
    events = []
    device = Device()
    original = device.adb

    def adb(*args):
        if "android.intent.category.LAUNCHER" in args:
            return "com.personal.app/.MainActivity"
        return original(*args)

    device.adb = adb
    protocol = DemoReplay(device, baseline_packages=set(), installed_by_lane={"org.fossify.math"}, sleep=lambda _: None)
    with pytest.raises(ResetRefused):
        protocol.run(
            case(),
            seed=lambda: {"verified": True},
            execute=lambda: events.append("execute"),
            capture=lambda: capture(events),
        )
    assert events == ["capture_start", "capture_stop"]


def test_clock_reset_waits_for_known_test_alarm_to_render(monkeypatch):
    from types import SimpleNamespace

    from tools import replay_showcase as harness

    rid = "com.google.android.deskclock:id/"
    empty = []
    card = {"id": "", "desc": "07:30 Isolated demo alarm", "text": "", "bounds": (0, 0, 500, 500)}
    label = {"id": rid + "label", "desc": "", "text": "Isolated demo alarm", "bounds": (10, 10, 200, 40)}
    switch = {"id": rid + "onoff", "desc": "", "text": "", "bounds": (300, 60, 350, 100)}
    delete = {"id": "", "desc": "Delete", "text": "", "bounds": (10, 300, 90, 350)}
    zero = [
        {"id": rid + "stopwatch_time_text", "text": "00", "desc": "", "bounds": (0, 0, 100, 100)},
        {"id": "", "text": "", "desc": "Start", "bounds": (0, 100, 100, 200)},
    ]
    views = iter([empty, [card, label, switch], [delete]])
    h = SimpleNamespace(
        _ID=rid,
        show_clock_tab=lambda *a: zero,
        clock_snapshot=lambda d: next(views),
        _inside=lambda inner, outer: outer == card["bounds"],
        _clock_prefs=lambda d: {"sw_state": "0"},
    )
    states = iter(
        [[{"enabled": True, "label": "Isolated demo alarm"}], [{"enabled": True, "label": "Isolated demo alarm"}], []]
    )
    monkeypatch.setattr(harness, "helper", lambda ref: h)
    monkeypatch.setattr(harness, "checked_seed", lambda *a: {"alarms": next(states)})
    monkeypatch.setattr(harness.time, "sleep", lambda _: None)
    tapped = []
    monkeypatch.setattr(harness, "tap", lambda d, n: tapped.append(n))
    assert harness.reset_clock_ui(Device())["verified"]
    assert tapped == [delete]


def test_home_behind_system_overlay_is_not_recorded():
    events = []
    protocol = DemoReplay(
        Device(focus="com.android.systemui"),
        baseline_packages=set(),
        installed_by_lane={"org.fossify.math"},
        sleep=lambda _: None,
    )
    with pytest.raises(ResetRefused):
        protocol.run(
            case(),
            seed=lambda: {"verified": True},
            execute=lambda: events.append("execute"),
            capture=lambda: capture(events),
        )
    assert not events
