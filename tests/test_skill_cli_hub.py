import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from gitd.skills.engine import cli

FIXTURE = Path(__file__).resolve().parents[1] / 'skillhub/ghost/tiktok'


@pytest.fixture
def skill(tmp_path):
    target = tmp_path / 'tiktok'
    shutil.copytree(FIXTURE, target)
    return target


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Unexpected network or subprocess call')
    monkeypatch.setattr('urllib.request.urlopen', forbidden)
    monkeypatch.setattr(cli.subprocess, 'run', forbidden)


@pytest.fixture
def fake_hub(skill, tmp_path, monkeypatch):
    import hashlib
    from gitd.skills import hub
    installed = tmp_path / 'installed'
    monkeypatch.setenv('GHOST_SKILLS_DIR', str(installed))
    blobs = {str(p.relative_to(skill)): p.read_bytes() for p in skill.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    metadata = cli.load_skill(skill)
    def entry(version):
        return {'tag': f'ghost/tiktok-v{version}', 'files': {name: 'sha256:' + hashlib.sha256(data).hexdigest() for name, data in blobs.items()}}
    registry = {'skills': {'ghost/tiktok': {'trust': 'official', 'latest': metadata.version, 'versions': {metadata.version: entry(metadata.version)}}}}
    seen = []
    def fetch(url):
        seen.append(url)
        if url.endswith('/skillhub/registry.json'):
            return json.dumps(registry).encode()
        marker = '/skillhub/ghost/tiktok/'
        if marker in url:
            return blobs[url.split(marker, 1)[1]]
        raise hub.HubError('unexpected fake URL: ' + url)
    monkeypatch.setattr(hub, '_fetch', fetch)
    return installed, registry, entry, seen


def test_real_hub_commands(fake_hub, capsys):
    installed, registry, entry, seen = fake_hub
    version = registry['skills']['ghost/tiktok']['latest']
    assert cli.main(['install', 'ghost/tiktok']) == 0
    assert (installed / f'ghost/tiktok/{version}/skill.yaml').exists()
    assert cli.main(['list']) == 0
    assert 'official' in capsys.readouterr().out
    assert cli.main(['outdated']) == 0
    assert cli.main(['update', 'ghost/tiktok']) == 0
    assert 'up to date' in capsys.readouterr().out
    registry['skills']['ghost/tiktok']['latest'] = '2.1.0'
    registry['skills']['ghost/tiktok']['versions']['2.1.0'] = entry('2.1.0')
    assert cli.main(['outdated']) == 0
    assert f'ghost/tiktok  {version}  2.1.0' in capsys.readouterr().out
    assert cli.main(['update', '--all']) == 0
    assert (installed / 'ghost/tiktok/2.1.0/skill.yaml').exists()
    assert cli.main(['uninstall', 'ghost/tiktok@2.1.0']) == 0
    assert not (installed / 'ghost/tiktok/2.1.0').exists()
    assert cli.main(['uninstall', 'ghost/tiktok']) == 0
    assert not (installed / 'ghost/tiktok').exists()
    assert seen


def test_real_client_trust_and_errors(fake_hub, monkeypatch, capsys):
    installed, registry, entry, seen = fake_hub
    monkeypatch.setattr('builtins.input', lambda prompt: 'n')
    assert cli.main(['install', 'ghost/tiktok', '--url', 'https://example.test/repo']) == 1
    assert not (installed / 'ghost/tiktok').exists()
    assert 'declined' in capsys.readouterr().err
    assert cli.main(['install', 'ghost/tiktok', '--url', 'https://example.test/repo', '--yes']) == 0
    assert 'unverified' in capsys.readouterr().out
    assert cli.main(['install', 'ghost/tiktok', '--force', '--yes']) == 0
    assert cli.main(['install', 'ghost/absent']) == 1
    assert cli.main(['uninstall', 'ghost/absent']) == 1
    registry['skills']['ghost/tiktok']['trust'] = 'quarantined'
    assert cli.main(['install', 'ghost/tiktok', '--force']) == 0
    assert cli.main(['uninstall', 'ghost/tiktok']) == 0
    assert cli.main(['install', 'ghost/tiktok']) == 1
    registry['skills']['ghost/tiktok']['trust'] = 'official'
    registry['skills']['ghost/tiktok']['versions'][registry['skills']['ghost/tiktok']['latest']]['files']['skill.yaml'] = 'sha256:wrong'
    assert cli.main(['install', 'ghost/tiktok']) == 1
    assert 'sha256 mismatch' in capsys.readouterr().err


def test_registry_commands(skill, monkeypatch, capsys):
    metadata = cli.load_skill(skill)
    entry = dict(name=metadata.name, description=metadata.description, trust='official', latest=metadata.version,
                 quality={'tier': 'C'}, versions={metadata.version: {'actions': metadata.action_names(), 'fingerprint': {'app_package': metadata.fingerprint.app_package}}})
    monkeypatch.setattr(cli, '_registry', lambda: {'skills': {'ghost/tiktok': entry}})
    monkeypatch.setattr(cli.hub, 'list_installed', lambda: [])
    for query in ['tiktok', 'get_my_stats', metadata.fingerprint.app_package]:
        assert cli.main(['search', query, '--json']) == 0
        assert 'ghost/tiktok' in json.loads(capsys.readouterr().out)
    assert cli.main(['search', 'tiktok']) == 0
    assert 'official' in capsys.readouterr().out
    assert cli.main(['info', 'ghost/tiktok']) == 0
    assert 'Install state: []' in capsys.readouterr().out
    assert cli.main(['info', 'ghost/missing']) == 1


def test_diff(skill, tmp_path, capsys):
    other = tmp_path / 'other'; shutil.copytree(skill, other)
    raw = yaml.safe_load((other / 'skill.yaml').read_text())
    raw['actions'][0]['steps'].append({'action': 'sleep', 'duration_s': 1})
    raw['actions'][0]['params'].append({'name': 'new'})
    raw['actions'][0]['end_state_validator'] = {'kind': 'text_visible', 'text': 'changed'}
    raw['fingerprint']['hardware'] = 'pixel'
    removed = raw['actions'].pop(); added = dict(removed, name='new_action'); raw['actions'].append(added)
    (other / 'skill.yaml').write_text(yaml.safe_dump(raw))
    assert cli.main(['diff', str(skill), str(other)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['fingerprint_changed']
    assert result['actions_added'] == ['new_action']
    assert result['actions_removed'] == [removed['name']]
    changes = result['actions_changed'][raw['actions'][0]['name']]
    assert set(changes) == {'params', 'steps', 'validator'}


def test_submit_dry_run(skill, capsys):
    (skill / 'bench.yaml').write_text('benches: []\n')
    (skill / 'demo.gif').write_bytes(b'GIF89a')
    assert cli.main(['submit', str(skill), '--dry-run']) == 0
    output = capsys.readouterr().out
    assert '[skill] ghost/tiktok' in output
    assert 'skillhub/ghost/tiktok/skill.yaml' in output
    assert 'Bench summary' in output and 'Demo:' in output and 'Contribution checklist' in output


def test_lint(skill, capsys):
    assert cli.main(['lint', str(skill)]) == 0
    capsys.readouterr()
    raw = yaml.safe_load((skill / 'skill.yaml').read_text())
    action = raw['actions'][0]
    action['description'] = ''
    action['test_case']['ref_prompt_variants'] = ['same', 'same']
    action['steps'] = [{'action': 'type_text', 'text': '{undeclared}'}, {'action': 'press_key', 'key': 'HOME'}, {'action': 'tap', 'x': 0, 'y': 0}, {'python_action': 'helpers:missing'}]
    (skill / 'skill.yaml').write_text(yaml.safe_dump(raw))
    assert cli.main(['lint', str(skill)]) == 1
    output = capsys.readouterr()
    for text in ['undeclared param', 'empty description', 'duplicate ref_prompt_variants', 'terminal press_key HOME', 'does not resolve']:
        assert text in output.err
    assert 'Coordinate tap' in output.out


def test_doctor(skill, monkeypatch, capsys):
    monkeypatch.setenv('GHOST_SKILLS_DIR', str(skill / 'installed'))
    monkeypatch.setattr(shutil, 'which', lambda name: '/bin/' + name)
    monkeypatch.setattr(cli.subprocess, 'run', lambda args, **kw: SimpleNamespace(stdout='List of devices attached\nmock\tdevice\n'))
    response = SimpleNamespace(status=200, __enter__=lambda self: self, __exit__=lambda *args: None)
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass
    monkeypatch.setattr('urllib.request.urlopen', lambda *args, **kw: Response())
    assert cli.main(['doctor']) == 0
    assert 'engine registries' in capsys.readouterr().out
    monkeypatch.setattr(shutil, 'which', lambda name: None)
    assert cli.main(['doctor']) == 1


@pytest.mark.parametrize('official, author', [(False, 'alice'), (True, 'ghost')])
def test_scaffold_hub_layout_and_amendment_fields(tmp_path, monkeypatch, official, author):
    monkeypatch.chdir(tmp_path)
    args = ['scaffold', 'alice/new-skill', '--app', 'com.example', '--actions', 'ping,pong']
    if official:
        args.append('--official')
    assert cli.main(args) == 0
    target = tmp_path / 'skillhub' / author / 'new-skill'
    raw = yaml.safe_load((target / 'skill.yaml').read_text())
    assert raw['author'] == author
    assert raw['license'] == 'MIT'
    assert raw['generated_with'].startswith('TODO:')  # scaffold forces the author to declare provenance
    assert raw['skill_path'] == f'skillhub/{author}/new-skill'
    assert not (tmp_path / 'community').exists()
    assert cli.load_skill(target).action_names() == ['ping', 'pong']
    assert cli.main(['validate', str(target)]) == 0
    assert cli.main(args) == 2


@pytest.mark.parametrize('target_body, location', [
    ('return adapter(device, params, context)', 'step'),
    ('return adapter(device, **params)', 'step'),
    ('return adapter(device, params or {})', 'step'),
    ('return adapter(device, params, context)', 'pre_hook'),
    ('return adapter(device, params, context)', 'subroutine'),
    ('return adapter(device, context.params)', 'validator'),
    ('return adapter(device, context)', 'validator'),
])
def test_lint_recognizes_forwarded_params(skill, capsys, target_body, location):
    raw = yaml.safe_load((skill / 'skill.yaml').read_text())
    action = raw['actions'][0]
    action['params'] = [{'name': 'forwarded_value', 'type': 'str'}]
    signature = 'device, context' if location == 'validator' else 'device, params, context'
    (skill / 'forwarder.py').write_text(f'def forward({signature}):\n    {target_body}\n')
    if location == 'validator':
        action['end_state_validator'] = {'kind': 'custom_python', 'function': 'forwarder:forward'}
    elif location == 'pre_hook':
        action['pre_hooks'] = [{'python_action': 'forwarder:forward'}]
    elif location == 'subroutine':
        raw['subroutines'].append({'name': 'forward_values', 'steps': [{'python_action': 'forwarder:forward'}]})
        action['steps'] = [{'subroutine': 'forward_values'}]
    else:
        action['steps'] = [{'python_action': 'forwarder:forward'}]
    (skill / 'skill.yaml').write_text(yaml.safe_dump(raw))
    assert cli.main(['lint', str(skill)]) == 0
    assert 'unused param forwarded_value' not in capsys.readouterr().out
    # No forwarding in this action: other functions/actions cannot hide unused params.
    (skill / 'forwarder.py').write_text(f'def forward({signature}):\n    return True\n\ndef unrelated(device, params, context):\n    return adapter(device, params, context)\n')
    assert cli.main(['lint', str(skill)]) == 0
    assert 'unused param forwarded_value' in capsys.readouterr().out


def test_lint_forwarding_does_not_hide_undeclared_placeholders(skill, capsys):
    raw = yaml.safe_load((skill / 'skill.yaml').read_text())
    action = raw['actions'][0]
    action['steps'] = [{'python_action': 'forwarder:forward'}, {'action': 'type_text', 'text': '{unknown_value}'}]
    (skill / 'forwarder.py').write_text('def forward(device, params, context):\n    return adapter(device, params, context)\n')
    (skill / 'skill.yaml').write_text(yaml.safe_dump(raw))
    assert cli.main(['lint', str(skill)]) == 1
    assert 'undeclared param unknown_value' in capsys.readouterr().err
