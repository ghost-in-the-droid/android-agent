"""`ghost skill submit`: plan by default, `--push` forks + isolated-index commit + PR, gh and git mocked."""
import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from gitd.skills.engine import cli, submission

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def checkout(tmp_path, monkeypatch):
    root = tmp_path / 'checkout'
    skill = root / 'skillhub/ghost/tiktok'
    skill.parent.mkdir(parents=True)
    shutil.copytree(REPO / 'skillhub/ghost/tiktok', skill, ignore=shutil.ignore_patterns('runs', 'verifications', '__pycache__'))
    (root / '.git').touch()
    monkeypatch.chdir(root)
    monkeypatch.delenv('GHOST_HUB_REPO', raising=False)
    calls = []
    state = {'login': 'alice', 'existing_pr': '', 'fail': None, 'can_push': 'false'}

    def fake_run(args, **kwargs):
        calls.append((list(args), kwargs))
        if state['fail'] and args[:len(state['fail'])] == state['fail']:
            raise subprocess.CalledProcessError(1, args, stderr='mock failure')
        if args[:3] == ['gh', 'api', 'user']:
            return SimpleNamespace(stdout=state['login'])
        if args[:2] == ['gh', 'api'] and args[2].startswith('repos/'):
            return SimpleNamespace(stdout=state['can_push'])
        if args[:3] == ['gh', 'repo', 'fork']:
            return SimpleNamespace(stdout='alice/hub already exists')
        if args[:3] == ['gh', 'repo', 'view']:
            return SimpleNamespace(stdout='main')
        if args[:3] == ['gh', 'pr', 'list']:
            return SimpleNamespace(stdout=state['existing_pr'])
        if args[:3] == ['gh', 'pr', 'create']:
            state['body'] = Path(args[args.index('--body-file') + 1]).read_text()
            return SimpleNamespace(stdout='https://github.com/ghost-in-the-droid/android-agent/pull/7')
        if args[:2] in [['git', 'rev-parse'], ['git', 'hash-object'], ['git', 'write-tree'], ['git', 'commit-tree']]:
            return SimpleNamespace(stdout='b' * 40)
        if args[0] == 'git':
            return SimpleNamespace(stdout='')
        pytest.fail('Unexpected external command: ' + repr(args))

    monkeypatch.setattr(subprocess, 'run', fake_run)
    monkeypatch.setattr('urllib.request.urlopen', lambda *a, **kw: pytest.fail('No real network'))
    return SimpleNamespace(root=root, skill=skill, calls=calls, state=state)


def commands(env):
    return [args for args, kwargs in env.calls]


def test_default_is_a_plan_and_runs_nothing(checkout, capsys):
    assert cli.main(['submit', 'skillhub/ghost/tiktok']) == 0
    out = capsys.readouterr().out
    plan = json.loads(out[out.index('\n{\n') + 1:out.rindex('}') + 1])  # the analysis table precedes the plan
    assert plan['title'].startswith('[skill] ghost/tiktok v')
    assert plan['branch'] == 'skill/ghost-tiktok'
    assert plan['repo'] == submission.DEFAULT_VERIFY_REPO
    assert 'skillhub/ghost/tiktok/skill.yaml' in plan['files']
    assert 'Pass --push' in out
    assert checkout.calls == []


def test_dry_run_flag_is_still_accepted_and_push_excludes_it(checkout, capsys):
    assert cli.main(['submit', 'skillhub/ghost/tiktok', '--dry-run']) == 0
    assert checkout.calls == []
    assert cli.main(['submit', 'skillhub/ghost/tiktok', '--push', '--dry-run']) == 1
    assert 'mutually exclusive' in capsys.readouterr().err
    assert checkout.calls == []


def test_push_forks_commits_on_isolated_index_and_opens_pr(checkout, capsys):
    env = checkout
    target = submission.DEFAULT_VERIFY_REPO
    assert cli.main(['submit', 'skillhub/ghost/tiktok', '--push']) == 0
    cmds = commands(env)
    fork, = [c for c in cmds if c[:3] == ['gh', 'repo', 'fork']]
    assert fork[3] == target and '--clone=false' in fork
    fetch, = [c for c in cmds if c[:2] == ['git', 'fetch']]
    assert fetch == ['git', 'fetch', '--no-tags', f'https://github.com/{target}.git', 'refs/heads/main']
    push, = [c for c in cmds if c[:2] == ['git', 'push']]
    assert push[2] == f'https://github.com/alice/{target.split("/")[1]}.git'
    assert push[3] == '+refs/heads/skill/ghost-tiktok:refs/heads/skill/ghost-tiktok'
    assert 'origin' not in push
    pr, = [c for c in cmds if c[:3] == ['gh', 'pr', 'create']]
    assert pr[pr.index('--repo') + 1] == target
    assert pr[pr.index('--base') + 1] == 'main'
    assert pr[pr.index('--head') + 1] == 'alice:skill/ghost-tiktok'
    assert pr[pr.index('--title') + 1].startswith('[skill] ghost/tiktok v')
    assert '| Action |' in env.state['body'] and 'Contribution checklist' in env.state['body']
    indexed = [c[-1] for c in cmds if c[:2] == ['git', 'update-index']]
    expected = submission.skill_submission_files(env.root, env.skill)
    assert indexed == expected and 'skillhub/ghost/tiktok/skill.yaml' in indexed
    assert all(path.startswith('skillhub/ghost/tiktok/') for path in indexed)
    assert not any(c[1] in {'checkout', 'switch', 'add', 'commit', 'reset', 'stash', 'tag'} for c in cmds if c[0] == 'git')
    isolated = {kwargs['env']['GIT_INDEX_FILE'] for args, kwargs in env.calls if args[:2] in [['git', 'read-tree'], ['git', 'update-index'], ['git', 'write-tree']]}
    assert len(isolated) == 1 and not Path(isolated.pop()).exists()
    out = capsys.readouterr().out
    assert 'Skill PR: https://github.com/ghost-in-the-droid/android-agent/pull/7' in out
    assert 'official namespace' in out


