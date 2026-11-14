"""Device-state regressions for the showcase skills; no emulator or model calls."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from gitd.skills.engine.context import RunContext
from gitd.skills.engine.dispatch import dispatch

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/showcase-skills"


def helper(slug):
    spec = importlib.util.spec_from_file_location(slug, ROOT / f"skillhub/ghost/{slug}/helpers.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture(name):
    return (FIXTURES / name).read_text()


def ctx(params=None, result=None):
    return SimpleNamespace(params=params or {}, result=result or {})


class Device:
    def __init__(self, xml="", prefs=None):
        self.xml = xml
        self.prefs = prefs
        self.events = []
        self.contacts = fixture("contacts-provider.txt")
        self.data = fixture("contacts-data.txt")

    def dump_xml(self):
        if self.prefs is not None:
            raise RuntimeError("could not get idle state")
        self.events.append("dump")
        return self.xml

    def tap(self, x, y, *args):
        self.events.append(("tap", x, y))

    def adb(self, *args):
        self.events.append(args)
        command = " ".join(args)
        if "content query" in command:
            return self.data if "/data " in command else self.contacts
        if args[:3] == ("shell", "pm", "path"):
            return "package:/demo/clock.apk" if args[-1] == "com.google.android.deskclock" else ""
        if "shared_prefs" in command:
            return self.prefs
        return ""

    def swipe(self, *args):
        pass


def test_contacts_search_scopes_xml_and_focuses_before_typing(monkeypatch):
    h = helper("contacts")
    monkeypatch.setattr(h.time, "sleep", lambda _: None)
    dev = Device(fixture("contacts-search.xml"))
    assert h._names(h.visible_nodes(dev, within="open_search_view")) == ["Grace Hopper", "Grace Kelly", "Alan Turing"]
    result = h.search(dev, {"query": "Grace"}, ctx())
    assert result["data"]["contacts"] == ["Grace Hopper", "Grace Kelly"]
    typed = next(i for i, e in enumerate(dev.events) if isinstance(e, tuple) and "text" in e)
    assert ("tap", 50, 60) in dev.events[:typed]


def test_markor_read_taps_folded_file_row():
    dev = Device(fixture("markor-folded.xml"))
    action = next(
        a
        for a in yaml.safe_load((ROOT / "skillhub/ghost/markor/skill.yaml").read_text())["actions"]
        if a["name"] == "read_note"
    )
    # Exercise the actual row-opening step from the manifest.
    step = next(
        s
        for s in action["steps"]
        if s.get("text") == "{title}.md"
        and s.get("action") == "tap_element"
        or s.get("python_action") == "helpers:open_note"
    )
    if "python_action" in step:
        assert helper("markor").open_note(dev, {"title": "Recipe"}, ctx())["success"]
    else:
        dispatch({**step, "text": "Recipe.md"}, RunContext(action_name="read_note", params={}), dev)
    assert dev.events[-1] == ("tap", 540, 250)


def test_clock_alarm_intent_reaches_clock_with_another_alarm_handler_installed():
    import shlex
    import xml.etree.ElementTree as ET

    from gitd.skills.engine.interpolate import interpolate

    class AlarmResolverDevice(Device):
        def __init__(self):
            super().__init__(fixture("clock-alarm-resolver.xml"))
            self.delivered = None

        def adb(self, *args):
            argv = shlex.split(" ".join(args))
            assert argv[:5] == ["shell", "am", "start", "-a", "android.intent.action.SET_ALARM"]
            # Model Android's resolver boundary: an unscoped intent leaves the
            # captured Clock/Noice chooser awaiting a selection on a fresh app.
            if "-p" in argv and argv[argv.index("-p") + 1] == "com.google.android.deskclock":
                self.delivered = argv
                self.xml = "<hierarchy/>"
            return "Starting: Intent"

    dev = AlarmResolverDevice()
    texts = {node.get("text") for node in ET.fromstring(dev.dump_xml()).iter("node")}
    assert {"Complete action using", "Clock", "Noice"} <= texts
    action = next(
        a
        for a in yaml.safe_load((ROOT / "skillhub/ghost/clock/skill.yaml").read_text())["actions"]
        if a["name"] == "set_alarm"
    )
    context = RunContext(action_name="set_alarm", params={"hour": 7, "minute": 30, "label": "Demo workout"})
    dispatch(interpolate(action["steps"][0], context), context, dev)
    assert dev.delivered is not None, "SET_ALARM remained in the captured Clock/Noice resolver"
    assert "Complete action using" not in dev.dump_xml()
    argv = dev.delivered
    for flag, key, value in [
        ("--ei", "HOUR", "7"),
        ("--ei", "MINUTES", "30"),
        ("--es", "MESSAGE", "Demo workout"),
        ("--ez", "SKIP_UI", "true"),
    ]:
        index = argv.index("android.intent.extra.alarm." + key)
        assert argv[index - 1 : index + 2] == [flag, "android.intent.extra.alarm." + key, value]


def test_clock_timer_checks_prefs_without_idle_dump():
    h = helper("clock")
    dev = Device(prefs=fixture("clock-prefs.xml"))
    assert h.timer_running(dev, ctx({"seconds": 240, "label": "Tea"}))
    assert not h.timer_running(dev, ctx({"seconds": 300, "label": "Tea"}))
    assert not h.timer_running(dev, ctx({"seconds": 240, "label": "Coffee"}))
    dev.prefs = dev.prefs.replace('name="timer_state_0" value="1"', 'name="timer_state_0" value="2"')
    assert not h.timer_running(dev, ctx({"seconds": 240, "label": "Tea"}))


def test_clock_stopwatch_checks_prefs_without_idle_dump():
    h = helper("clock")
    dev = Device(prefs=fixture("clock-prefs.xml"))
    assert h.stopwatch_running(dev, ctx())
    dev.prefs = dev.prefs.replace('name="sw_state" value="1"', 'name="sw_state" value="2"')
    assert not h.stopwatch_running(dev, ctx())
    dev.prefs = "Permission denied"
    assert not h.stopwatch_running(dev, ctx())


def test_contacts_details_retains_untyped_number():
    h = helper("contacts")
    dev = Device(fixture("contacts-details.xml"))
    result = h.read_details(dev, {}, ctx())["data"]
    assert result["contact"]["phones"] == [{"type": "", "number": "+1 555 0100"}]
    assert h.details_ok(dev, ctx({"query": "Grace"}, result))
    result["contact"]["phones"] = []
    assert not h.details_ok(dev, ctx({"query": "Grace"}, result))


@pytest.mark.parametrize(
    "validator,result,params",
    [
        ("result_readable", {"display": "99", "value": 99}, {}),
        ("history_read", {"formulas": [], "results": []}, {}),
        (
            "conversion_done",
            {"input": 100, "value": 99, "from_unit": "Fahrenheit", "to_unit": "Celsius", "symbol": "°C"},
            {"value": "100", "from_unit": "Fahrenheit", "to_unit": "Celsius"},
        ),
    ],
)
def test_calculator_rejects_collected_values_that_disagree_with_device(validator, result, params):
    assert not getattr(helper("calculator"), validator)(Device(fixture("calculator.xml")), ctx(params, result))


@pytest.mark.parametrize("field,value", [("phone", "999"), ("email", "wrong@example.com")])
def test_contacts_saved_verifies_provider_fields(field, value):
    h = helper("contacts")
    dev = Device(fixture("contacts-details.xml"))
    params = {"name": "Grace Hopper", "phone": "+1 555 0100", "email": "grace@example.com"}
    assert h.contact_saved(dev, ctx(params))
    params[field] = value
    assert not h.contact_saved(dev, ctx(params))


@pytest.mark.parametrize("validator", ["list_ok", "search_ok"])
def test_contacts_empty_collection_rejected_when_provider_has_matches(validator):
    h = helper("contacts")
    assert not getattr(h, validator)(
        Device(fixture("contacts-search.xml")), ctx({"query": "Grace"}, {"contacts": [], "count": 0})
    )


def test_tasks_list_validator_reads_device(monkeypatch):
    h = helper("tasks")
    monkeypatch.setattr(h, "read_rows", lambda _: [{"title": "Buy milk", "notes": "", "section": ""}])
    assert not h.tasks_ok(Device(), ctx(result={"tasks": [], "count": 0}))


def test_markor_list_validator_reads_device():
    h = helper("markor")
    dev = Device(fixture("markor-folded.xml"))
    dev.adb_soft = lambda *a: SimpleNamespace(returncode=0, stdout="Recipe.md\nRecipe.md.bak\n")
    assert not h.notebook_listed(dev, ctx(result={"files": [], "folders": [], "count": 0}))


def test_clock_alarm_list_rejects_empty_collection_with_device_rows(monkeypatch):
    h = helper("clock")
    row = {"time": "07:30", "label": "Gym", "repeat": "", "enabled": True}
    monkeypatch.setattr(h, "read_alarm_rows", lambda _: [row])
    assert not h.alarms_listed(Device(), ctx(result={"alarms": [], "count": 0}))


def test_clock_alarm_must_be_enabled(monkeypatch):
    h = helper("clock")
    import time

    monkeypatch.setattr(time, "sleep", lambda _: None)
    monkeypatch.setattr(h, "read_alarm_rows", lambda _: [{"time": "07:30", "label": "Gym", "enabled": False}])
    assert not h.alarm_exists(Device(), ctx({"hour": 7, "minute": 30, "label": "Gym"}))


def test_calculator_zero_operand_does_not_evaluate_unused_division():
    assert helper("calculator").expected_value("2+0") == 2


def test_tasks_search_rejects_empty_collection_with_device_rows(monkeypatch):
    h = helper("tasks")
    monkeypatch.setattr(h, "read_rows", lambda _: [{"title": "Buy milk", "notes": "", "section": ""}])
    dev = TasksKeyboardDevice(query="milk", rows=False)
    dev.keyboard = False
    assert not h.search_ok(dev, ctx({"query": "milk"}, {"tasks": [], "count": 0}))


def test_calculator_accepts_fresh_display_history_and_conversion():
    h = helper("calculator")
    dev = Device(fixture("calculator.xml"))
    assert h.result_readable(dev, ctx(result={"display": "42", "value": 42}))
    assert h.history_read(dev, ctx(result={"formulas": ["6×7"], "results": ["42"]}))
    assert h.conversion_done(
        dev,
        ctx(
            {"value": "100", "from_unit": "Fahrenheit", "to_unit": "Celsius"},
            {"input": 100, "value": 37.777778, "from_unit": "Fahrenheit", "to_unit": "Celsius", "symbol": "°C"},
        ),
    )
    assert not h.history_read(Device("<hierarchy/>"), ctx(result={"formulas": [], "results": []}))


def test_contacts_empty_provider_allows_empty_results_and_errors_fail_closed():
    h = helper("contacts")
    dev = Device(fixture("contacts-search.xml"))
    dev.contacts = dev.data = "No result found."
    for name in ("list_ok", "search_ok"):
        assert getattr(h, name)(dev, ctx({"query": "Grace"}, {"contacts": [], "count": 0}))
        dev.contacts = "Permission Denial: requires READ_CONTACTS"
        with pytest.raises(ValueError, match="ContactsProvider"):
            getattr(h, name)(dev, ctx({"query": "Grace"}, {"contacts": [], "count": 0}))
        dev.contacts = "No result found."


def test_contacts_create_does_not_combine_fields_from_different_people():
    h = helper("contacts")
    dev = Device(fixture("contacts-details.xml"))
    dev.contacts += "Row: 3 _id=4, display_name=Grace Hopper\n"
    dev.data = dev.data.replace(
        "contact_id=1, mimetype=vnd.android.cursor.item/email_v2",
        "contact_id=4, mimetype=vnd.android.cursor.item/email_v2",
    )
    assert not h.contact_saved(dev, ctx({"name": "Grace Hopper", "phone": "+1 555 0100", "email": "grace@example.com"}))


def test_contacts_phone_search_preserves_matching_name(monkeypatch):
    h = helper("contacts")
    monkeypatch.setattr(h.time, "sleep", lambda _: None)
    dev = Device(fixture("contacts-search.xml"))
    assert h.search(dev, {"query": "5550100"}, ctx())["data"]["contacts"] == ["Grace Hopper"]


def test_markor_list_reads_folded_rows_and_rechecks_directory(monkeypatch):
    h = helper("markor")
    monkeypatch.setattr(h.time, "sleep", lambda _: None)
    dev = Device(fixture("markor-folded.xml"))
    dev.adb_soft = lambda *a: SimpleNamespace(returncode=0, stdout="Recipe.md\nRecipe.md.bak\n")
    result = h.list_notebook(dev, {}, ctx())["data"]
    assert set(result["files"]) == {"Recipe.md", "Recipe.md.bak"}
    assert h.notebook_listed(dev, ctx(result=result))
    dev.adb_soft = lambda *a: SimpleNamespace(returncode=1, stdout="")
    assert not h.notebook_listed(dev, ctx(result=result))


def test_clock_running_stopwatch_noop_never_dumps():
    h = helper("clock")
    dev = Device(prefs=fixture("clock-prefs.xml"))
    assert h.start_stopwatch(dev, {}, ctx())["success"]
    assert not any(e[0] == "tap" for e in dev.events)


def test_clock_reads_device_protected_preferences():
    h = helper("clock")
    dev = Device(prefs=fixture("clock-prefs.xml"))
    assert h.stopwatch_running(dev, ctx())
    assert "/data/user_de/0/com.google.android.deskclock/shared_prefs/" in dev.events[0][1]


@pytest.mark.parametrize(
    "action,params",
    [
        ("start_timer", {"seconds": 240, "label": "Tea"}),
        ("start_stopwatch", {}),
    ],
)
def test_clock_manifest_runs_without_idle_dump(monkeypatch, action, params):
    from gitd.skills.engine import runner
    from gitd.skills.engine.loader import load_skill

    dev = Device(prefs=fixture("clock-prefs.xml"))
    monkeypatch.setattr(runner, "_get_device", lambda _: dev)
    monkeypatch.setattr(runner.time, "sleep", lambda _: None)
    result = runner.run_action(load_skill(ROOT / "skillhub/ghost/clock"), action, params=params, device_serial="stub")
    assert result.success, result.error


def test_contacts_ambiguous_duplicate_cannot_hide_stored_numbers():
    h = helper("contacts")
    dev = Device(
        '<hierarchy><node resource-id="com.google.android.contacts:id/large_title" text="Grace Hopper" bounds="[0,100][600,200]" /></hierarchy>'
    )
    dev.contacts += "Row: 3 _id=4, display_name=Grace Hopper\n"
    # The second same-name contact has no data. It must not excuse a missing number
    # on the displayed contact when the UI does not expose the selected contact ID.
    result = h.read_details(dev, {}, ctx())["data"]
    assert not h.details_ok(dev, ctx({"query": "Grace"}, result))


class TasksKeyboardDevice(Device):
    """Captured terminal layout with explicitly reconstructed preceding state."""

    def __init__(self, query="bank", rows=True):
        super().__init__()
        self.query = query
        self.rows = rows
        self.keyboard = True
        self.scrolls = []

    def dump_xml(self):
        xml = fixture("tasks-search-keyboard.xml").replace('text="bank by"', f'text="{self.query}"')
        if self.rows and self.query == "bank":
            row = (
                '<node resource-id="org.tasks:id/rowBody" bounds="[0,400][1080,600]">'
                '<node resource-id="org.tasks:id/title" text="Call the bank" bounds="[100,420][900,480]" />'
                "</node>"
            )
            xml = xml.replace("</hierarchy>", row + "</hierarchy>")
        return xml

    def adb(self, *args):
        self.events.append(args)
        if args[-2:] == ("keyevent", "KEYCODE_BACK"):
            self.keyboard = False
        return ""

    def swipe(self, x1, y1, x2, y2, duration):
        self.scrolls.append((x1, y1, x2, y2))
        if self.keyboard and max(y1, y2) >= 1517:
            self.query = "bank by"


def test_tasks_search_preserves_query_through_collection_and_validation(monkeypatch):
    h = helper("tasks")
    monkeypatch.setattr(h.time, "sleep", lambda _: None)
    dev = TasksKeyboardDevice()
    result = h.search(dev, {"query": "bank"}, ctx())
    assert result["success"]
    assert result["data"]["tasks"] == [{"title": "Call the bank", "notes": "", "section": ""}]
    assert h.search_ok(dev, ctx({"query": "bank"}, result["data"]))
    assert dev.query == "bank"
    assert dev.scrolls


def test_tasks_search_rejects_wrong_query_even_when_both_reads_are_empty():
    h = helper("tasks")
    dev = TasksKeyboardDevice(query="bank by", rows=False)
    assert not h.search_ok(dev, ctx({"query": "bank"}, {"query": "bank", "tasks": [], "count": 0}))


def test_tasks_search_rejects_query_corruption_during_validator_rewind():
    h = helper("tasks")
    dev = TasksKeyboardDevice(rows=False)
    assert not h.search_ok(dev, ctx({"query": "bank"}, {"query": "bank", "tasks": [], "count": 0}))


def test_tasks_search_accepts_genuine_empty_result_under_unchanged_query():
    h = helper("tasks")
    dev = TasksKeyboardDevice(rows=False)
    dev.keyboard = False
    assert h.search_ok(dev, ctx({"query": "bank"}, {"query": "bank", "tasks": [], "count": 0}))


def test_tasks_search_validation_reveals_collapsed_query_toolbar(monkeypatch):
    h = helper("tasks")
    monkeypatch.setattr(h.time, "sleep", lambda _: None)

    class CollapsingToolbarDevice(Device):
        collapsed = False

        def dump_xml(self):
            return fixture("tasks-search-collapsed.xml" if self.collapsed else "tasks-search-expanded.xml")

        def swipe(self, x1, y1, x2, y2, duration):
            self.collapsed = y2 < y1

    dev = CollapsingToolbarDevice()
    params = {"query": "Showcase f2 tasks 20261023"}
    result = h.search(dev, params, ctx())
    assert result["success"]
    assert result["data"]["count"] == 1
    assert dev.collapsed  # Collection legitimately hides the query toolbar.
    assert h.search_ok(dev, ctx(params, result["data"]))
