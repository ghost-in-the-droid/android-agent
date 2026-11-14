import json
import subprocess
from pathlib import Path

import pytest
import yaml

from gitd.skills.engine import cli
from gitd.skills.engine.importers import parse_automate, parse_maestro

FIXTURES = Path(__file__).parent / 'fixtures'


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Import commands must not access network or devices')
    monkeypatch.setattr(subprocess, 'run', forbidden)
    monkeypatch.setattr('urllib.request.urlopen', forbidden)


@pytest.mark.parametrize('format_name, filename, expected', [
    ('maestro', 'maestro_flow.yaml', ['launch_app', 'tap_element', 'tap_element', 'type_text', 'swipe', 'press_key', 'wait_for_text']),
    ('automate', 'automate_flow.flo', ['sleep', 'launch_app', 'tap_element', 'type_text', 'sleep', 'press_key', 'wait_for_text']),
])
def test_import_primitives(tmp_path, capsys, format_name, filename, expected):
    source = FIXTURES / filename
    output = tmp_path / 'skillhub/alice/notes'
    assert cli.main(['import', '--' + format_name, str(source), '--out', str(output)]) == 0
    skill = cli.load_skill(output)
    assert skill.author == 'alice' and skill.name == 'notes'
    assert skill.license == 'MIT' and skill.generated_with == f'ghost skill import --{format_name}'
    assert skill.fingerprint.app_package == 'com.example.notes'
    action = skill.action('add_note')
    assert [step['action'] for step in action.steps] == expected
    assert action.end_state_validator == {'kind': 'text_visible', 'text': 'Saved'}
    assert action.steps[1 if format_name == 'maestro' else 2]['id'] == 'com.example.notes:id/add'
    original = output / ('imported-source.yaml' if format_name == 'maestro' else 'imported-source.flo')
    assert original.read_bytes() == source.read_bytes()
    assert cli.main(['validate', str(output)]) == 0
    assert cli.main(['lint', str(output)]) == 0
    assert 'Unmapped imported node' not in capsys.readouterr().out
    assert cli.main(['import', '--' + format_name, str(source), '--out', str(output)]) == 1


@pytest.mark.parametrize('format_name', ['maestro', 'automate'])
def test_unmapped_nodes_are_preserved_commented_and_linted(tmp_path, capsys, format_name):
    source = tmp_path / ('unknown.yaml' if format_name == 'maestro' else 'unknown.flo')
    node = {'runScript': {'file': 'secret.js'}} if format_name == 'maestro' else {'id': 1, 'type': 'unknown', 'args': {'value': '{undeclared_source_variable}'}}
    if format_name == 'maestro':
        source.write_text('appId: com.example\n---\n' + yaml.safe_dump([node, {'back': None}]))
    else:
        source.write_text(json.dumps({'name': 'unknown', 'app_package': 'com.example', 'blocks': [node, {'type': 'key_press', 'args': {'key': 'BACK'}}]}))
    target = tmp_path / 'skillhub/alice/unknown'
    assert cli.main(['import', '--' + format_name, str(source), '--out', str(target)]) == 0
    text = (target / 'skill.yaml').read_text()
    assert '# TODO: translate this source node' in text
    action = cli.load_skill(target).actions[0]
    assert action.steps[0]['import_unmapped']['source'] == node
    assert action.steps[1] == {'action': 'press_key', 'key': 'BACK'}
    assert 'TODO' in action.end_state_validator['text']
    capsys.readouterr()
    assert cli.main(['lint', str(target)]) == 0
    assert 'Unmapped imported node' in capsys.readouterr().out


def test_native_binary_is_retained_as_explicit_todo(tmp_path, capsys):
    source = tmp_path / 'native.flo'; source.write_bytes(b'\x00\xff\x01native-flow')
    target = tmp_path / 'skillhub/alice/native'
    assert cli.main(['import', '--automate', str(source), '--out', str(target)]) == 0
    assert (target / 'imported-source.flo').read_bytes() == source.read_bytes()
    assert 'Native binary' in capsys.readouterr().out
    assert cli.main(['lint', str(target)]) == 0
    assert 'Unmapped imported node' in capsys.readouterr().out


def test_automate_multiple_flows_and_branch_preservation(tmp_path):
    data = json.loads((FIXTURES / 'automate_flow.flo').read_text())
    other = {**data, 'name': 'second_flow', 'blocks': [{'id': 1, 'type': 'app_start', 'next': 1}]}
    source = tmp_path / 'flows.flo'; source.write_text(json.dumps({'flows': [data, other]}))
    target = tmp_path / 'skillhub/alice/flows'
    assert cli.main(['import', '--automate', str(source), '--out', str(target)]) == 0
    skill = cli.load_skill(target)
    assert skill.action_names() == ['add_note', 'second_flow']
    assert skill.actions[1].steps[0]['import_unmapped']['source']['next'] == 1


def test_import_default_path_and_bad_inputs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert cli.main(['import', '--maestro', str(FIXTURES / 'maestro_flow.yaml')]) == 0
    assert (tmp_path / 'skillhub/local/maestro_flow/skill.yaml').exists()
    bad = tmp_path / 'bad.yaml'; bad.write_text('appId: com.example\n---\ncommands: invalid\n')
    assert cli.main(['import', '--maestro', str(bad)]) == 1
    assert not (tmp_path / 'skillhub/local/bad').exists()
    bad.write_text('appId: [unterminated')
    with pytest.raises(ValueError, match='Cannot parse Maestro'):
        parse_maestro(bad)
    bad_flo = tmp_path / 'bad.flo'; bad_flo.write_text('{"flows": []}')
    with pytest.raises(ValueError):
        parse_automate(bad_flo)


def test_unsupported_maestro_options_and_nonterminal_assertions(tmp_path):
    source = tmp_path / 'options.yaml'
    source.write_text('appId: com.example\nonFlowStart: ignored\n---\n- tapOn: {text: Save, optional: true}\n- assertVisible: Saved\n- back\n')
    target = tmp_path / 'skillhub/alice/options'
    assert cli.main(['import', '--maestro', str(source), '--out', str(target)]) == 0
    skill = cli.load_skill(target)
    assert skill.actions[0].steps[0]['import_unmapped']['source'] == {'onFlowStart': 'ignored'}
    assert skill.actions[0].steps[1]['import_unmapped']['source'] == {'tapOn': {'text': 'Save', 'optional': True}}
    assert 'TODO' in skill.actions[0].end_state_validator['text']
