"""Fingerprint distance: version ranges, field matching, the run rule, CLI/MCP wiring, doctor <ref>."""
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from gitd.skills.engine import cli, fingerprint
from gitd.skills.engine.fingerprint import Distance, check, distance, field_matches, version_matches
from gitd.skills.engine.loader import Fingerprint
from gitd.skills.engine.runner import RunResult

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / 'tests/fixtures/fake_google_maps'   # android 14, Fixture/GoogleMaps, maps 25.0.0


@pytest.mark.parametrize('spec, actual, expected', [
    ('*', 'anything', True), ('', '9', True),
    ('14', '14', True), ('14', '14.1', True), ('14.1', '14', False), ('1.4.0', '1.4.0', True), ('1.4.0', '1.4.1', False),
    ('>=14', '14', True), ('>=14', '13', False), ('>=1.4.0', '1.10.2', True), ('>=1.4.0', '1.4', True),
    ('>=14 <16', '15', True), ('>=14 <16', '16', False), ('>=14, <16', '15.1', True),
    ('^1.4', '1.9.9', True), ('^1.4', '2.0.0', False), ('^0.2', '0.2.9', True), ('^0.2', '0.3.0', False),
    ('~1.4', '1.4.7', True), ('~1.4', '1.5.0', False),
    ('1.x', '1.42.0', True), ('1.x', '2.0', False), ('25.*', '25.0.0', True),
    ('>=14', 'unknown', False), ('>=14', '', False),
])
def test_version_matches(spec, actual, expected):
    assert version_matches(spec, actual) is expected


def test_field_matches_hardware_wildcards_and_case():
    assert field_matches('hardware', '*', 'Google/Pixel 6')
    assert field_matches('hardware', 'google/*', 'Google/Pixel 6')
    assert field_matches('hardware', 'Google/Pixel 6', 'google/pixel 6')
    assert not field_matches('hardware', 'ASUS/ROG', 'Google/Pixel 6')
    assert field_matches('app_package', 'org.fossify.math', 'org.fossify.math')
    assert not field_matches('app_package', 'org.fossify.math', 'org.fossify.calculator')
    assert field_matches('os', 'android', 'Android')


def test_distance_counts_mismatches_and_tiers():
    skill = Fingerprint(os='android', os_version='>=14', hardware='*', app_package='org.fossify.math', app_version='>=1.4.0')
    hit = distance(skill, {'os': 'android', 'os_version': '15', 'hardware': 'Google/Pixel', 'app_package': 'org.fossify.math', 'app_version': '1.6.0'})
    assert (hit.distance, hit.tier, hit.mismatches) == (0, 'hit', [])
    warn = distance(skill, {'os': 'android', 'os_version': '13', 'hardware': 'Google/Pixel', 'app_package': 'org.fossify.math', 'app_version': '1.2.0'})
    assert (warn.distance, warn.tier, warn.mismatches) == (2, 'warn', ['os_version', 'app_version'])
    assert "os_version: skill '>=14' vs device '13'" in warn.summary()
    refuse = distance({'os': 'ios', 'app_package': 'other'}, {'os': 'android', 'os_version': '14', 'hardware': 'x/y', 'app_package': 'org.fossify.math', 'app_version': '1'})
    assert refuse.distance == 2 and refuse.skill['os_version'] == '*'   # dict skill with missing fields = wildcards
    far = distance(Fingerprint(os='ios', os_version='17', hardware='Apple/iPhone', app_package='a', app_version='1'),
                   {'os': 'android', 'os_version': '14', 'hardware': 'Google/Pixel', 'app_package': 'b', 'app_version': '2'})
    assert far.distance == 5 and far.tier == 'refuse'
    assert far.as_dict()['mismatches'] == list(fingerprint.FIELDS)


def _skill(**fp):
    return SimpleNamespace(fingerprint=Fingerprint(**fp))


