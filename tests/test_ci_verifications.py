"""PR verification identity and real SSH signing tests, with no network."""
import json
import subprocess
from pathlib import Path

import pytest

from tools.ci import verify_evidence


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError('Network is forbidden in verification tests')
    monkeypatch.setattr(verify_evidence.urllib.request, 'urlopen', denied)


@pytest.fixture(scope='module')
def signing_keys(tmp_path_factory, ssh_keygen):
    directory = tmp_path_factory.mktemp('ci-ssh-keys')
    keys = []
    for name in ('author', 'attacker'):
        private = directory / name
        subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(private)], check=True, capture_output=True, timeout=20)
        keys.append((private, Path(str(private) + '.pub').read_text().strip()))
    return keys


def write_signed(tmp_path, signing_keys, *, actor='reviewer-user', verifier=None, key_index=0, namespace='ghost-skill-run', filename_actor=None, principal=None):
    directory = tmp_path / 'skillhub' / 'alice' / 'chat' / 'verifications'
    directory.mkdir(parents=True, exist_ok=True)
    (directory.parent / 'skill.yaml').write_text('author: alice\nversion: 1.0.0\n')
    payload = {'schema_version': 1, 'kind': 'verification', 'skill': 'alice/chat', 'version': '1.0.0',
               'verifier': actor if verifier is None else verifier, 'fingerprint_hash': 'a' * 64,
               'success': True, 'actions': [], 'timestamp': '2026-10-05T01:00:00Z'}
    private, public = signing_keys[key_index]
    source = tmp_path / 'signed-payload.json'
    source.write_bytes(verify_evidence.canonical(payload))
    subprocess.run(['ssh-keygen', '-Y', 'sign', '-f', str(private), '-n', namespace, str(source)], check=True, capture_output=True, timeout=20)
    payload['signature'] = {'algorithm': 'ssh-ed25519', 'namespace': namespace, 'public_key': public,
                            'value': Path(str(source) + '.sig').read_text()}
    if principal is not None:
        payload['signature']['principal'] = principal
    artifact = directory / f'{filename_actor or actor}-{"a" * 64}-20261005T010000Z.json'
    artifact.write_text(json.dumps(payload, indent=2))
    return artifact


def test_signed_verification_matches_pr_author_and_registered_key(tmp_path, signing_keys):
    path = write_signed(tmp_path, signing_keys)
    # Accept any registered author key, with the signing key among them.
    assert verify_evidence.verify_artifact(path, 'reviewer-user', [signing_keys[1][1], signing_keys[0][1]], 'alice') == str(path)


@pytest.mark.parametrize('kwargs,message', [
    ({'verifier': 'impostor'}, 'verifier field'),
    ({'filename_actor': 'other-user'}, 'filename prefix'),
    ({'filename_actor': 'reviewer-user-extra'}, 'filename prefix'),
    ({'principal': 'impostor'}, 'principal'),
    ({'namespace': 'other-purpose'}, 'namespace'),
])
def test_identity_namespace_and_principal_mismatch_rejected(tmp_path, signing_keys, kwargs, message):
    path = write_signed(tmp_path, signing_keys, **kwargs)
    with pytest.raises(ValueError, match=message):
        verify_evidence.verify_artifact(path, 'reviewer-user', [signing_keys[0][1]], 'alice')


def test_wrong_key_rejected_despite_spoofed_embedded_public_key(tmp_path, signing_keys):
    path = write_signed(tmp_path, signing_keys, key_index=1)
    data = json.loads(path.read_text())
    data['signature']['public_key'] = signing_keys[0][1]
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='does not verify'):
        verify_evidence.verify_artifact(path, 'reviewer-user', [signing_keys[0][1]], 'alice')


def test_tampered_signed_payload_rejected(tmp_path, signing_keys):
    path = write_signed(tmp_path, signing_keys)
    data = json.loads(path.read_text())
    data['success'] = False
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='does not verify'):
        verify_evidence.verify_artifact(path, 'reviewer-user', [signing_keys[0][1]], 'alice')


def test_self_verification_rejected_case_insensitively(tmp_path, signing_keys):
    path = write_signed(tmp_path, signing_keys, actor='Alice')
    with pytest.raises(ValueError, match='own skill'):
        verify_evidence.verify_artifact(path, 'Alice', [signing_keys[0][1]], 'alice')


