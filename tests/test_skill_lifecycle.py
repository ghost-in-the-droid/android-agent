"""Lifecycle (forked_from / superseded_by / deprecated_reason, `ghost skill fork`, `ghost skill deprecate`) and multi-app fingerprints."""
import importlib.util
import json
import shutil
from pathlib import Path

import pytest
import yaml

from gitd.skills.engine import cli
from gitd.skills.engine.loader import SchemaError, load_skill

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("_test_tools_build_registry_l", REPO / "tools" / "build_registry.py")
build_registry = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_registry)


@pytest.fixture
def checkout(tmp_path, monkeypatch):
    hub = tmp_path / 'skillhub'
    src = hub / 'ghost' / 'calculator'
    shutil.copytree(REPO / 'skillhub/ghost/calculator', src, ignore=shutil.ignore_patterns('__pycache__'))
    (src / 'runs').mkdir(exist_ok=True)
    (src / 'runs' / 'x.json').write_text('{}')
    (src / 'verifications').mkdir(exist_ok=True)
    (src / 'verifications' / 'v.json').write_text('{}')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('urllib.request.urlopen', lambda *a, **kw: pytest.fail('No network'))
    return hub


def test_fork_copies_without_evidence_and_records_lineage(checkout, capsys):
    assert cli.main(['fork', 'skillhub/ghost/calculator', '--as', 'alice/calc']) == 0
    out = capsys.readouterr().out
    dest = checkout / 'alice' / 'calc'
    assert 'forked_from ghost/calculator@' in out and dest.is_dir()
    forked = load_skill(dest)
    assert (forked.author, forked.name, forked.version) == ('alice', 'calc', '0.1.0')
    assert forked.forked_from.startswith('ghost/calculator@') and forked.status == 'active'
    assert not (dest / 'runs').exists() and not (dest / 'verifications').exists() and not (dest / 'demos').exists()
    assert forked.demo is None and forked.demos == {}
    text = (dest / 'skill.yaml').read_text()
    assert text.startswith('# Ghost in the Droid') and 'generated_with: ghost skill fork of ghost/calculator@' in text   # comments kept, provenance reset
    assert cli.main(['fork', 'skillhub/ghost/calculator', '--as', 'alice/calc']) == 1    # exists
    assert 'pass --force' in capsys.readouterr().err
    assert cli.main(['fork', 'skillhub/ghost/calculator', '--as', 'alice/calc', '--force']) == 0
    assert cli.main(['fork', 'skillhub/ghost/calculator', '--as', 'ghost/calculator']) == 1
    assert cli.main(['fork', 'skillhub/ghost/calculator', '--as', 'alice/calc@1.0.0', '--force']) == 1
    assert cli.main(['fork', 'skillhub/ghost/calculator', '--as', 'bob/c2', '--out', str(checkout.parent / 'elsewhere')]) == 0
    assert (checkout.parent / 'elsewhere' / 'bob' / 'c2' / 'skill.yaml').is_file()


def test_deprecate_and_undo_keep_comments(checkout, capsys):
    skill_dir = checkout / 'ghost' / 'calculator'
    assert cli.main(['deprecate', str(skill_dir), '--reason', 'app removed from F-Droid', '--superseded-by', 'ghost/calc2']) == 0
    assert 'status deprecated, superseded by ghost/calc2 (app removed from F-Droid)' in capsys.readouterr().out
    text = (skill_dir / 'skill.yaml').read_text()
    assert text.startswith('# Ghost in the Droid') and text.count('\nstatus:') == 1
    s = load_skill(skill_dir)
    assert (s.status, s.superseded_by, s.deprecated_reason) == ('deprecated', 'ghost/calc2', 'app removed from F-Droid')
    assert cli.main(['deprecate', str(skill_dir), '--reason', 'x', '--undo']) == 0
    s = load_skill(skill_dir)
    assert (s.status, s.superseded_by, s.deprecated_reason) == ('active', '', '')


