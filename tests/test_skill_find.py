"""`ghost skill find` / MCP find_skill: BM25 intent search over skill actions."""
import json
from pathlib import Path

import pytest
import yaml

from gitd.skills.engine import cli
from gitd.skills.engine.find import Doc, docs_from_dirs, docs_from_registry, docs_from_skill_yaml, rank, tokenize

REPO = Path(__file__).resolve().parents[1]


def _skill(tmp_path, author, slug, package, actions):
    directory = tmp_path / 'skillhub' / author / slug
    directory.mkdir(parents=True)
    raw = {'name': slug, 'version': '1.0.0', 'author': author, 'description': f'{slug} skill', 'skill_class': 'hard',
           'fingerprint': {'os': 'android', 'os_version': '*', 'hardware': '*', 'app_package': package, 'app_version': '*'},
           'actions': actions}
    (directory / 'skill.yaml').write_text(yaml.safe_dump(raw))
    return directory


@pytest.fixture
def corpus(tmp_path):
    expense = _skill(tmp_path, 'ghost', 'expense', 'com.arduia.expense', [
        {'name': 'add_expense', 'ref_prompt': 'Add an expense of {amount} for {note}',
         'params': [{'name': 'amount', 'type': 'str'}, {'name': 'note', 'type': 'str'}],
         'test_case': {'ref_prompt_variants': ['Record a {amount} purchase called {note}', 'Log spending {note}']}},
        {'name': 'delete_expense', 'ref_prompt': 'Delete the expense named {note}', 'params': [{'name': 'note', 'type': 'str'}]},
    ])
    calc = _skill(tmp_path, 'ghost', 'calculator', 'org.fossify.math', [
        {'name': 'calculate', 'ref_prompt': 'Calculate {expression}', 'params': [{'name': 'expression', 'type': 'str'}]},
    ])
    return {'root': tmp_path, 'expense': expense, 'calc': calc}


def test_tokenize_drops_placeholders_and_stop_words():
    assert tokenize('Add an expense of {amount} for {note}!') == ['add', 'expense']
    assert tokenize('') == []


def test_docs_from_skill_yaml_uses_prompt_variants_and_package(corpus):
    raw = yaml.safe_load((corpus['expense'] / 'skill.yaml').read_text())
    docs = docs_from_skill_yaml('ghost/expense', raw, 'checkout')
    assert [d.action for d in docs] == ['add_expense', 'delete_expense']
    add = docs[0]
    assert add.prompt == 'Add an expense of {amount} for {note}' and add.params == ['amount', 'note']
    assert 'purchase' in add.tokens and 'arduia' in add.tokens and add.app_package == 'com.arduia.expense'
    assert docs_from_skill_yaml('v1/skill', {'name': 'old', 'exports': {'actions': ['x']}}, 'flat') == []


def test_rank_prefers_the_matching_action_and_is_deterministic(corpus):
    docs = docs_from_dirs([('ghost/expense', corpus['expense']), ('ghost/calculator', corpus['calc'])], 'checkout')
    hits = rank('log a purchase as spending', docs, top=3)
    assert hits[0][1].action == 'add_expense'
    assert all(score > 0 for score, _ in hits)
    assert rank('log a purchase as spending', docs, top=3) == hits
    assert rank('', docs) == [] and rank('zebra', docs) == []
    calc = rank('calculate 2 plus 2', docs, top=1)
    assert calc[0][1].skill == 'ghost/calculator'


def test_rank_tie_breaks_on_skill_then_action():
    docs = [Doc('b/skill', 'z', 'hub', 'open inbox'), Doc('a/skill', 'y', 'hub', 'open inbox'), Doc('a/skill', 'x', 'hub', 'open inbox')]
    assert [(d.skill, d.action) for _, d in rank('open inbox', docs)] == [('a/skill', 'x'), ('a/skill', 'y'), ('b/skill', 'z')]


def test_docs_from_registry_reads_prompts_and_skips_excluded_and_blocked():
    registry = {'skills': {
        'ghost/expense': {'name': 'expense', 'description': 'track money', 'latest': '1.0.0', 'versions': {'1.0.0': {
            'fingerprint': {'app_package': 'com.arduia.expense'}, 'actions': ['add_expense'],
            'prompts': {'add_expense': ['Add an expense of {amount}', 'Record a purchase']}}}},
        'ghost/old': {'name': 'old', 'latest': '0.1.0', 'status': 'blocked', 'versions': {'0.1.0': {'actions': ['x']}}},
        'ghost/local': {'name': 'local', 'latest': '0.1.0', 'versions': {'0.1.0': {'actions': ['y']}}},
        'ghost/gone': {'name': 'gone', 'latest': '0.1.0', 'status': 'deprecated', 'versions': {'0.1.0': {'actions': ['z']}}},
        'androidworld/clock': {'name': 'clock', 'latest': '0.1.0', 'status': 'draft', 'versions': {'0.1.0': {'actions': ['w']}}},
    }}
    docs = docs_from_registry(registry, exclude={'ghost/local'})
    assert [(d.skill, d.action, d.source) for d in docs] == [('ghost/expense', 'add_expense', 'hub')]
    assert docs[0].prompt == 'Add an expense of {amount}' and 'purchase' in docs[0].tokens