def test_push_to_own_repository_skips_the_fork(checkout, monkeypatch):
    env = checkout
    monkeypatch.setenv('GHOST_HUB_REPO', 'Alice/hub')
    assert cli.main(['submit', 'skillhub/ghost/tiktok', '--push']) == 0
    cmds = commands(env)
    assert not any(c[:3] == ['gh', 'repo', 'fork'] for c in cmds)
    push, = [c for c in cmds if c[:2] == ['git', 'push']]
    assert push[2] == 'https://github.com/Alice/hub.git'
    pr, = [c for c in cmds if c[:3] == ['gh', 'pr', 'create']]
    assert pr[pr.index('--head') + 1] == 'skill/ghost-tiktok'


def test_push_with_write_access_skips_the_fork(checkout, monkeypatch):
    # Maintainers of an org hub (or a repo with forking disabled) push the branch to the hub itself.
    env = checkout
    env.state['can_push'] = 'true'
    monkeypatch.setenv('GHOST_HUB_REPO', 'some-org/hub')
    assert cli.main(['submit', 'skillhub/ghost/tiktok', '--push']) == 0
    cmds = commands(env)
    assert not any(c[:3] == ['gh', 'repo', 'fork'] for c in cmds)
    push, = [c for c in cmds if c[:2] == ['git', 'push']]
    assert push[2] == 'https://github.com/some-org/hub.git'
    pr, = [c for c in cmds if c[:3] == ['gh', 'pr', 'create']]
    assert pr[pr.index('--head') + 1] == 'skill/ghost-tiktok'


def test_push_updates_an_open_pr_instead_of_creating_a_second(checkout, capsys):
    env = checkout
    env.state['existing_pr'] = 'https://github.com/ghost-in-the-droid/android-agent/pull/3'
    assert cli.main(['submit', 'skillhub/ghost/tiktok', '--push']) == 0
    cmds = commands(env)
    assert any(c[:2] == ['git', 'push'] for c in cmds)
    assert not any(c[:3] == ['gh', 'pr', 'create'] for c in cmds)
    assert 'Skill PR: https://github.com/ghost-in-the-droid/android-agent/pull/3' in capsys.readouterr().out


def test_push_fails_closed_before_any_remote_call(checkout, capsys):
    env = checkout
    (env.skill / 'suspicious.py').write_text("import os\nos.system('true')\n")
    assert cli.main(['submit', 'skillhub/ghost/tiktok', '--push']) == 2
    assert env.calls == []
    capsys.readouterr()
    (env.skill / 'suspicious.py').unlink()
    env.state['fail'] = ['gh', 'api', 'user']
    assert cli.main(['submit', 'skillhub/ghost/tiktok', '--push']) == 1
    assert 'gh api' in capsys.readouterr().err
    assert not any(c[:2] == ['git', 'push'] or c[:3] == ['gh', 'pr', 'create'] for c in commands(env))


def test_submission_files_reject_symlinks_and_paths_outside_skillhub(checkout, tmp_path):
    env = checkout
    files = submission.skill_submission_files(env.root, env.skill)
    assert files == sorted(files) and all('/__pycache__/' not in f and not f.endswith('.pyc') for f in files)
    link = env.skill / 'escape.yaml'
    link.symlink_to(tmp_path / 'outside.yaml')
    with pytest.raises(ValueError, match='symlinks'):
        submission.skill_submission_files(env.root, env.skill)
    link.unlink()
    outside = env.root / 'docs'
    outside.mkdir()
    (outside / 'skill.yaml').write_text('name: x\n')
    with pytest.raises(ValueError, match='skillhub/<author>/<slug>'):
        submission.skill_submission_files(env.root, outside)
    with pytest.raises(ValueError, match='does not match'):
        submission.push_skill(env.root, env.skill, {'repo': None, 'branch': 'skill/ghost-tiktok', 'files': ['skillhub/ghost/tiktok/skill.yaml'], 'title': 't', 'body': 'b'})
