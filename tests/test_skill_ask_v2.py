"""Typed ask steps using fake channels, devices and providers."""
import json
import threading
import pytest
from gitd.skills.engine import load_skill, run_action
from gitd.skills.engine import runner, hitl
from gitd.skills.engine.ask import validate_answer, NO_ANSWER
from gitd.skills.engine.ask_resume import resume_action, token_path
from gitd.skills.engine.errors import AskInvalidAnswerError, SchemaError
from tests.test_skill_checkpoint_v2 import make_skill, FakeDevice


def skill(tmp_path, who='human', **options):
    path = make_skill(tmp_path, '{reason: generic}')
    import yaml
    raw = yaml.safe_load((path / 'skill.yaml').read_text())
    raw['skill_class'] = 'hard'
    raw['actions'][0]['steps'] = [
        {'ask': {**dict(who=who, prompt='Your answer?', schema={'type': 'int'}, store_as='choice', timeout_s=1), **options}},
        {'python_action': 'helpers:save'}]
    (path / 'helpers.py').write_text('def always(device, context):\n    return True\ndef save(device, params, context):\n    context.result["choice"] = context.choice\n')
    (path / 'skill.yaml').write_text(yaml.safe_dump(raw))
    return load_skill(path)


@pytest.fixture(autouse=True)
def device(monkeypatch):
    monkeypatch.setattr(runner, '_get_device', lambda serial: FakeDevice())


def test_human(tmp_path):
    ch = hitl.LocalChannel(echo=False)
    ch.answer(7)
    result = run_action(skill(tmp_path), 'go', checkpoint_channel=ch, device_serial='fake')
    assert result.success, result.error
    assert result.data['choice'] == 7
    assert result.trace[0].ask['answered_by'] == 'human'


def test_parent_resume(tmp_path, monkeypatch):
    monkeypatch.setenv('HOME', str(tmp_path))
    result = run_action(skill(tmp_path, 'parent_agent', attach=['a11y', {'params': ['who']}]), 'go', device_serial='fake')
    assert result.status == 'needs_input'
    assert result.data['attachments']['params'] == {'who': 'me'}
    assert token_path(result.resume_token).exists()
    with pytest.raises(AskInvalidAnswerError):
        resume_action(result.resume_token, 'wrong')
    resumed = resume_action(result.resume_token, 4)
    assert resumed.success, resumed.error
    assert resumed.data['choice'] == 4
    assert resumed.trace[0].ask['answered_by'] == 'parent_agent'
    assert not token_path(result.resume_token).exists()


def test_sub_agent(tmp_path, monkeypatch):
    from gitd.skills.engine import ask_agent
    class Agent:
        def answer(self, *args, **kwargs):
            assert kwargs['max_turns'] == 3
            return 9
    monkeypatch.setattr(ask_agent, 'ask_agent', Agent())
    result = run_action(skill(tmp_path, 'sub_agent'), 'go', device_serial='fake')
    assert result.success and result.data['choice'] == 9


@pytest.mark.parametrize('who', ['human', 'sub_agent'])
def test_fallback(tmp_path, monkeypatch, who):
    from gitd.skills.engine import ask_agent
    monkeypatch.setattr(ask_agent.ask_agent, 'answer', lambda *a, **kw: NO_ANSWER)
    s = skill(tmp_path, who, fallback={'value': 2})
    assert s.skill_class == 'hard'
    result = run_action(s, 'go', device_serial='fake')
    assert result.success and result.data['choice'] == 2


def test_dry(tmp_path):
    result = run_action(skill(tmp_path, 'parent_agent'), 'go', dry_run=True)
    assert result.success and result.data['asks'][0]['answered_by'] == 'dry_run'


@pytest.mark.parametrize('value,schema', [(True, {'type': 'int'}), (1, {'type': 'str'}), ('x', {'type': 'enum', 'values': ['y']})])
def test_invalid(value, schema):
    with pytest.raises(AskInvalidAnswerError):
        validate_answer(value, schema)


def test_loader(tmp_path):
    with pytest.raises(SchemaError, match='ask'):
        skill(tmp_path, schema={})


def test_human_timeout(tmp_path):
    ch = hitl.LocalChannel(echo=False)
    result = run_action(skill(tmp_path), 'go', checkpoint_channel=ch, device_serial='fake')
    assert not result.success and result.error['kind'] == 'AskTimeoutError'
    assert result.trace[0].ask['who'] == 'human'


def test_indefinite_human(tmp_path):
    ch = hitl.LocalChannel(echo=False)
    threading.Timer(0.1, lambda: ch.answer(3)).start()
    result = run_action(skill(tmp_path, timeout_s=0), 'go', checkpoint_channel=ch, device_serial='fake')
    assert result.success and result.data['choice'] == 3


def test_typed_errors():
    from gitd.skills.engine.errors import AskTimeoutError
    assert AskTimeoutError('timeout').as_dict()['kind'] == 'AskTimeoutError'
    assert AskInvalidAnswerError('invalid').as_dict()['kind'] == 'AskInvalidAnswerError'