def test_cli_find_skips_underscore_dirs_in_the_checkout(corpus, tmp_path, monkeypatch, capsys):
    _skill(tmp_path / 'skillhub' / '_drafts', 'androidworld', 'zebra', 'org.zebra', [
        {'name': 'feed_zebra', 'ref_prompt': 'Feed the zebra'}])
    _skill(tmp_path, '_wip', 'zebra', 'org.zebra', [{'name': 'feed_zebra', 'ref_prompt': 'Feed the zebra'}])
    monkeypatch.setenv('GHOST_SKILLS_DIR', str(tmp_path / 'installed'))
    monkeypatch.chdir(tmp_path)
    assert cli.main(['find', 'feed the zebra', '--no-hub', '--json']) == 0
    assert all('zebra' not in h['skill'] for h in json.loads(capsys.readouterr().out))

def test_registry_builder_emits_prompts_per_action():
    from tools.build_registry import _prompts
    raw = yaml.safe_load((REPO / 'skillhub/ghost/calculator/skill.yaml').read_text())
    prompts = _prompts(raw)
    assert set(prompts) == {a['name'] for a in raw['actions']}
    assert prompts['calculate'][0] == raw['actions'][0]['ref_prompt']
    assert _prompts({'exports': {'actions': ['x']}}) == {}


def test_cli_find_searches_installed_checkout_and_hub(corpus, tmp_path, monkeypatch, capsys):
    installed = tmp_path / 'installed' / 'ghost' / 'calculator' / '2.0.0'
    installed.mkdir(parents=True)
    (installed / 'skill.yaml').write_text((corpus['calc'] / 'skill.yaml').read_text().replace('1.0.0', '2.0.0'))
    monkeypatch.setenv('GHOST_SKILLS_DIR', str(tmp_path / 'installed'))
    registry = tmp_path / 'registry.json'
    registry.write_text(json.dumps({'skills': {
        'alice/weather': {'name': 'weather', 'description': 'forecast', 'latest': '1.0.0', 'versions': {'1.0.0': {
            'fingerprint': {'app_package': 'org.breezyweather'}, 'actions': ['forecast'], 'prompts': {'forecast': ['Show the weather forecast for {city}']}}}},
        'ghost/calculator': {'name': 'calculator', 'description': 'ignored: installed wins', 'latest': '9.9.9', 'versions': {'9.9.9': {'actions': ['calculate'], 'prompts': {'calculate': ['calculate']}}}},
    }}))
    monkeypatch.setenv('GHOST_HUB_REGISTRY', str(registry))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('urllib.request.urlopen', lambda *a, **kw: pytest.fail('No network'))
    assert cli.main(['find', 'record a purchase', '--json']) == 0
    hits = json.loads(capsys.readouterr().out)
    assert hits[0]['skill'] == 'ghost/expense' and hits[0]['action'] == 'add_expense' and hits[0]['source'] == 'checkout'
    assert hits[0]['params'] == ['amount', 'note']
    assert cli.main(['find', 'weather forecast', '--json']) == 0
    hits = json.loads(capsys.readouterr().out)
    assert hits[0]['skill'] == 'alice/weather' and hits[0]['source'] == 'hub'
    assert cli.main(['find', 'calculate', '--json']) == 0
    hits = json.loads(capsys.readouterr().out)
    assert [h['source'] for h in hits if h['skill'] == 'ghost/calculator'] == ['installed']
    assert cli.main(['find', 'weather forecast', '--no-hub', '--json']) == 0
    assert all(h['skill'] != 'alice/weather' for h in json.loads(capsys.readouterr().out))
    assert cli.main(['find', 'zebra crossing']) == 1
    assert 'No matching skill action' in capsys.readouterr().out
    assert cli.main(['find', 'calculate']) == 0
    assert 'SCORE  SKILL  ACTION  SOURCE  PROMPT' in capsys.readouterr().out


def test_mcp_find_skill_ranks_flat_skill_dirs(corpus, monkeypatch):
    from gitd import mcp_server
    flat = [corpus['expense'], corpus['calc']]
    monkeypatch.setattr('gitd.skills.locations.iter_legacy_skill_dirs', lambda: flat)
    hits = json.loads(mcp_server.find_skill('delete the lunch expense', top=2))
    assert hits[0]['skill'] == 'expense' and hits[0]['action'] == 'delete_expense' and hits[0]['source'] == 'flat'
    assert len(hits) == 2
    empty = json.loads(mcp_server.find_skill('zebra'))
    assert empty['hits'] == [] and 'list_skills' in empty['hint']


def test_agent_tool_find_skill_dispatches_like_mcp(corpus, monkeypatch):
    from gitd.services.agent_tools import TOOLS, execute_tool
    flat = [corpus['expense'], corpus['calc']]
    monkeypatch.setattr('gitd.skills.locations.iter_legacy_skill_dirs', lambda: flat)
    tool, = [t for t in TOOLS if t['name'] == 'find_skill']
    assert tool['input_schema']['required'] == ['intent']
    hits = json.loads(execute_tool('find_skill', {'intent': 'add an expense', 'top': 1}))
    assert hits == json.loads(__import__('gitd.mcp_server', fromlist=['find_skill']).find_skill('add an expense', top=1))
    assert hits[0]['skill'] == 'expense' and hits[0]['action'] == 'add_expense'
    assert hits[0]['run_with'] == 'run_skill' and hits[0]['notes_with'] == 'get_skill_notes'
    assert 'hint' in json.loads(execute_tool('find_skill', {'intent': 'zebra'}))