def test_missing_verifier_field_is_rejected(tmp_path, signing_keys):
    path = write_signed(tmp_path, signing_keys)
    data = json.loads(path.read_text())
    data.pop('verifier')
    data['github_login'] = 'reviewer-user'
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='verifier field'):
        verify_evidence.verify_artifact(path, 'reviewer-user', [signing_keys[0][1]], 'alice')


def test_conflicting_legacy_login_is_rejected(tmp_path, signing_keys):
    path = write_signed(tmp_path, signing_keys)
    data = json.loads(path.read_text())
    data['github_login'] = 'impostor'
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='github_login'):
        verify_evidence.verify_artifact(path, 'reviewer-user', [signing_keys[0][1]], 'alice')


def test_symlink_and_unsigned_artifact_rejected(tmp_path, signing_keys):
    path = write_signed(tmp_path, signing_keys)
    link = path.with_name('link.json')
    link.symlink_to(path)
    with pytest.raises(ValueError, match='regular JSON'):
        verify_evidence.verify_artifact(link, 'reviewer-user', [signing_keys[0][1]], 'alice')
    data = json.loads(path.read_text())
    data.pop('signature')
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='SSH signature'):
        verify_evidence.verify_artifact(path, 'reviewer-user', [signing_keys[0][1]], 'alice')


def test_verification_path_filter_and_evidence_only_gate():
    artifact = f'skillhub/alice/chat/verifications/reviewer-{"a" * 64}-now.json'
    assert verify_evidence.verification_paths([artifact, artifact, 'skillhub/alice/chat/runs/self.json', 'skillhub/alice/chat/verifications/nested/other.json']) == [artifact]
    assert verify_evidence.only_verifications([artifact])
    assert not verify_evidence.only_verifications([artifact, 'skillhub/alice/chat/helpers.py'])
    assert not verify_evidence.only_verifications([])


def test_changed_artifacts_include_additions_modifications_and_type_changes(monkeypatch):
    commands = []
    path = 'skillhub/alice/chat/verifications/reviewer.json'
    monkeypatch.setattr(verify_evidence.subprocess, 'check_output', lambda command: commands.append(command) or path.encode() + b'\0')
    assert verify_evidence.changed_verifications('base', 'head') == [path]
    assert '--no-renames' in commands[0] and '--diff-filter=AMT' in commands[0] and '-z' in commands[0]


def test_fetch_keys_uses_github_author_and_discards_options(monkeypatch, signing_keys):
    requested = []
    public = signing_keys[0][1]
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self, size):
            return (public + '\ncommand="bad" ' + public + '\n').encode()
    monkeypatch.setattr(verify_evidence.urllib.request, 'urlopen', lambda url, **kw: requested.append((url, kw)) or Response())
    assert verify_evidence.fetch_author_keys('reviewer-user') == [' '.join(public.split()[:2])]
    assert requested == [('https://github.com/reviewer-user.keys', {'timeout': 20})]


def test_invalid_login_never_fetches_keys():
    with pytest.raises(ValueError, match='Invalid'):
        verify_evidence.fetch_author_keys('reviewer/../../bad')


def test_main_fetches_author_keys_once_and_verifies_real_signature(tmp_path, monkeypatch, signing_keys):
    path = write_signed(tmp_path, signing_keys)
    monkeypatch.chdir(tmp_path)
    relative = str(path.relative_to(tmp_path))
    monkeypatch.setattr(verify_evidence, 'changed_verifications', lambda base, head: [relative])
    monkeypatch.setattr(verify_evidence, 'signers_changed', lambda base, head: False)
    requested = []
    monkeypatch.setattr(verify_evidence, 'fetch_author_keys', lambda actor: requested.append(actor) or [signing_keys[0][1]])
    monkeypatch.setattr('sys.argv', ['verify_evidence', '--base', 'base', '--head', 'head', '--actor', 'reviewer-user'])
    assert verify_evidence.main() == 0
    assert requested == ['reviewer-user']


def test_main_rejects_self_verification_in_namespace(tmp_path, monkeypatch, signing_keys):
    path = write_signed(tmp_path, signing_keys, actor='alice')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(verify_evidence, 'changed_verifications', lambda base, head: [str(path.relative_to(tmp_path))])
    monkeypatch.setattr(verify_evidence, 'signers_changed', lambda base, head: False)
    monkeypatch.setattr(verify_evidence, 'fetch_author_keys', lambda actor: [signing_keys[0][1]])
    monkeypatch.setattr('sys.argv', ['verify_evidence', '--base', 'base', '--actor', 'alice'])
    assert verify_evidence.main() == 1


