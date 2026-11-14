import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from gitd import ghost_cli
from gitd.skills.engine import cli, evidence
from gitd.skills.engine.runner import RunResult, TraceEntry


@pytest.fixture
def setup(tmp_path, monkeypatch):
    checkout = tmp_path / 'checkout'
    skill = checkout / 'skillhub/ghost/tiktok'
    skill.parent.mkdir(parents=True)
    (checkout / '.git').touch()
    monkeypatch.chdir(checkout)
    shutil.copytree(Path(__file__).resolve().parents[1] / 'skillhub/ghost/tiktok', skill, ignore=shutil.ignore_patterns('runs', 'verifications'))  # start from a clean evidence state
    monkeypatch.setenv('GHOST_CONFIG_DIR', str(tmp_path / 'config'))
    monkeypatch.setenv('GHOST_SKILLS_DIR', str(tmp_path / 'installed'))
    monkeypatch.delenv('DEFAULT_DEVICE', raising=False)
    fingerprint = {'os': 'android', 'os_version': '14', 'hardware': 'ASUS/ROG',
                   'app_package': 'com.zhiliaoapp.musically', 'app_version': '44.3.3'}
    fp_path = tmp_path / 'fingerprint.json'
    fp_path.write_text(json.dumps(fingerprint))
    monkeypatch.setattr('urllib.request.urlopen', lambda *args, **kwargs: pytest.fail('Network prohibited'))
    return skill, fingerprint, fp_path


def result(action, success=True):
    return RunResult(success=success, skill='tiktok', action=action, duration_ms=12,
                     data={'handle': 'private-handle'}, error=None if success else {'kind': 'ValidatorFailedError', 'message': 'private-message'},
                     trace=[TraceEntry(0, {'text': 'private-text'}, 123, 12, None if success else 'private-error')])


def test_run_record_writes_success_and_failure(setup, monkeypatch):
    skill, fingerprint, fp_path = setup
    monkeypatch.setattr(evidence, '_sign', lambda payload: {'algorithm': 'test-signature'})
    success = [True]
    monkeypatch.setattr(cli, 'run_action', lambda skill, action, **kwargs: result(action, success[0]))
    args = ['run', str(skill), 'open_inbox', '--device', 'mock', '--record', '--fingerprint', str(fp_path)]
    assert cli.main(args) == 0
    success[0] = False
    assert cli.main(args) == 1
    artifacts = sorted((skill / 'runs').glob('*.json'))
    assert len(artifacts) == 2
    first, second = [json.loads(path.read_text()) for path in artifacts]
    assert first['success'] is True and second['success'] is False
    assert first['fingerprint'] == fingerprint
    assert first['fingerprint_hash'] == evidence.fingerprint_hash(fingerprint)
    assert first['actions'][0]['steps'][0]['success'] is True
    assert second['actions'][0]['error_kind'] == 'ValidatorFailedError'
    assert 'private' not in artifacts[0].read_text() and 'private' not in artifacts[1].read_text()
    assert artifacts[0].name.startswith(first['fingerprint_hash'] + '-')


def test_run_without_record_does_not_collect_or_write(setup, monkeypatch):
    skill, fingerprint, fp_path = setup
    monkeypatch.setattr(evidence, 'collect_fingerprint', lambda *args: pytest.fail('No fingerprint without record'))
    monkeypatch.setattr(cli, 'run_action', lambda skill, action, **kwargs: result(action))
    assert cli.main(['run', str(skill), 'open_inbox', '--device', 'mock']) == 0
    assert not (skill / 'runs').exists()
    assert cli.main(['run', str(skill), 'open_inbox', '--record']) == 2


def test_verify_login_and_failed_run(setup, monkeypatch, capsys):
    skill, fingerprint, fp_path = setup
    monkeypatch.setattr(evidence, '_sign', lambda payload: {'algorithm': 'test-signature'})
    monkeypatch.setattr(evidence, 'github_login', lambda: 'verifier-user')
    monkeypatch.setattr(cli, 'run_action', lambda skill, action, **kwargs: result(action, False))
    args = ['verify', str(skill), '--action', 'open_inbox', '--device', 'mock', '--fingerprint', str(fp_path), '--dry-run']
    assert cli.main(args) == 1
    artifacts = list((skill / 'verifications').glob('*.json'))
    assert len(artifacts) == 1 and artifacts[0].name.startswith('verifier-user-')
    payload = json.loads(artifacts[0].read_text())
    assert payload['github_login'] == 'verifier-user' and payload['kind'] == 'verification'
    assert 'PR preview only' in capsys.readouterr().out
    monkeypatch.setattr(evidence, 'github_login', lambda: 'ghost')
    assert cli.main(args) == 1
    assert 'other than the skill author' in capsys.readouterr().err
    assert len(list((skill / 'verifications').glob('*.json'))) == 1


