"""Cross-device regressions: narrow layouts, slow dialogs and unprivileged devices."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


def helper(ref):
    spec = importlib.util.spec_from_file_location(ref.replace("/", "_"), ROOT / "skillhub" / ref / "helpers.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def context(params=None, result=None):
    return SimpleNamespace(params=params or {}, result=result or {})


class XMLDevice:
    def __init__(self, xml):
        self.xml = xml
        self.taps = []

    def dump_xml(self, **kwargs):
        return self.xml

    def tap(self, x, y, *args):
        self.taps.append((x, y))


@pytest.mark.parametrize("width", [720, 1080])
def test_clock_reads_enabled_alarm_on_both_screen_widths(width):
    h = helper("ghost/clock")
    dev = XMLDevice(f'''<hierarchy><node content-desc="07:30 Demo" bounds="[10,100][{width - 10},400]">
      <node resource-id="{h._ID}digital_clock" text="07:30" bounds="[30,140][200,210]" />
      <node resource-id="{h._ID}label" text="Demo" bounds="[30,110][200,130]" />
      <node resource-id="{h._ID}onoff" checked="true" bounds="[{width - 100},220][{width - 30},280]" />
    </node></hierarchy>''')
    assert h.read_alarm_rows(dev) == [{"time": "07:30", "label": "Demo", "repeat": "", "enabled": True}]


def test_unit_picker_waits_for_dialog_and_accepts_identified_options(monkeypatch):
    h = helper("ghost/calculator")
    monkeypatch.setattr(h.time, "sleep", lambda _: None)
    holder = {"id": h._ID + "top_unit_name", "text": "Celsius", "bounds": (0, 100, 200, 150)}
    option = {"id": "android:id/text1", "text": "Fahrenheit", "bounds": (0, 200, 300, 260)}
    states = iter([[holder], [holder], [option]])
    monkeypatch.setattr(h, "visible_nodes", lambda _: next(states, [option]))
    dev = XMLDevice("")
    dev.back = lambda *_: None
    h._pick_unit(dev, "top_unit_name", "Fahrenheit")
    assert dev.taps[-1] == (150, 230)


def test_markor_refuses_mismatched_filename_before_saving(monkeypatch):
    h = helper("ghost/markor")
    monkeypatch.setattr(h.time, "sleep", lambda _: None)
    dev = XMLDevice("""<hierarchy><node resource-id="net.gsantner.markor:id/new_file_dialog__name"
       text="Dropped prefix" bounds="[0,100][400,200]" /></hierarchy>""")
    dev.adb = lambda *args: ""
    result = h.type_title(dev, {"title": "Requested title"}, context())
    assert not result["success"]
    assert "title" in result["error"].lower()


def test_tasks_missing_systemui_field_does_not_block_confirmed_app_control(monkeypatch):
    h = helper("ghost/tasks")
    monkeypatch.setattr(h.time, "sleep", lambda _: None)
    dev = XMLDevice("""<hierarchy><node package="org.tasks" content-desc="Save"
       bounds="[0,50][60,110]" /></hierarchy>""")
    dev.adb = lambda *args: (
        "mCurrentFocus=Window{a u0 org.tasks/.activities.TaskEditActivity}" if "window" in " ".join(args) else ""
    )
    node = {"id": "", "desc": "Save", "bounds": (0, 50, 60, 110)}
    assert h.guarded_top_tap(dev, node, wait_s=0)
    assert dev.taps == [(30, 80)]


def test_tasks_unknown_focus_or_notification_never_taps(monkeypatch):
    h = helper("ghost/tasks")
    monkeypatch.setattr(h.time, "sleep", lambda _: None)
    dev = XMLDevice("<hierarchy/>")
    dev.adb = lambda *args: ""
    assert not h.guarded_top_tap(dev, {"id": "", "desc": "Save", "bounds": (0, 50, 60, 110)}, wait_s=0)
    assert not dev.taps


@pytest.mark.parametrize(
    "ref", ["ghost/calculator", "ghost/clock", "ghost/markor", "ghost/tasks", "androidworld/pro-expense"]
)
def test_showcase_skill_loads_with_private_review_assets(ref):
    from gitd.skills.engine.loader import load_skill

    assert load_skill(ROOT / "skillhub" / ref).name == ref.split("/")[-1]


def clock_node(name, text="", desc=""):
    return {"id": "com.google.android.deskclock:id/" + name, "text": text, "desc": desc, "bounds": (0, 0, 100, 100)}


def timer_nodes(value="4:58", label="Tea", control="Pause"):
    return [clock_node("timer_label", label), clock_node("timer_text", value), clock_node("play_pause", desc=control)]


@pytest.mark.parametrize("second,expected", [("4:56", True), ("4:58", False), ("4:59", False), ("−0:01", False)])
def test_unrooted_timer_requires_advancing_countdown(monkeypatch, second, expected):
    h = helper("ghost/clock")
    monkeypatch.setattr(h, "_clock_prefs", lambda _: {})
    monkeypatch.setattr(h, "show_clock_tab", lambda *_: timer_nodes())
    monkeypatch.setattr(h, "clock_snapshot", lambda _: timer_nodes(second))
    monkeypatch.setattr(h.time, "sleep", lambda _: None)
    monkeypatch.setattr(h.time, "monotonic", lambda: 10)
    ctx = context({"seconds": 300, "label": "Tea"})
    ctx.timer_started_at = 5
    assert h.timer_running(None, ctx) is expected


@pytest.mark.parametrize(
    "nodes",
    [timer_nodes(label="Coffee"), timer_nodes(control="Start"), timer_nodes() + [clock_node("timer_label", "Other")]],
)
def test_unrooted_timer_rejects_wrong_label_paused_and_ambiguous_pages(nodes):
    assert helper("ghost/clock").timer_ui_state(nodes, {"label": "Tea"}) is None


def test_stopwatch_requires_pause_and_increasing_measured_time(monkeypatch):
    h = helper("ghost/clock")
    monkeypatch.setattr(h, "_clock_prefs", lambda _: {})
    monkeypatch.setattr(h.time, "sleep", lambda _: None)

    def screen(seconds):
        return [
            clock_node("stopwatch_time_text", seconds),
            clock_node("stopwatch_hundredths_text", "45"),
            clock_node("fab", desc="Pause"),
        ]

    states = iter([screen("00"), screen("02")])
    monkeypatch.setattr(h, "clock_snapshot", lambda _: next(states))
    assert h.stopwatch_running(None, context())
    monkeypatch.setattr(h, "clock_snapshot", lambda _: screen("02"))
    assert not h.stopwatch_running(None, context())
    assert h.stopwatch_ui_state(screen("02")[:-1]) is None


def test_clock_snapshot_missing_marker_fails_closed_and_removes_only_its_jar():
    h = helper("ghost/clock")

    class Device:
        calls = []

        def adb(self, *args):
            self.calls.append(args)
            return "INSTRUMENTATION_FAILED: permission denied"

    dev = Device()
    assert h.clock_snapshot(dev) == []
    pushed = dev.calls[0][-1]
    assert pushed.startswith("/data/local/tmp/ghost-clock-")
    assert dev.calls[-1] == ("shell", "rm", "-f", pushed)


def expense_editor(h, *, amount="4.50", note="Receipt", category="Food", checked=True, update="UPDATE"):
    def n(rid, text="", bounds=(0, 100, 300, 200), **kw):
        return {"id": h._ID + rid, "text": text, "desc": "", "bounds": bounds, **kw}

    return [
        n("edt_name", "Coffee"),
        n("edt_amount", amount),
        n("edt_note", note),
        n("btn_save", update),
        n("cd_category", bounds=(0, 300, 200, 400), checked=checked),
        n("tv_name", category, bounds=(10, 310, 190, 390)),
    ]


def test_expense_unrooted_editor_reads_persisted_fields_and_checked_card(monkeypatch):
    h = helper("androidworld/pro-expense")
    monkeypatch.setattr(h, "nodes", lambda _, **kw: expense_editor(h))
    assert h.saved_editor_row(None) == ("Coffee", 450, 3, "Receipt")
    monkeypatch.setattr(h, "nodes", lambda _, **kw: expense_editor(h, category="Income", amount="9", note="Other"))
    assert h.saved_editor_row(None) == ("Coffee", 900, 2, "Other")


@pytest.mark.parametrize("overrides", [{"checked": False}, {"update": "SAVE"}, {"category": "Unknown"}])
def test_expense_editor_cannot_prove_category_from_an_unchecked_label(monkeypatch, overrides):
    h = helper("androidworld/pro-expense")
    monkeypatch.setattr(h, "nodes", lambda _, **kw: expense_editor(h, **overrides))
    assert h.saved_editor_row(None) is None


def test_expense_successful_sqlite_read_remains_authoritative(monkeypatch):
    h = helper("androidworld/pro-expense")
    monkeypatch.setattr(h, "ledger", lambda _: [("Coffee", 450, 3, "Receipt")])
    monkeypatch.setattr(h, "saved_rows_visible", lambda *_: pytest.fail("must not bypass a readable ledger"))
    row = {"name": "Coffee", "amount": "4.50", "category": "Food", "note": "Receipt"}
    assert h.rows_present(None, [row])
    for key, value in [("amount", "9"), ("category", "Income"), ("note", "Other"), ("name", "Other")]:
        assert not h.rows_present(None, [{**row, key: value}])


def test_timer_scopes_controls_to_matching_card_instead_of_old_timer():
    h = helper("ghost/clock")

    def shifted(rows, dy):
        return [
            {**n, "bounds": (n["bounds"][0], n["bounds"][1] + dy, n["bounds"][2], n["bounds"][3] + dy)} for n in rows
        ]

    old = timer_nodes("−0:30", label="Old")
    new = shifted(timer_nodes("4:58"), 200)
    cards = [clock_node("timer_background"), {**clock_node("timer_background"), "bounds": (0, 200, 100, 300)}]
    assert h.timer_ui_state(old + new + cards, {"label": "Tea"}) == 298
    assert h.timer_ui_state(old + new + cards, {"label": "Missing"}) is None
    assert h.timer_ui_state(new + new + cards, {"label": "Tea"}) is None


def test_tasks_overlay_over_save_is_not_tapped(monkeypatch):
    h = helper("ghost/tasks")
    monkeypatch.setattr(h.time, "sleep", lambda _: None)
    dev = XMLDevice("""<hierarchy><node package="org.tasks" content-desc="Save" bounds="[0,50][60,110]"/>
      <node package="com.android.systemui" bounds="[0,40][720,220]"/></hierarchy>""")
    dev.adb = lambda *args: (
        "mCurrentFocus=Window{a u0 org.tasks/.activities.TaskEditActivity}" if "window" in " ".join(args) else ""
    )
    assert not h.guarded_top_tap(dev, {"id": "", "desc": "Save", "bounds": (0, 50, 60, 110)}, wait_s=0)
    assert not dev.taps


def test_markor_retries_only_unsaved_filename_when_ime_drops_prefix(monkeypatch):
    h = helper("ghost/markor")
    monkeypatch.setattr(h.time, "sleep", lambda _: None)

    def field(text):
        return [{"id": h._ID + "new_file_dialog__name", "text": text, "bounds": (0, 100, 400, 200), "focused": True}]

    states = iter([field(""), field(""), field("title"), field("title"), field("title"), field("Requested title")])
    monkeypatch.setattr(h, "visible_nodes", lambda _, **kw: next(states))
    dev = XMLDevice("")
    calls = []
    dev.adb = lambda *args: calls.append(args)
    assert h.type_title(dev, {"title": "Requested title"}, context())["success"]
    assert sum(call[:3] == ("shell", "input", "text") for call in calls) == 2
    assert all("KEYCODE_ENTER" not in call for call in calls)


def test_clock_snapshot_discards_offscreen_pager_and_foreign_nodes():
    h = helper("ghost/clock")
    xml = """<?xml version="1.0"?><hierarchy><node package="com.google.android.deskclock" bounds="[0,0][720,1500]">
      <node package="com.google.android.deskclock" resource-id="visible" checked="true" bounds="[0,100][300,200]"/>
      <node package="com.google.android.deskclock" resource-id="offscreen" bounds="[720,100][1000,200]"/>
      <node package="com.android.systemui" resource-id="foreign" bounds="[0,100][300,200]"/>
    </node></hierarchy>"""

    class Device:
        def adb(self, *args):
            return "CLOCK_XML:" + xml.replace("\n", "") if "runtest" in args else ""

    assert [n["id"] for n in h.clock_snapshot(Device())] == ["", "visible"]
    assert h.clock_snapshot(Device())[1]["checked"] is True


@pytest.mark.parametrize("field,value", [("name", "a" * 21), ("note", "n" * 101), ("amount", "123456789.01")])
def test_expense_overlong_fields_fail_before_any_row_is_added(monkeypatch, field, value):
    h = helper("androidworld/pro-expense")
    monkeypatch.setattr(h, "add_row", lambda *_: pytest.fail("must reject truncation before writing"))
    row = {"name": "Coffee", "amount": "4.50", "category": "Food", "note": "Receipt", field: value}
    with pytest.raises(ValueError, match="field limit"):
        h.add_rows(None, {"rows": [row]}, context())


def test_markor_rating_prompt_declines_without_opening_store(monkeypatch):
    from gitd.bots.common.adb import Device
    from gitd.skills.engine.loader import load_skill

    skill = load_skill(ROOT / 'skillhub/ghost/markor')
    device = Device('rating-test')
    taps = []
    monkeypatch.setattr(device, 'tap', lambda x, y, **kw: taps.append((x, y)))
    xml = '''<hierarchy><node text="Hey there! You seem to like this app, would you mind visiting the Play Store"/>
      <node text="NO THANKS" bounds="[0,800][200,900]"/>
      <node text="RATE!" bounds="[500,800][700,900]"/></hierarchy>'''
    assert device.dismiss_popups(xml, skill.popup_detectors, generic=False)
    assert taps == [(100, 850)]


@pytest.mark.parametrize('overlay', [False, True])
def test_tasks_compose_target_needs_unobscured_focused_window(monkeypatch, overlay):
    h = helper('ghost/tasks')
    target = {'id': '', 'desc': 'Save', 'bounds': (31, 83, 76, 128)}
    dev = XMLDevice('<hierarchy/>')
    windows = f'''Window #0 Window{{aaa u0 StatusBar}}:
      package=com.android.systemui
      isVisible=true
      Frames: frame=[0,0][720,{200 if overlay else 45}]
    Window #1 Window{{bbb u0 org.tasks/.Editor}}:
      package=org.tasks
      isVisible=true
      Frames: frame=[0,45][720,1510]
    '''
    dev.adb = lambda *a: windows if 'windows' in ' '.join(a) else 'mCurrentFocus=Window{bbb u0 org.tasks/.Editor}'
    monkeypatch.setattr(h, 'visible_nodes', lambda _: [target])
    assert h.app_control_exposed(dev, target) is (not overlay)


def test_clock_real_device_reads_app_scoped_snapshot_without_idle_dump(monkeypatch):
    h = helper('ghost/clock')
    dev = XMLDevice('<hierarchy/>')
    dev.serial = 'test-clock'
    dev.dump_xml = lambda **kw: pytest.fail('an expired timer prevents idle dumps')
    expected = [clock_node('digital_clock', '07:30')]
    monkeypatch.setattr(h, 'clock_snapshot', lambda _: expected)
    assert h.visible_nodes(dev) == expected


def test_clock_city_search_result_alone_is_not_a_saved_city(monkeypatch):
    h = helper('ghost/clock')
    monkeypatch.setattr(h, 'visible_nodes', lambda _: [clock_node('city_name', 'Tokyo')])
    assert not h.city_listed(None, context({'city': 'Tokyo'}))


def test_clock_adding_existing_city_does_not_toggle_it_off(monkeypatch):
    h = helper('ghost/clock')
    ns = [clock_node('fab', desc='Add city'), clock_node('city_name', 'Tokyo')]
    monkeypatch.setattr(h, 'show_clock_tab', lambda *_: ns)
    monkeypatch.setattr(h, 'tap_clock_control', lambda *a, **kw: pytest.fail('existing city must not be toggled'))
    assert h.add_world_city(None, {'city': 'Tokyo'}, context())['success']


def test_clock_city_selection_restores_list_after_timer_interrupt(monkeypatch):
    h = helper('ghost/clock')
    screens = []
    monkeypatch.setattr(h, 'show_clock_tab', lambda d, tab: screens.append(tab) or [clock_node('fab', desc='Add city')])
    monkeypatch.setattr(h, 'tap_clock_control', lambda *a, **kw: None)
    monkeypatch.setattr(h, 'clock_control', lambda *a, **kw: pytest.fail('timer may interrupt; restore the city tab'))
    device = SimpleNamespace(adb=lambda *a: '')
    assert h.add_world_city(device, {'city':'London'}, context())['success']
    assert screens == ['clock', 'clock']


def test_markor_filename_uses_fresh_native_field_when_portal_lags(monkeypatch):
    h = helper('ghost/markor')
    monkeypatch.setattr(h.time, 'sleep', lambda _: None)

    class Device:
        value = ''
        writes = 0

        def dump_portal_json(self):
            return {'resourceId': h._ID + 'new_file_dialog__name', 'text':'',
                    'boundsInScreen': {'left':0,'top':0,'right':100,'bottom':50}}

        def dump_xml(self, **kw):
            assert kw.get('use_portal') is False
            return f'<hierarchy><node resource-id="{h._ID}new_file_dialog__name" text="{self.value}" focused="true" bounds="[0,0][100,50]"/></hierarchy>'

        def tap(self, *args):
            pass

        def adb(self, *args):
            if args[:3] == ('shell', 'input', 'text'):
                self.value += args[-1]
                self.writes += 1

    device = Device()
    assert h.type_title(device, {'title':'Shopping'}, context())['success']
    assert device.value == 'Shopping' and device.writes == 1


def test_markor_name_focus_is_required_before_any_text_input(monkeypatch):
    h = helper('ghost/markor')
    monkeypatch.setattr(h.time, 'sleep', lambda _: None)
    field = {'id':h._ID+'new_file_dialog__name','text':'','bounds':(0,100,400,200),'focused':False}
    monkeypatch.setattr(h, 'visible_nodes', lambda *a, **kw:[field])
    dev = XMLDevice('')
    dev.adb = lambda *a: pytest.fail('must not type into another focused field')
    assert not h.type_title(dev, {'title':'Shopping'}, context())['success']


def test_markor_notebook_deduplicates_title_and_row_description(monkeypatch):
    h = helper('ghost/markor')
    monkeypatch.setattr(h.time, 'sleep', lambda _:None)
    nodes = [{'id':h._ID+'opoc_filesystem_item__title','text':'Shopping.md','desc':'','bounds':(0,100,400,200)},
             {'id':h._ID+'opoc_filesystem_item__root','text':'','desc':'File Shopping.md 24/10/2026, 01:00','bounds':(0,100,400,200)}]
    monkeypatch.setattr(h, 'visible_nodes', lambda _:nodes)
    dev = SimpleNamespace(swipe=lambda *a:None)
    assert h.list_notebook(dev, {}, context())['data'] == {'files':['Shopping.md'],'folders':[],'count':1}
