"""Theme validation reads system state, including on Samsung's radio layout."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


def settings():
    path = Path(__file__).resolve().parents[1] / 'skillhub/ghost/settings/helpers.py'
    spec = importlib.util.spec_from_file_location('settings', path)
    h = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(h)
    return h


@pytest.mark.parametrize('enabled', [True, False])
def test_theme_sets_and_reads_back_system_state_without_oem_switch(enabled):
    h = settings()
    class Device:
        state = not enabled
        def adb(self, *args):
            assert args[:4] == ('shell', 'cmd', 'uimode', 'night')
            if len(args) == 5:
                self.state = args[4] == 'yes'
            return 'Night mode: ' + ('yes' if self.state else 'no')
    d = Device()
    result = h.set_dark_theme(d, {'enabled': enabled}, None)
    assert result['success']
    ctx = SimpleNamespace(params={'enabled': enabled}, result=result['data'])
    assert h.dark_theme_matches(d, ctx)
    d.state = not enabled
    assert not h.dark_theme_matches(d, ctx)


def test_theme_does_not_claim_success_when_shell_state_cannot_be_read(monkeypatch):
    h = settings()
    monkeypatch.setattr(h.time, 'sleep', lambda _: None)
    d = SimpleNamespace(adb=lambda *args: 'Unknown command')
    result = h.set_dark_theme(d, {'enabled': True}, None)
    assert not result['success']

@pytest.mark.parametrize('mode', ['auto', 'custom'])
def test_theme_preserves_existing_automatic_schedule(mode):
    h = settings()
    class Device:
        def adb(self, *args):
            assert args == ('shell', 'cmd', 'uimode', 'night'), 'Automatic schedule must never be overwritten'
            return 'Night mode: ' + mode
    result = h.set_dark_theme(Device(), {'enabled': True}, None)
    assert not result['success'] and 'preserved' in result['error']

class AggregateDevice:
    def __init__(self, output):
        self.output = output
        self.commands = []

    def adb(self, *args):
        self.commands.append(args)
        assert args[0] == 'shell'
        return self.output


def test_device_info_reads_only_three_non_unique_properties():
    h = settings()
    values = {'ro.product.model': 'SM-A156B', 'ro.build.version.release': '16',
              'ro.build.display.id': 'TEST.BUILD'}
    class Device:
        def adb(self, *args):
            assert args[:2] == ('shell', 'getprop') and len(args) == 3
            return values[args[2]]
    r = h.read_device_info(Device(), {}, None)
    assert r['success'] and r['data'] == {'device_info': {
        'model': 'SM-A156B', 'android_version': '16', 'build_number': 'TEST.BUILD'}}


@pytest.mark.parametrize('raw,expected', [
    ('level: 50\nscale: 100\nstatus: 2', {'level_percent': 50, 'charging': True}),
    ('level: 100\nscale: 100\nstatus: 5', {'level_percent': 100, 'charging': False}),
    ('level: 20\nscale: 40\nstatus: 3', {'level_percent': 50, 'charging': False}),
    ('level: 50\nscale: 0\nstatus: 2', None),
    ('level: 200\nscale: 100\nstatus: 2', None),
    ('level: 50\nscale: 100\nstatus: 1', None),
    ('permission denied', None),
])
def test_battery_aggregates_reject_unknown_or_impossible_values(raw, expected):
    h = settings(); d = AggregateDevice(raw)
    r = h.read_battery(d, {}, None)
    assert r['success'] is (expected is not None)
    if expected is not None:
        assert r['data'] == {'battery': expected}
    assert d.commands == [('shell', h.BATTERY_STATUS)]


@pytest.mark.parametrize('raw,expected', [
    ('1000 300 600', {'total_kib': 1000, 'used_kib': 300, 'free_kib': 600}),
    ('0 0 0', None), ('100 99 50', None), ('/data 100 20 70', None),
])
def test_storage_totals_only_and_consistency(raw, expected):
    h = settings(); d = AggregateDevice(raw)
    r = h.read_storage(d, {}, None)
    assert r['success'] is (expected is not None)
    if expected is not None:
        assert r['data'] == {'storage': expected}
    assert d.commands == [('shell', h.STORAGE_TOTALS)]


@pytest.mark.parametrize('raw,expected', [
    ('enabled=true\nconnected=true', {'enabled': True, 'connected': True}),
    ('enabled=true\nconnected=false', {'enabled': True, 'connected': False}),
    ('enabled=false', {'enabled': False, 'connected': False}),
    ('enabled=true', None), ('', None),
    ('enabled=true\nenabled=false\nconnected=true', None),
    ('enabled=false\nconnected=true', None),
])
def test_wifi_unknown_conflicting_and_disabled_states(raw, expected):
    h = settings(); d = AggregateDevice(raw)
    r = h.read_wifi(d, {}, None)
    assert r['success'] is (expected is not None)
    if expected is not None:
        assert r['data'] == {'wifi': expected}
    assert d.commands == [('shell', h.WIFI_STATUS)]


def test_native_filters_drop_identifier_fields_before_adb_returns():
    import subprocess
    import shlex
    h = settings()
    examples = [
        (h.WIFI_STATUS, 'Wifi is enabled\nWifiInfo: SSID: private-test-network, BSSID: aa:bb:cc:dd:ee:ff, IP: /192.0.2.1, Supplicant state: COMPLETED\n',
         {'enabled=true', 'connected=true'}),
        (h.BATTERY_STATUS, '  level: 50\n  scale: 100\n  status: 2\n  serial: private-test-serial\n',
         {'level: 50', 'scale: 100', 'status: 2'}),
        (h.STORAGE_TOTALS, 'Filesystem 1K-blocks Used Available Use% Mounted on\n/private-volume 1000 300 600 30% /data\n',
         {'1000 300 600'}),
    ]
    for command, raw, expected in examples:
        # Execute exactly the shell filter used on Android against synthetic input.
        filtered = command.split('|', 1)[1]
        out = subprocess.check_output(['sh', '-c', 'printf %s ' + shlex.quote(raw) + ' | ' + filtered], text=True)
        assert set(out.splitlines()) == expected


def test_read_manifests_have_no_settings_page_or_accessibility_steps():
    import yaml
    path = Path(__file__).resolve().parents[1] / 'skillhub/ghost/settings/skill.yaml'
    d = yaml.safe_load(path.read_text())
    assert d['version'] == '1.1.0'
    for action in d['actions'][:4]:
        assert len(action['steps']) == 1
        assert set(action['steps'][0]) == {'python_action'}