def _write(skill_dir, **top):
    raw = yaml.safe_load((skill_dir / 'skill.yaml').read_text())
    raw.update(top)
    (skill_dir / 'skill.yaml').write_text(yaml.safe_dump(raw, allow_unicode=True))


def test_lineage_validation(checkout):
    skill_dir = checkout / 'ghost' / 'calculator'
    _write(skill_dir, forked_from='bob/calc')
    with pytest.raises(SchemaError, match='forked_from'):
        load_skill(skill_dir)
    _write(skill_dir, forked_from='ghost/calculator@1.0.0')
    with pytest.raises(SchemaError, match='itself'):
        load_skill(skill_dir)
    _write(skill_dir, forked_from='bob/calc@2.0.0', superseded_by='not a ref')
    with pytest.raises(SchemaError, match='superseded_by'):
        load_skill(skill_dir)
    _write(skill_dir, superseded_by='ghost/calculator')
    with pytest.raises(SchemaError, match='itself'):
        load_skill(skill_dir)
    _write(skill_dir, superseded_by='alice/calc@1.2.3', status='deprecated')
    s = load_skill(skill_dir)
    assert s.forked_from == 'bob/calc@2.0.0' and any('deprecated_reason' in w for w in s.warnings)
    _write(skill_dir, status='active', deprecated_reason='stale')
    assert any('status is not deprecated' in w for w in load_skill(skill_dir).warnings)


def test_multi_app_fingerprint(checkout):
    skill_dir = checkout / 'ghost' / 'calculator'
    raw = yaml.safe_load((skill_dir / 'skill.yaml').read_text())
    raw['fingerprint']['apps'] = ['org.fossify.gallery', 'com.simplemobiletools.notes']
    (skill_dir / 'skill.yaml').write_text(yaml.safe_dump(raw))
    s = load_skill(skill_dir)
    assert s.fingerprint.apps == ['org.fossify.gallery', 'com.simplemobiletools.notes'] and s.fingerprint.app_package == 'org.fossify.math'
    raw['fingerprint']['apps'] = ['org.fossify.math']
    (skill_dir / 'skill.yaml').write_text(yaml.safe_dump(raw))
    with pytest.raises(SchemaError, match='primary app_package'):
        load_skill(skill_dir)
    raw['fingerprint']['apps'] = ['not a package']
    (skill_dir / 'skill.yaml').write_text(yaml.safe_dump(raw))
    with pytest.raises(SchemaError, match='not a package name'):
        load_skill(skill_dir)


def test_registry_carries_lineage_and_apps(checkout):
    skill_dir = checkout / 'ghost' / 'calculator'
    raw = yaml.safe_load((skill_dir / 'skill.yaml').read_text())
    raw['fingerprint']['apps'] = ['org.fossify.gallery']
    raw.update(status='deprecated', deprecated_reason='replaced', superseded_by='alice/calc', forked_from='bob/calc@1.0.0')
    (skill_dir / 'skill.yaml').write_text(yaml.safe_dump(raw))
    reg = build_registry.build_registry(checkout, now='2026-10-20T00:00:00Z', repo_name='org/repo')
    entry = reg['skills']['ghost/calculator']
    assert (entry['forked_from'], entry['superseded_by'], entry['deprecated_reason']) == ('bob/calc@1.0.0', 'alice/calc', 'replaced')
    assert entry['versions'][entry['latest']]['fingerprint']['apps'] == ['org.fossify.gallery']
    plain = build_registry.describe_version({'skill.yaml': (REPO / 'skillhub/ghost/calculator/skill.yaml').read_bytes()}, tag=None, commit=None)[1]
    assert plain['fingerprint']['apps'] == []
    from gitd.skills.engine.find import docs_from_skill_yaml
    assert 'gallery' in docs_from_skill_yaml('ghost/calculator', raw, 'checkout')[0].tokens