def test_main_no_artifacts_never_fetches_keys(monkeypatch):
    monkeypatch.setattr(verify_evidence, 'changed_verifications', lambda base, head: [])
    monkeypatch.setattr(verify_evidence, 'signers_changed', lambda base, head: False)
    monkeypatch.setattr('sys.argv', ['verify_evidence', '--base', 'base', '--actor', 'reviewer-user'])
    assert verify_evidence.main() == 0


def _signers(login, public):
    return f'{login} namespaces="ghost-skill-run" {" ".join(public.split()[:2])}'


def test_signers_lines_bind_to_actor_and_published_keys(signing_keys):
    author_pub, attacker_pub = signing_keys[0][1], signing_keys[1][1]
    assert verify_evidence.check_signers_lines([_signers('reviewer-user', author_pub)], [], 'reviewer-user', [author_pub]) == ['reviewer-user']
    assert verify_evidence.check_signers_lines([], [], 'reviewer-user', [author_pub]) == []
    with pytest.raises(ValueError, match='only be added for the PR author'):
        verify_evidence.check_signers_lines([_signers('ghost', author_pub)], [], 'reviewer-user', [author_pub])
    with pytest.raises(ValueError, match='not published'):
        verify_evidence.check_signers_lines([_signers('reviewer-user', attacker_pub)], [], 'reviewer-user', [author_pub])
    with pytest.raises(ValueError, match='not "<login> namespaces'):
        verify_evidence.check_signers_lines([f'reviewer-user {author_pub}'], [], 'reviewer-user', [author_pub])
    with pytest.raises(ValueError, match='only be removed by their own principal'):
        verify_evidence.check_signers_lines([], [_signers('alice', author_pub)], 'reviewer-user', [author_pub])
    with pytest.raises(ValueError, match='Invalid PR author'):
        verify_evidence.check_signers_lines([], [], 'bad/login', [author_pub])


def test_main_checks_signers_change_without_verification_artifacts(tmp_path, monkeypatch, signing_keys, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(verify_evidence, 'changed_verifications', lambda base, head: [])
    monkeypatch.setattr(verify_evidence, 'signers_changed', lambda base, head: True)
    monkeypatch.setattr(verify_evidence, 'signers_diff', lambda base, head: ([_signers('reviewer-user', signing_keys[0][1])], []))
    requested = []
    monkeypatch.setattr(verify_evidence, 'fetch_author_keys', lambda actor: requested.append(actor) or [signing_keys[0][1]])
    monkeypatch.setattr('sys.argv', ['verify_evidence.py', '--base', 'b', '--head', 'h', '--actor', 'reviewer-user'])
    assert verify_evidence.main() == 0
    assert requested == ['reviewer-user'] and 'Verified SIGNERS change: 1 added' in capsys.readouterr().out
    monkeypatch.setattr(verify_evidence, 'signers_diff', lambda base, head: ([_signers('ghost', signing_keys[0][1])], []))
    assert verify_evidence.main() == 1
    assert 'only be added for the PR author' in capsys.readouterr().out


def test_signers_diff_reads_both_revisions(tmp_path, monkeypatch):
    repo = tmp_path / 'repo'; (repo / 'skillhub').mkdir(parents=True)
    env = {'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@x', 'GIT_COMMITTER_NAME': 't', 'GIT_COMMITTER_EMAIL': 't@x'}
    def git(*args):
        subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True, env={**__import__('os').environ, **env})
    git('init', '-q'); (repo / 'skillhub/SIGNERS').write_text('# header\nalice namespaces="ghost-skill-run" ssh-ed25519 AAAA\n')
    git('add', '.'); git('commit', '-q', '-m', 'base')
    (repo / 'skillhub/SIGNERS').write_text('# header\nbob namespaces="ghost-skill-run" ssh-ed25519 BBBB\n')
    git('add', '.'); git('commit', '-q', '-m', 'head')
    monkeypatch.chdir(repo)
    assert verify_evidence.signers_changed('HEAD~1', 'HEAD') is True
    assert verify_evidence.signers_diff('HEAD~1', 'HEAD') == (['bob namespaces="ghost-skill-run" ssh-ed25519 BBBB'],
                                                              ['alice namespaces="ghost-skill-run" ssh-ed25519 AAAA'])
