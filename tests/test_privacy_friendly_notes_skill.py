import importlib.util
from pathlib import Path
import pytest
import yaml

ROOT = Path(__file__).parents[1]
DIRECTORY = ROOT / 'skillhub/ghost/privacy-friendly-notes'
spec = importlib.util.spec_from_file_location('notes_helpers', DIRECTORY / 'helpers.py')
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)

def test_every_action_handles_welcome_before_action_helpers():
    spec = yaml.safe_load((DIRECTORY / 'skill.yaml').read_text())
    opening = next(s for s in spec['subroutines'] if s['name'] == 'open_app')
    assert opening['steps'][-1] == {'python_action': 'helpers:skip_intro'}
    for action in spec['actions']:
        steps = action['steps']
        launch = next(i for i, step in enumerate(steps) if step.get('subroutine') == 'open_app')
        assert any('python_action' in step for step in steps[launch + 1:])

@pytest.mark.parametrize('screen', ['list', 'text', 'checklist'])
def test_intro_preserves_existing_note_screen(monkeypatch, screen):
    monkeypatch.setattr(h, '_nodes', lambda _: [])
    monkeypatch.setattr(h, 'read_state', lambda *args: {'screen': screen})
    class Device:
        def tap(self, *args, **kwargs): pytest.fail('Existing notes must not be touched')
    assert h.skip_intro(Device(), {}, None) == {}

def test_first_run_skip_must_reach_note_list(monkeypatch):
    state = {'screen': 'welcome'}
    monkeypatch.setattr(h, '_nodes', lambda _: [{'id': 'btn_skip', 'bounds': (10, 20, 110, 60)}] if state['screen'] == 'welcome' else [])
    monkeypatch.setattr(h, 'read_state', lambda *args: {'screen': 'list' if state['screen'] == 'list' else 'other'})
    class Device:
        def tap(self, x, y, **kwargs):
            assert (x, y) == (60, 40)
            state['screen'] = 'list'
    h.skip_intro(Device(), {}, None)
    assert state['screen'] == 'list'

def test_unknown_or_stuck_welcome_fails_closed(monkeypatch):
    monkeypatch.setattr(h, '_nodes', lambda _: [])
    monkeypatch.setattr(h, 'read_state', lambda *args: {'screen': 'other'})
    monkeypatch.setattr(h.time, 'sleep', lambda _: None)
    with pytest.raises(RuntimeError, match='welcome did not resolve'):
        h.skip_intro(object(), {}, None)