def test_check_probes_fake_devices_and_applies_the_rule():
    serial = 'fake:' + str(FIXTURE)
    hit = check(_skill(app_package='com.google.android.apps.maps', os_version='>=14'), serial)
    assert hit.distance == 0 and hit.device['hardware'] == 'Fixture/GoogleMaps'
    warn = check(_skill(app_package='com.google.android.apps.maps', os_version='>=15', app_version='26.x'), serial)
    assert warn.tier == 'warn'
    with pytest.raises(ValueError, match='--strict-fingerprint'):
        check(_skill(app_package='com.google.android.apps.maps', os_version='>=15'), serial, strict=True)
    far = _skill(os='android', os_version='>=15', hardware='ASUS/ROG', app_package='com.google.android.apps.maps', app_version='26.x')
    with pytest.raises(ValueError, match='--force-fingerprint'):
        check(far, serial)
    assert check(far, serial, force=True).tier == 'refuse'


def test_check_tolerates_unprobeable_devices_unless_strict(monkeypatch):
    skill = _skill(app_package='org.fossify.math')
    assert check(skill, 'ios:abc') is None
    with pytest.raises(ValueError, match='cannot be probed'):
        check(skill, 'ios:abc', strict=True)
    monkeypatch.setattr(fingerprint, 'probe_device', lambda serial, package: (_ for _ in ()).throw(RuntimeError('adb: device offline')))
    assert check(skill, 'emulator-5554') is None
    with pytest.raises(ValueError, match='device offline'):
        check(skill, 'emulator-5554', strict=True)
    supplied = {'os': 'android', 'os_version': '14', 'hardware': 'X/Y', 'app_package': 'org.fossify.math', 'app_version': '1'}
    assert check(skill, 'emulator-5554', device_fingerprint=supplied).distance == 0


def test_probe_device_reads_adb(monkeypatch):
    answers = {('dumpsys', 'package', 'org.fossify.math'): '  versionName=1.4.0\n', ('getprop', 'ro.build.version.release'): '14',
               ('getprop', 'ro.product.manufacturer'): 'Google', ('getprop', 'ro.product.model'): 'Pixel 6'}
    def fake_run(args, **kwargs):
        assert args[:4] == ['adb', '-s', 'emulator-5554', 'shell']
        return SimpleNamespace(stdout=answers[tuple(args[4:])])
    monkeypatch.setattr(fingerprint.subprocess, 'run', fake_run)
    assert fingerprint.probe_device('emulator-5554', 'org.fossify.math') == {
        'os': 'android', 'os_version': '14', 'hardware': 'Google/Pixel 6', 'app_package': 'org.fossify.math', 'app_version': '1.4.0'}
    answers[('dumpsys', 'package', 'org.fossify.math')] = ''
    assert fingerprint.probe_device('emulator-5554', 'org.fossify.math')['app_version'] == ''


@pytest.fixture
def maps_skill(tmp_path, monkeypatch):
    skill = tmp_path / 'skillhub' / 'ghost' / 'maps'
    shutil.copytree(REPO / 'tests/fixtures/fake_google_maps/skill', skill) if (REPO / 'tests/fixtures/fake_google_maps/skill').is_dir() else None
    if not skill.is_dir():
        src = next(p for p in (REPO / 'skillhub/ghost').iterdir() if (p / 'skill.yaml').is_file() and 'com.google.android.apps.maps' in (p / 'skill.yaml').read_text())
        shutil.copytree(src, skill, ignore=shutil.ignore_patterns('runs', 'verifications', 'demos', '__pycache__'))
    monkeypatch.setattr(cli, 'run_action', lambda skill, action, **kwargs: RunResult(True, skill.name, action))
    monkeypatch.setattr('urllib.request.urlopen', lambda *a, **kw: pytest.fail('No network'))
    return skill


def test_cli_run_warns_refuses_forces_and_reports(maps_skill, capsys):
    import yaml
    raw = yaml.safe_load((maps_skill / 'skill.yaml').read_text())
    action = raw['actions'][0]['name']
    serial = 'fake:' + str(FIXTURE)
    assert cli.main(['run', str(maps_skill), action, '--device', serial]) == 0
    assert 'Warning' not in capsys.readouterr().err
    raw['fingerprint'].update({'os_version': '>=15'})
    (maps_skill / 'skill.yaml').write_text(yaml.safe_dump(raw))
    assert cli.main(['run', str(maps_skill), action, '--device', serial]) == 0
    assert 'fingerprint distance 1' in capsys.readouterr().err
    assert cli.main(['run', str(maps_skill), action, '--device', serial, '--strict-fingerprint']) == 2
    assert '--strict-fingerprint' in capsys.readouterr().err
    raw['fingerprint'].update({'hardware': 'ASUS/ROG', 'app_version': '26.x'})
    (maps_skill / 'skill.yaml').write_text(yaml.safe_dump(raw))
    assert cli.main(['run', str(maps_skill), action, '--device', serial]) == 2
    assert 'force-fingerprint' in capsys.readouterr().err
    assert cli.main(['run', str(maps_skill), action, '--device', serial, '--force-fingerprint']) == 0
    assert cli.main(['run', str(maps_skill), action, '--device', serial, '--no-fingerprint-check']) == 0