def test_collect_android_fingerprint_and_gh_identity(setup, monkeypatch):
    skill_path, fingerprint, fp_path = setup
    skill = cli.load_skill(skill_path)
    seen = []
    def run(args, **kwargs):
        seen.append(args)
        values = {'ro.build.version.release': '14', 'ro.product.manufacturer': 'ASUS', 'ro.product.model': 'ROG'}
        if args[0] == 'gh': return SimpleNamespace(stdout='verifier-user\n')
        if 'dumpsys' in args: return SimpleNamespace(stdout='  versionName=44.3.3\n')
        return SimpleNamespace(stdout=values[args[-1]])
    monkeypatch.setattr(evidence.subprocess, 'run', run)
    assert evidence.collect_fingerprint(skill, 'mock') == fingerprint
    assert all(args[:4] == ['adb', '-s', 'mock', 'shell'] for args in seen)
    assert evidence.github_login() == 'verifier-user'
    with pytest.raises(ValueError, match='iOS recording requires'):
        evidence.collect_fingerprint(skill, 'ios:mock')
    with pytest.raises(ValueError, match='platform'):
        evidence.collect_fingerprint(skill, 'ios:mock', str(fp_path))
    fingerprint['app_version'] = '>=44'
    with pytest.raises(ValueError, match='concrete app_version'):
        evidence.validate_fingerprint(fingerprint)


def test_signature_verifies_and_rejects_tampering(setup, tmp_path):
    if not shutil.which('ssh-keygen'):
        pytest.skip('SSH signing tool unavailable')
    skill_path, fingerprint, fp_path = setup
    skill = cli.load_skill(skill_path)
    artifact = evidence.write_evidence(skill, [result('open_inbox')], fingerprint)
    payload = json.loads(artifact.read_text())
    signature = payload.pop('signature')
    sig_file = tmp_path / 'signature'; sig_file.write_text(signature['value'])
    allowed = tmp_path / 'allowed'; allowed.write_text('recorder ' + signature['public_key'] + '\n')
    args = ['ssh-keygen', '-Y', 'verify', '-f', str(allowed), '-I', 'recorder', '-n', signature['namespace'], '-s', str(sig_file)]
    assert subprocess.run(args, input=evidence.canonical(payload), capture_output=True).returncode == 0
    payload['success'] = False
    assert subprocess.run(args, input=evidence.canonical(payload), capture_output=True).returncode != 0


def test_telemetry_config_only_default_off_dnt_and_rotation(setup, monkeypatch, capsys):
    from gitd.ghostcli import config
    def forbidden(*args, **kwargs): pytest.fail('Telemetry cannot start subprocesses')
    monkeypatch.setattr(subprocess, 'run', forbidden)
    monkeypatch.delenv('DO_NOT_TRACK', raising=False)
    assert ghost_cli.main(['telemetry', 'status']) == 0
    assert 'Telemetry: off' in capsys.readouterr().out
    assert not config.config_path().exists()
    config.save_config({'backend': {'name': 'codex'}})
    assert ghost_cli.main(['telemetry', 'on']) == 0
    first_id = config.load_config()['telemetry']['install_id']
    assert config.load_config()['backend']['name'] == 'codex'
    assert ghost_cli.main(['telemetry', 'on']) == 0
    assert config.load_config()['telemetry']['install_id'] != first_id
    capsys.readouterr()
    monkeypatch.setenv('DO_NOT_TRACK', '1')
    assert ghost_cli.main(['telemetry', 'status']) == 0
    assert 'DO_NOT_TRACK=1 overrides' in capsys.readouterr().out
    assert ghost_cli.main(['telemetry', 'off']) == 0
    assert 'install_id' not in config.load_config()['telemetry']
    assert config.load_config()['telemetry']['enabled'] is False


def test_display_axes_records_screen_density_locale_and_prefers_overrides():
    from gitd.skills.engine.evidence import _display_axes

    out = {
        ("wm", "size"): "Physical size: 1080x2340\nOverride size: 720x1560",
        ("wm", "density"): "Physical density: 450",
        ("getprop", "persist.sys.locale"): "en-GB",
    }
    assert _display_axes(lambda *a: out.get(a, "")) == {"screen_wxh": "720x1560", "density": "450", "locale": "en-GB"}


def test_display_axes_omits_unreadable_fields():
    from gitd.skills.engine.evidence import _display_axes

    def broken(*a):
        raise RuntimeError("adb gone")

    assert _display_axes(broken) == {}
    assert _display_axes(lambda *a: "") == {}
