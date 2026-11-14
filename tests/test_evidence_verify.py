"""gitd.skills.engine.evidence: registry-side verification of run artifacts (reviewer finding P0 #1)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from gitd.skills.engine import evidence

pytestmark = pytest.mark.skipif(shutil.which('ssh-keygen') is None, reason='ssh-keygen not installed')


@pytest.fixture
def signer(tmp_path, monkeypatch):
    monkeypatch.setenv('GHOST_CONFIG_DIR', str(tmp_path / 'config'))
    public = evidence.signing_public_key()
    signers = tmp_path / 'SIGNERS'
    signers.write_text('# keys\n' + evidence.signers_line('alice', public))
    return signers, public


def _artifact(**overrides):
    payload = {'schema_version': 1, 'kind': 'self-run', 'skill': 'alice/foo', 'version': '1.0.0',
               'fingerprint_hash': 'f' * 64, 'success': True, 'actions': [], 'device_backend': 'device',
               'simulation': False, 'finished_at': '2026-10-01T00:00:00Z'}
    payload.update(overrides)
    payload['signature'] = evidence._sign(payload)
    return payload


def test_signed_self_run_verifies_under_the_author_principal(signer):
    signers, public = signer
    data = _artifact()
    assert data['signature']['public_key'].split()[:2] == public.split()[:2]
    assert evidence.artifact_rejection(data, skill_ref='alice/foo', principal='alice', allowed_signers=signers) is None


@pytest.mark.parametrize('mutate, reason', [
    (lambda d: d.pop('signature'), 'unsigned'),
    (lambda d: d['signature'].update(namespace='file'), 'unsigned'),
    (lambda d: d.update(simulation=True), 'simulated'),
    (lambda d: d.update(device_backend='fake'), 'simulated'),
    (lambda d: d.update(skill='alice/bar'), 'wrong-skill'),
    (lambda d: d.update(success=False), 'bad-signature'),                         # tampered after signing
    (lambda d: d['signature'].update(value='-----BEGIN SSH SIGNATURE-----\nx\n-----END SSH SIGNATURE-----\n'), 'bad-signature'),
    (lambda d: d.update(bench={'suite': 'androidworld', 'arm': 'after_replay'}), 'bad-bench-block'),
    (lambda d: d.update(bench={'suite': 'androidworld', 'task_id': 'T', 'arm': 'sideways'}), 'bad-bench-block'),
    (lambda d: d.update(bench={'suite': 'androidworld', 'task_id': 'T', 'arm': 'before', 'seed': -1}), 'bad-bench-block'),
])
def test_rejection_reasons(signer, mutate, reason):
    signers, _ = signer
    data = _artifact()
    mutate(data)
    assert evidence.artifact_rejection(data, skill_ref='alice/foo', principal='alice', allowed_signers=signers) == reason


def test_unknown_principal_and_unlisted_key_are_bad_signature(signer, tmp_path):
    signers, _ = signer
    data = _artifact()
    assert evidence.artifact_rejection(data, skill_ref='alice/foo', principal='mallory', allowed_signers=signers) == 'bad-signature'
    empty = tmp_path / 'EMPTY'; empty.write_text('')
    assert evidence.artifact_rejection(data, skill_ref='alice/foo', principal='alice', allowed_signers=empty) == 'bad-signature'
    assert evidence.artifact_rejection(data, skill_ref='alice/foo', principal='alice', allowed_signers=tmp_path / 'missing') == 'bad-signature'


def test_embedded_public_key_is_not_trusted(signer, tmp_path):
    """A hand-written artifact carrying its own key must not verify: the trust store decides."""
    signers, _ = signer
    private = tmp_path / 'mallory'
    subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(private)], check=True, capture_output=True)
    payload = {'skill': 'alice/foo', 'success': True, 'device_backend': 'device', 'simulation': False}
    source = tmp_path / 'p.json'; source.write_bytes(evidence.canonical(payload))
    subprocess.run(['ssh-keygen', '-Y', 'sign', '-f', str(private), '-n', evidence.NAMESPACE, str(source)], check=True, capture_output=True)
    payload['signature'] = {'algorithm': 'ssh-ed25519', 'namespace': evidence.NAMESPACE,
                            'public_key': (tmp_path / 'mallory.pub').read_text().strip(),
                            'value': (tmp_path / 'p.json.sig').read_text()}
    assert evidence.artifact_rejection(payload, skill_ref='alice/foo', principal='alice', allowed_signers=signers) == 'bad-signature'


def test_verification_fails_closed_without_ssh_keygen(signer, monkeypatch):
    signers, _ = signer
    data = _artifact()
    monkeypatch.setattr(evidence.shutil, 'which', lambda name: None)
    assert evidence.artifact_rejection(data, skill_ref='alice/foo', principal='alice', allowed_signers=signers) == 'bad-signature'


def test_well_formed_bench_block_is_accepted_and_signed(signer):
    signers, _ = signer
    bench = {'suite': 'androidworld', 'task_id': 'ExpenseAddMultipleFromMarkor', 'arm': 'after_replay', 'seed': 3,
             'steps': 12, 'tokens': 0, 'wall_ms': 41000, 'trace_path': 'traces/x.json'}
    data = _artifact(bench=bench)
    assert evidence.bench_block_error(bench) is None
    assert evidence.artifact_rejection(data, skill_ref='alice/foo', principal='alice', allowed_signers=signers) is None


def test_signers_line_format_and_validation():
    line = evidence.signers_line('alice', 'ssh-ed25519 AAAATEST comment here')
    assert line == 'alice namespaces="ghost-skill-run" ssh-ed25519 AAAATEST\n'
    with pytest.raises(ValueError):
        evidence.signers_line('bad/login', 'ssh-ed25519 AAAATEST')
    with pytest.raises(ValueError):
        evidence.signers_line('alice', 'not-a-key')


def test_keys_subcommand_prints_key_and_signers_line(tmp_path, monkeypatch, capsys):
    from gitd.skills.engine import cli
    monkeypatch.setenv('GHOST_CONFIG_DIR', str(tmp_path / 'config'))
    assert cli.main(['keys', '--principal', 'alice', '--json']) == 0
    out = json.loads(capsys.readouterr().out)
    assert out['public_key'].startswith('ssh-ed25519 ')
    assert out['signers_line'] == evidence.signers_line('alice', out['public_key']).rstrip('\n')
    assert cli.main(['keys']) == 0
    text = capsys.readouterr().out
    assert 'Run-signing public key: ssh-ed25519' in text and 'SIGNERS' in text
