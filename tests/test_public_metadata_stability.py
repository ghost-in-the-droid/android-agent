"""Provider refreshes must settle; ownership and fresh validation stay strict."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture(params=['myne', 'transportr'])
def helper(request, monkeypatch):
    path = Path(__file__).parents[1] / 'skillhub/ghost' / request.param / 'helpers.py'
    spec = importlib.util.spec_from_file_location('stability_' + request.param, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    clock = SimpleNamespace(now=0.0)
    monkeypatch.setattr(module, 'time', SimpleNamespace(
        monotonic=lambda: clock.now,
        sleep=lambda duration: setattr(clock, 'now', clock.now + duration),
    ))
    return module


def test_refresh_and_incomplete_rows_restart_consecutive_read_requirement(helper, monkeypatch):
    samples = iter([{'row': 'old'}, None, {'row': 'new'}, {'row': 'new'}])
    seen = []
    monkeypatch.setattr(helper, 'nodes', lambda device: next(samples))

    def parse(rows):
        seen.append(rows)
        if rows is None:
            raise ValueError('Rows still loading')
        return rows

    assert helper.stable_read(object(), parse) == {'row': 'new'}
    assert len(seen) == 4


def test_focus_loss_aborts_without_retrying_or_parsing(helper, monkeypatch):
    def lost_focus(device):
        raise ValueError('Foreign window owns focus')

    monkeypatch.setattr(helper, 'nodes', lost_focus)
    with pytest.raises(ValueError, match='Foreign window'):
        helper.stable_read(object(), lambda rows: pytest.fail('Must not parse foreign UI'))
    assert helper.time.monotonic() == 0


def test_never_stable_provider_stops_at_deadline(helper, monkeypatch):
    reads = []

    def changing(device):
        reads.append(len(reads))
        return {'revision': len(reads)}

    monkeypatch.setattr(helper, 'nodes', changing)
    with pytest.raises(ValueError, match='did not stabilize'):
        helper.stable_read(object(), lambda rows: rows, timeout=1)
    assert len(reads) == 4
    assert 1 <= helper.time.monotonic() < 1.3


def test_validator_rejects_metadata_changed_after_action(helper, monkeypatch):
    monkeypatch.setattr(helper, 'nodes', lambda device: [])
    context = SimpleNamespace(result={'revision': 'old'}, params={})
    if helper.PKG == 'com.starry.myne':
        monkeypatch.setattr(helper, 'catalog_data', lambda rows: {'revision': 'new'})
        assert not helper.catalog_ok(object(), context)
    else:
        monkeypatch.setattr(helper, 'connections', lambda rows: {'revision': 'new'})
        assert not helper.connections_ok(object(), context)