def test_mcp_run_skill_reports_distance_and_refuses(maps_skill, monkeypatch):
    import yaml
    from gitd import mcp_server
    raw = yaml.safe_load((maps_skill / 'skill.yaml').read_text())
    action = raw['actions'][0]['name']
    monkeypatch.setattr('gitd.skills.engine.run_action', lambda skill, action, params, device: RunResult(True, skill.name, action))
    serial = 'fake:' + str(FIXTURE)
    result = json.loads(mcp_server.run_skill(str(maps_skill), action, '{}', serial))
    assert result['success'] and result['fingerprint']['distance'] == 0 and result['fingerprint']['tier'] == 'hit'
    assert json.loads(mcp_server.run_skill(str(maps_skill), action, '{}', ''))['fingerprint'] is None
    raw['fingerprint'].update({'os': 'android', 'os_version': '>=15', 'hardware': 'ASUS/ROG', 'app_version': '26.x'})
    (maps_skill / 'skill.yaml').write_text(yaml.safe_dump(raw))
    refused = json.loads(mcp_server.run_skill(str(maps_skill), action, '{}', serial))
    assert refused['status'] == 'refused' and refused['error']['kind'] == 'fingerprint_mismatch'
    monkeypatch.setenv('GHOST_STRICT_FINGERPRINT', '1')
    raw['fingerprint'].update({'os_version': '>=14', 'hardware': '*', 'app_version': '*'})
    (maps_skill / 'skill.yaml').write_text(yaml.safe_dump(raw))
    assert json.loads(mcp_server.run_skill(str(maps_skill), action, '{}', serial))['fingerprint']['distance'] == 0


def test_doctor_ref_reports_tested_fingerprints_and_distance(maps_skill, capsys):
    runs = maps_skill / 'runs'
    runs.mkdir()
    base = {'os': 'android', 'os_version': '14', 'hardware': 'Fixture/GoogleMaps', 'app_package': 'com.google.android.apps.maps', 'app_version': '25.0.0'}
    (runs / 'a.json').write_text(json.dumps({'fingerprint': base, 'success': True, 'finished_at': '2026-10-01T00:00:00+00:00', 'signature': {}}))
    (runs / 'b.json').write_text(json.dumps({'fingerprint': dict(base, hardware='ASUS/ROG', os_version='15'), 'success': False, 'signature': {}}))
    (runs / 'sim.json').write_text(json.dumps({'fingerprint': base, 'success': True, 'simulation': True, 'signature': {}}))
    assert cli.main(['doctor', str(maps_skill)]) == 0
    out = capsys.readouterr().out
    assert 'Authored for:' in out and 'Fixture/GoogleMaps Android 14 app 25.0.0: 1/1 passed, last pass' in out
    assert 'ASUS/ROG Android 15 app 25.0.0: 0/1 passed' in out and out.count('25.0.0') == 2
    assert cli.main(['doctor', str(maps_skill), '--device', 'fake:' + str(FIXTURE)]) == 0
    out = capsys.readouterr().out
    assert 'Distance 0 (hit)' in out and 'Nearest tested fingerprint: Fixture/GoogleMaps Android 14' in out
    assert cli.main(['doctor', str(maps_skill), '--device', 'ios:abc']) == 1
    assert 'cannot be probed' in capsys.readouterr().out


def test_doctor_without_ref_still_runs_the_environment_checks(monkeypatch, capsys):
    monkeypatch.setattr(cli.subprocess, 'run', lambda *a, **k: (_ for _ in ()).throw(OSError('no tools')))
    monkeypatch.setattr('urllib.request.urlopen', lambda *a, **kw: (_ for _ in ()).throw(OSError('offline')))
    assert cli.main(['doctor']) == 1
    assert 'adb devices' in capsys.readouterr().out
