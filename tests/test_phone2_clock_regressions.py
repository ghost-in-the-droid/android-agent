"""Samsung timer support stays within Timer, verifies duration and preserves active timers."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


def clock():
    p = Path(__file__).resolve().parents[1] / 'skillhub/ghost/clock/helpers.py'
    spec = importlib.util.spec_from_file_location('clock', p)
    h = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(h)
    return h


class SamsungTimer:
    def __init__(self):
        self.active = False
        self.minute = 0
        self.taps = []
        self.commands = []
    def adb(self, *args):
        self.commands.append(args)
        if args[:3] == ('shell', 'pm', 'path'):
            return 'package:/demo/clock.apk' if args[-1] == 'com.sec.android.app.clockpackage' else ''
        if args[:4] == ('shell', 'dumpsys', 'activity', 'services'):
            return '* ServiceRecord\nTimerService isForeground=false\n* ServiceRecord\nTimerNotificationService isForeground=' + ('true' if self.active else 'false')
        return ''
    def tap(self, x, y, *args):
        self.taps.append((x, y))
        if y < 1000:
            self.minute += 1
        elif x == 270:
            self.active = False
        else:
            self.active = True
    def nodes(self):
        prefix = 'com.sec.android.app.clockpackage:id/'
        def node(name, text, bounds):
            return {'id': prefix + name, 'text': text, 'desc': '', 'bounds': bounds}
        if self.active:
            return [node('timer_cancel_button', 'Cancel', (135, 1678, 405, 1954)),
                    node('timer_pause_button', 'Pause', (675, 1678, 945, 1954))]
        parent = node('timer_picker_view', '', (121, 328, 959, 981))
        parent['desc'] = f'0 Hour {self.minute} Minute 0 Second'
        return [parent, node('numberpicker_input', ', Hour', (121, 560, 331, 763)),
                node('numberpicker_input', f'{self.minute:02d}, Minute', (435, 560, 645, 763)),
                node('numberpicker_input', '00, Second', (749, 560, 959, 763)),
                node('timer_start_button', 'Start', (402, 1678, 678, 1954))]


def test_samsung_start_cancel_and_state_do_not_open_alarms(monkeypatch):
    h = clock()
    dev = SamsungTimer()
    monkeypatch.setattr(h, 'clock_snapshot', lambda d, package=None: d.nodes())
    ctx = SimpleNamespace(params={'seconds': 60}, result={})
    result = h.start_timer(dev, ctx.params, ctx)
    assert result['success']
    ctx.result.update(result['data'])
    assert h.timer_running(dev, ctx)
    cancelled = h.cancel_timer(dev, {}, ctx)
    assert cancelled['success']
    ctx.result.update(cancelled['data'])
    assert h.timer_cancelled(dev, ctx)
    assert h.get_timer_state(dev, {}, ctx)['data']['active'] is False
    assert all('SET_ALARM' not in str(c) for c in dev.commands)
    assert sum('android.intent.action.SHOW_TIMERS' in c for c in dev.commands) == 1


def test_samsung_existing_timer_is_preserved():
    h = clock()
    dev = SamsungTimer()
    dev.active = True
    result = h.start_timer(dev, {'seconds': 60}, SimpleNamespace(result={}))
    assert not result['success']
    assert dev.active and not dev.taps


def test_samsung_custom_label_is_not_silently_ignored():
    h = clock()
    dev = SamsungTimer()
    result = h.start_timer(dev, {'seconds': 60, 'label': 'Tea'}, SimpleNamespace(result={}))
    assert not result['success']
    assert not dev.taps


def test_samsung_cancel_uses_visible_control_when_service_report_lags(monkeypatch):
    h = clock()
    dev = SamsungTimer()
    dev.active = True
    monkeypatch.setattr(h, 'clock_snapshot', lambda d, package=None: d.nodes())
    monkeypatch.setattr(h, 'samsung_timer_active', lambda _: False)
    assert h.cancel_timer(dev, {}, SimpleNamespace(result={}))['success']
    assert not dev.active


def test_samsung_does_not_start_when_duration_readback_disagrees(monkeypatch):
    h = clock()
    dev = SamsungTimer()
    monkeypatch.setattr(h, 'clock_snapshot', lambda d, package=None: d.nodes())
    monkeypatch.setattr(dev, 'tap', lambda *args: None)
    ticks=SimpleNamespace(now=0.)
    monkeypatch.setattr(h,'time',SimpleNamespace(monotonic=lambda:ticks.now,sleep=lambda dt:setattr(ticks,'now',ticks.now+dt)))
    result = h.start_timer(dev, {'seconds': 60}, SimpleNamespace(result={}))
    assert not result['success'] and not dev.active
    assert not any(y >= 1000 for x,y in dev.taps)


def test_samsung_canvas_values_require_authoritative_native_summary():
    h=clock();dev=SamsungTimer();nodes=dev.nodes()
    for n in nodes:
        if n['id'].endswith('numberpicker_input'):n['text']=', Minute'
    nodes[0]['desc']='0 Hour 1 Minute 0 Second'
    assert h.timer_picker(nodes)[1]==[0,1,0]
    assert h.timer_picker(nodes[1:]) is None


def test_samsung_conflicting_or_out_of_range_native_values_are_rejected():
    h=clock();nodes=SamsungTimer().nodes();nodes[0]['desc']='0 Hour 1 Minute 0 Second'
    assert h.timer_picker(nodes) is None
    nodes[0]['desc']='0 Hour 60 Minute 0 Second'
    assert h.timer_picker(nodes) is None


def test_samsung_waits_for_delayed_accessibility_readback(monkeypatch):
    h=clock();dev=SamsungTimer();stale=dev.nodes();lag=SimpleNamespace(remaining=1)
    def snapshot(*_):
        if dev.minute and not dev.active and lag.remaining:
            lag.remaining-=1
            return stale
        return dev.nodes()
    monkeypatch.setattr(h,'clock_snapshot',snapshot)
    assert h.start_timer(dev,{'seconds':60},SimpleNamespace(result={}))['success']
    assert dev.active and dev.minute==1


def test_samsung_cold_picker_settles_before_input(monkeypatch):
    h=clock();dev=SamsungTimer();ticks=SimpleNamespace(now=0.)
    monkeypatch.setattr(h,'time',SimpleNamespace(monotonic=lambda:ticks.now,sleep=lambda dt:setattr(ticks,'now',ticks.now+dt)))
    def snapshot(*_):
        ticks.now+=.2
        return dev.nodes()
    original=dev.tap
    def tap(*args):
        if ticks.now>=.5:original(*args)
    monkeypatch.setattr(dev,'tap',tap);monkeypatch.setattr(h,'clock_snapshot',snapshot)
    assert h.start_timer(dev,{'seconds':60},SimpleNamespace(result={}))['success']
    assert dev.active and dev.minute==1


@pytest.mark.parametrize('choice,expected', [('auto', 'com.sec.android.app.clockpackage'), ('google', 'com.google.android.deskclock')])
def test_clock_detects_installed_variants(choice, expected):
    h = clock()
    dev = SimpleNamespace(adb=lambda *args: 'package:/demo/clock.apk')
    assert h.clock_package(dev, choice) == expected

@pytest.mark.parametrize('active', [True, False])
def test_samsung_cancel_never_taps_ringing_alarm_controls(monkeypatch,active):
    h=clock();d=SamsungTimer();d.active=active
    alarm=[{'id':'com.sec.android.app.clockpackage:id/alarm_alert_dismiss','text':'Dismiss','desc':'','bounds':(100,100,500,500)},
           {'id':'com.sec.android.app.clockpackage:id/alarm_cancel_button','text':'Cancel','desc':'','bounds':(100,600,500,900)}]
    monkeypatch.setattr(h,'clock_snapshot',lambda *_:alarm)
    result=h.cancel_timer(d,{},SimpleNamespace(result={}))
    assert not d.taps and d.active==active
    assert result['success'] is (not active)
